import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.agent.tools import Tool, ToolRegistry
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.places import DEATH, Places, server_of
from src.core.skills.minecraft.state import count_items, render_state
from src.core.skills.minecraft.tools import build_minecraft_tools
from src.utils.logger import get_logger
from src.utils.prompts import prompt_for

logger = get_logger("bea.skills.minecraft")

# how long she may stand around doing nothing in the game before she is told.
# 0 turns the nudge off.
IDLE_NUDGE_SECONDS = 30.0

# the shortest gap between two words asked of her while a long action runs,
# and only when something changed in it. 0 turns it off.
COMMENTARY_SECONDS = 20.0

# how long something the game did on its own (eating, getting unstuck) stays in
# her frame: long enough to be seen by the next turn, short enough to be news
REFLEX_MEMORY_SECONDS = 60.0

# the reflexes worth a turn of their own: being in a fight, having died
_LOUD_REFLEXES = ("defend", "respawn")

# the most one clipped line carries into her frame
LINE_LIMIT = 220

# where a perception comes from when it is about the game she is in
_GAME_SURFACES = ("game:mc", "chat:mc")

# measured live: three game turns in a row were one `speak` each ("let me just
# start punching some birch logs"), and a spoken turn is over, so nothing moved
_EMPTY_HANDS = (
    "[Nothing is happening in Minecraft: your hands are empty, and this turn only "
    "talked. Do what you said — call the game action now. Don't say it again. If you "
    "really choose to stand there, stay_silent.]"
)


@dataclass
class Doing:
    """One action of hers in progress: what, since when, and how it is going."""

    name: str
    args: Dict[str, Any]
    started: float = field(default_factory=time.time)
    progress: str = ""

    def describe(self) -> str:
        shown = ", ".join(f"{k}={v}" for k, v in self.args.items() if not isinstance(v, (dict, list)))
        return f"{self.name}({shown})"


class MinecraftSurface(Skill):
    """Minecraft, lived in: the game's senses in, the game's tools out.

    She plays it herself. The tools are hers the way `send_message` is: an
    action that takes time runs beside her and comes back as what happened,
    and everything she reads about the game is about her.
    """

    name = "game:mc"
    skill_name = "minecraft"

    def initialize(self) -> None:
        persona = persona_of(self.config)
        self._rules = persona.fill(
            prompt_for(self.skill_config, "system_prompt", "data/prompts/minecraft.md"))
        self.client: Optional[MinecraftClient] = None
        self.places: Optional[Places] = None
        self._saving: set = set()
        self._registry: Optional[ToolRegistry] = None
        self._poll_task: Optional[asyncio.Task] = None
        self.doing: Optional[Doing] = None
        # the last thing her hands finished, for the dashboard
        self._last: str = ""
        self._idle_since: float = time.time()
        self._last_nudge: float = 0.0
        self._last_commentary: float = 0.0
        # what the last word asked of her was about: the same again is not news
        self._said_about: Optional[Tuple] = None
        self._reflexes: List[Tuple[float, str]] = []

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("minecraft", {})

    async def start(self) -> None:
        if not self.enabled:
            logger.info("MinecraftSurface inactive (minecraft skill disabled).")
            return
        url = self.skill_config.get("server_url", "ws://127.0.0.1:8080")
        loop = asyncio.get_running_loop()
        self.client = MinecraftClient(url, loop, on_event=self._on_mod_event)
        self.places = await asyncio.to_thread(Places)
        self._registry = build_minecraft_tools(
            self.client, build_scripts=bool(self.skill_config.get("build_scripts", True)),
            places=self.places)
        self.client.connect()
        self.active = True
        self._idle_since = time.time()
        self._poll_task = asyncio.create_task(self._perceive_loop())
        logger.info("MinecraftSurface started.")

    async def stop(self) -> None:
        self.active = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        if self.client:
            self.client.stop()
            self.client = None
        self._registry = None
        self.doing = None
        logger.info("MinecraftSurface stopped.")

    async def _perceive_loop(self) -> None:
        """Streams game events onto the bus.

        The periodic snapshot is marked `noise`: the state is always in
        live_state, so only real events (interrupts, deaths) wake the mind.
        """
        if self.client is None:
            return
        await self.client.wait_until_ready()
        self._joined()
        while self.active and self.client is not None:
            await self.client.wait_for_event_or_timeout(10.0)
            if self.client is None:
                break
            events = self.client.drain_events()
            if not events:
                nudge = self._nudge()
                if nudge:
                    self.bus.put(nudge)
                else:
                    # nothing happened: don't pay to serialize 700 lidar blocks
                    self.bus.put(Perception(PerceptionKind.GAME, self.name, "(still playing)",
                                            salience=0.15, meta={"noise": True}))
                continue
            # declared in meta so the gate never has to guess from salience
            interrupted = any(e.startswith("INTERRUPTED") for e in events)
            self.bus.put(Perception(
                PerceptionKind.GAME, self.name, self._snapshot(events),
                salience=0.95 if interrupted else 0.9,
                meta={"event": "interrupted"} if interrupted else {},
            ))

    def _joined(self) -> None:
        self.bus.put(Perception(PerceptionKind.GAME, self.name,
                                "You are in Minecraft now: the world is loaded around you.",
                                salience=0.4, meta={"first_state": True}))

    # --- the two silences worth breaking --------------------------------------

    def _nudge(self) -> Optional[Perception]:
        """Standing around, or deep in something long: the two times a word is asked of her."""
        if self.doing is not None:
            return self._working_nudge(self.doing)
        return self._idle_nudge()

    def _working_nudge(self, doing: Doing) -> Optional[Perception]:
        """A long action with something new in it since she last said a word.

        Measured on a real session: while one find_block ran for two minutes she
        was asked to comment five times on the same stale line, and filled every
        one of them with nothing. Time passing is not news; a change is.
        """
        every = float(self.skill_config.get("commentary_seconds", COMMENTARY_SECONDS))
        if every <= 0:
            return None
        now = time.time()
        if now - max(doing.started, self._last_commentary) < every:
            return None
        about = self._about(doing)
        if about == self._said_about:
            return None
        self._last_commentary = now
        self._said_about = about
        return self._word(asked=False)

    def _about(self, doing: Doing) -> Tuple:
        """What a word about this action would be about: the action, how far, what she carries."""
        carried = tuple(sorted(count_items(self._latest_state()).items()))
        return (id(doing), doing.progress, carried)

    def _idle_nudge(self) -> Optional[Perception]:
        """She is standing in a field. With a plan she has somewhere to start; without one, still a game."""
        every = float(self.skill_config.get("idle_nudge_seconds", IDLE_NUDGE_SECONDS))
        if every <= 0 or self.doing is not None:
            return None
        now = time.time()
        if now - max(self._idle_since, self._last_nudge) < every:
            return None
        self._last_nudge = now
        idle = round(now - self._idle_since)
        pending = self._pending_objectives()
        todo = ""
        if pending:
            todo = " Today's plan still has: " + "; ".join(
                f"#{o.id} {o.text}" for o in pending[:3]) + "."
        return Perception(
            PerceptionKind.GAME, self.name,
            f"You have been standing around in Minecraft doing nothing for {idle}s.{todo} "
            f"It is your game: do something.",
            salience=0.8,
            # declared: a nudge the gate filters out is a player left standing
            meta={"addressed": "idle-in-game", "event": "idle_in_game"},
        )

    def ask_for_a_word(self) -> bool:
        """The owner pressing "what are you doing?" on the dashboard."""
        if not self.active or self.client is None:
            return False
        self._last_commentary = time.time()
        self.bus.put(self._word(asked=True))
        return True

    def _word(self, asked: bool) -> Perception:
        """What she is up to, and a request for words rather than a decision."""
        doing = self.doing
        if doing is None:
            lines = ["You are standing still in Minecraft, not doing anything."]
        else:
            lines = [f"You have been at {doing.describe()} for "
                     f"{round(time.time() - doing.started)}s."]
            if doing.progress:
                lines.append(f"Last you heard: {doing.progress}.")
            carried = self._carried_line()
            if carried:
                lines.append(carried)
        lines.append("Someone watching just asked what you are up to. Tell them." if asked else
                     "Say something about it if there is something to say; staying quiet is fine too.")
        return Perception(
            PerceptionKind.GAME, self.name, " ".join(lines), salience=0.5,
            # declared: a question from the dashboard the gate drops is a button that does nothing
            meta={"addressed": "game-word", "event": "game_word"},
        )

    def _carried_line(self) -> str:
        carried = count_items(self._latest_state())
        if not carried:
            return ""
        top = sorted(carried.items(), key=lambda kv: -kv[1])[:6]
        return "You are carrying " + ", ".join(f"{n} {k}" for k, n in top) + "."

    def _pending_objectives(self) -> list:
        plan = getattr(getattr(self.context, "memory", None), "plan", None)
        if plan is None:
            return []
        try:
            return plan.open()
        except Exception as e:
            logger.error(f"Could not read the stream plan: {e}")
            return []

    # --- the senses -------------------------------------------------------------

    def _on_mod_event(self, kind: str, data: dict) -> None:
        """Typed packets from the mod. Called on the event loop thread."""
        if kind == "chat":
            self._on_chat(data)
        elif kind == "player_event":
            self._on_player_event(data)
        elif kind == "combat":
            self._on_combat(data)
        elif kind == "death_event":
            self._on_death(data)
        elif kind == "auto_action":
            self._on_auto_action(data)
        elif kind == "reflex":
            self._on_reflex(data)
        elif kind == "progress":
            self._on_progress(data)
        elif kind == "activity":
            self._on_activity(data)

    def _on_chat(self, data: dict) -> None:
        """Someone talked in game.

        The whole social stack (roster, person cards, attention) is keyed on
        `Author`, so building one here is what switches it on in Minecraft.
        """
        text = str(data.get("text", "")).strip()
        if not text:
            return

        author_data = data.get("author") or {}
        uuid = str(author_data.get("uuid", "") or "")
        name = str(author_data.get("name", "") or "")

        if data.get("kind") == "system" or not uuid:
            # server lines: joins, deaths, /me. Nobody said them TO her.
            self.bus.put(Perception(
                PerceptionKind.CHAT, "chat:mc", f"(server) {text}", salience=0.3,
                meta={"conversation_key": "stage", "system": True},
            ))
            return

        if uuid == self._self_uuid():
            return  # her own message coming back

        whisper = self._is_whisper(text, name)
        distance = data.get("distance")
        self.bus.put(Perception(
            kind=PerceptionKind.CHAT,
            surface="chat:mc",
            content=f"[{name}] (in game): {text}",
            salience=0.9 if whisper else 0.7,
            meta={
                "uuid": uuid, "whisper": whisper,
                "distance": float(distance) if distance not in (None, -1) else None,
                # the room she is standing in: she answers out loud AND in chat
                "conversation_key": "stage",
            },
            author=Author(platform="minecraft", native_id=uuid, display_name=name or uuid[:8]),
        ))

    def _on_player_event(self, data: dict) -> None:
        player = data.get("player") or {}
        uuid = str(player.get("uuid", "") or "")
        name = str(player.get("name", "") or "") or uuid[:8]
        if not uuid or uuid == self._self_uuid():
            return
        event = data.get("event", "join")
        self.bus.put(Perception(
            PerceptionKind.CHAT, "chat:mc",
            f"{name} {'joined' if event == 'join' else 'left'} the server.",
            salience=0.5,
            meta={"uuid": uuid, "event": f"player_{event}", "conversation_key": "stage"},
            author=Author(platform="minecraft", native_id=uuid, display_name=name),
        ))

    def _on_combat(self, data: dict) -> None:
        """Being hit. By a person it is a social event, not a number going down."""
        source = str(data.get("source", "environment"))
        by = data.get("by") or {}
        health = data.get("health")
        damage = data.get("damage", 0)

        if source == "player":
            name = str(by.get("name", "someone"))
            content = f"{name} just hit you ({damage:g} damage, {health:g} health left)."
            author = Author(platform="minecraft", native_id=str(by.get("uuid", name)),
                            display_name=name)
        elif source == "mob":
            content = (f"A {by.get('name', 'mob')} is hitting you "
                       f"({damage:g} damage, {health:g} health left).")
            author = None
        else:
            content = f"You took {damage:g} damage ({health:g} health left)."
            author = None

        self.bus.put(Perception(
            PerceptionKind.GAME, "game:mc", content,
            salience=0.95 if source == "player" else 0.8,
            meta={"event": "hurt", "source": source, "health": health},
            author=author,
        ))

    def _on_death(self, data: dict) -> None:
        details = data.get("details") or {}
        pos = details.get("death_pos") or {}
        lost = details.get("lost_items") or []
        self._remember_death(pos, str(details.get("dimension") or "minecraft:overworld"))

        where = ""
        if pos.get("x") is not None:
            where = f" at ({pos.get('x', 0):.0f}, {pos.get('y', 0):.0f}, {pos.get('z', 0):.0f})"
        lines = [f"YOU DIED{where}. Cause: {details.get('cause', 'unknown')}."]
        if lost:
            lines.append("You dropped: " + ", ".join(str(i) for i in lost[:10]))
        lines.append("You respawned.")

        self.bus.put(Perception(
            PerceptionKind.GAME, "game:mc", "\n".join(lines), salience=1.0,
            meta={"event": "death", "cause": details.get("cause", "unknown")},
        ))

    def _on_auto_action(self, data: dict) -> None:
        event = data.get("event") or {}
        self.bus.put(Perception(
            PerceptionKind.GAME, "game:mc",
            f"You are fighting back against {event.get('attacker', 'something')}.",
            salience=0.85, meta={"event": "hurt", "source": "mob"},
        ))

    def _on_reflex(self, data: dict) -> None:
        """Something the game had her do on its own: eat, fight back, get unstuck.

        A fight and a death are hers to react to now; the rest she only needs to
        know about the next time she looks, so it waits in her frame.
        """
        reflex = str(data.get("reflex") or "reflex")
        message = " ".join(str(data.get("message") or "").split())
        if not message:
            return
        now = time.time()
        self._reflexes = [(at, line) for at, line in self._reflexes
                          if now - at < REFLEX_MEMORY_SECONDS][-7:]
        self._reflexes.append((now, _clip(message)))
        if reflex in _LOUD_REFLEXES and data.get("event") == "started":
            self.bus.put(Perception(
                PerceptionKind.GAME, self.name, f"On reflex: {message}.", salience=0.85,
                meta={"event": "reflex", "reflex": reflex},
            ))

    def _on_progress(self, data: dict) -> None:
        """A long action saying how far it has got (a build, cell by cell)."""
        message = " ".join(str(data.get("message") or "").split())
        if self.doing is not None and message:
            self.doing.progress = _clip(message)

    def _on_activity(self, data: dict) -> None:
        """Something answered when it started, following someone, has ended on its own."""
        if data.get("result") == "INTERRUPTED":
            return  # she replaced it or stopped it: she knows
        action = str(data.get("action") or "activity").replace("_", " ")
        message = " ".join(str(data.get("message") or "").split())
        if not message:
            return
        self.bus.put(Perception(
            PerceptionKind.GAME, self.name, f"You stopped {action}: {message}.", salience=0.6,
            meta={"event": "activity_ended"},
        ))

    def _is_whisper(self, text: str, name: str) -> bool:
        """Vanilla renders a whisper as "Marco whispers to you: ..."."""
        low = text.lower()
        return "whispers to you" in low or low.startswith(f"{name.lower()} whispers")

    def _self_uuid(self) -> str:
        player = (self._latest_state() or {}).get("player") or {}
        return str(player.get("uuid", "") or "")

    def _snapshot(self, events: Optional[List[str]] = None) -> str:
        parts = []
        if events:
            parts.append("EVENTS:\n" + "\n".join(events))
        parts.append("GAME STATE:\n" + render_state(self._latest_state()))
        return "\n\n".join(parts)

    def _latest_state(self) -> dict:
        return self.client.latest_state if self.client is not None else {}

    def _places_line(self) -> str:
        if self.places is None:
            return ""
        state = self._latest_state() or {}
        pos = (state.get("player") or {}).get("position") or {}
        here = (float(pos["x"]), float(pos["y"]), float(pos["z"])) if {"x", "y", "z"} <= set(pos) else None
        dimension = str((state.get("world") or {}).get("dimension") or "minecraft:overworld")
        return self.places.render(server_of(state), here, dimension)

    def _remember_death(self, pos: dict, dimension: str) -> None:
        """Where she died, kept as last_death: what she dropped is lying there."""
        if self.places is None or not {"x", "y", "z"} <= set(pos):
            return
        self.places.remember(server_of(self._latest_state()), DEATH, float(pos["x"]), float(pos["y"]),
                             float(pos["z"]), dimension=dimension)
        task = asyncio.get_running_loop().create_task(self.places.save())
        # a task nobody holds can be collected before it runs
        self._saving.add(task)
        task.add_done_callback(self._saving.discard)

    @property
    def context_section(self) -> Optional[str]:
        return self._rules or None

    # --- her hands ---------------------------------------------------------------

    def tools(self) -> List[Tool]:
        if not self.active or self.client is None or self._registry is None:
            return []
        return [self._tracked(t) if t.long_running else t for t in self._registry.tools()]

    def _tracked(self, tool: Tool) -> Tool:
        """The same tool, with what she is in the middle of kept for her frame."""
        async def handler(**kwargs):
            doing = Doing(tool.name, dict(kwargs))
            self.doing = doing
            # what it is like when she starts is the baseline a word has to beat
            self._said_about = self._about(doing)
            try:
                result = tool.handler(**kwargs)
                if asyncio.iscoroutine(result):
                    result = await result
                self._last = f"{tool.name}: {_clip(str(result))}"
                return result
            finally:
                # a newer action may already hold her hands: only this one's own end clears it
                if self.doing is doing:
                    self.doing = None
                    self._idle_since = time.time()
        return Tool(tool.name, tool.description, tool.parameters, handler,
                    long_running=True, surface=tool.surface or self.name, reaches=tool.reaches)

    def left_undone(self, batch, acted) -> Optional[str]:
        """A turn about the game that is ending with nothing in her hands.

        Every other world is answered by a reply. This one is answered by
        playing: without this the turn ends on the line where she says she will.
        """
        if not self.active or self.client is None or self._registry is None:
            return None
        if self.doing is not None:
            return None
        if not any(getattr(p, "surface", "") in _GAME_SURFACES for p in batch):
            return None
        hands = {t.name for t in self._registry.tools() if t.long_running}
        for call in acted:
            if call.get("tool") in hands and not str(call.get("result", "")).startswith(
                    ("ERROR", "FAILED")):
                return None
        return _EMPTY_HANDS

    async def stop_doing(self) -> Optional[str]:
        """The dashboard putting her hands down. None when she is not in the game."""
        if self.client is None or not self.active:
            return None
        return await self.client.execute("stop_moving", {})

    def snapshot(self) -> Dict[str, Any]:
        """What she is doing in the game, for the dashboard."""
        connected = bool(self.client is not None and self.client.is_connected)
        doing = self.doing
        return {
            "active": bool(self.active),
            "connected": connected,
            "mod_version": self.client.mod_version if self.client else "",
            "doing": doing.describe() if doing else "",
            "elapsed": round(time.time() - doing.started, 1) if doing else 0.0,
            "progress": doing.progress if doing else "",
            "last": self._last,
        }

    def live_state(self) -> Optional[str]:
        """Where she is and what her hands are on, in every frame she thinks in."""
        if not self.active:
            return None
        lines = []
        doing = self.doing
        if doing is not None:
            lines.append(f"- you are doing: {doing.describe()}, "
                         f"{round(time.time() - doing.started)}s so far")
            if doing.progress:
                lines.append(f"  last you heard: {doing.progress}")
        else:
            lines.append("- you are not doing anything right now")
        now = time.time()
        recent = [line for at, line in self._reflexes if now - at < REFLEX_MEMORY_SECONDS]
        if recent:
            lines.append("- on reflex, just now: " + "; ".join(recent))
        state = render_state(self._latest_state())
        if state:
            lines.append(state)
        places = self._places_line()
        if places:
            lines.append(f"- places you remember: {places}")
        return "IN MINECRAFT (right now):\n" + "\n".join(lines)


def _clip(text: str, limit: int = LINE_LIMIT) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
