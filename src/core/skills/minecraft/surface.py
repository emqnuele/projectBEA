import asyncio
import time
from typing import List, Optional

from src.core.agent.tools import Tool
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.skills.minecraft.agent import GameAgent
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.state import render_state
from src.core.skills.minecraft.tools import build_minecraft_tools
from src.utils.logger import get_logger
from src.utils.prompts import load_text

logger = get_logger("bea.skills.minecraft")

# how long the body may stand still with unfinished objectives before her own
# body tells her about it. 0 turns the nudge off.
IDLE_NUDGE_SECONDS = 90.0


class MinecraftSurface(Skill):
    """The game body: perceives game events and state, exposes in-game actions.

    While active it injects the survival rules and arms the minecraft tools, so
    Bea only knows how to play when actually connected.
    """

    name = "game:mc"
    skill_name = "minecraft"

    def initialize(self) -> None:
        cfg = self.skill_config
        persona = persona_of(self.config)
        self._rules = persona.fill(
            load_text(cfg.get("system_prompt_path", "data/prompts/minecraft.md")))
        # recipe trees belong to the body, not in her head
        self._body_rules = persona.fill(
            load_text(cfg.get("body_prompt_path", "data/prompts/minecraft_body.md")))
        self.client: Optional[MinecraftClient] = None
        self.notebook = Notebook()
        self._registry = None
        self.agent: Optional[GameAgent] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._idle_since: float = 0.0
        self._last_nudge: float = 0.0

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("minecraft", {})

    async def start(self) -> None:
        if not self.skill_config.get("enabled", False):
            logger.info("MinecraftSurface inactive (minecraft skill disabled).")
            return
        url = self.skill_config.get("server_url", "ws://127.0.0.1:8080")
        loop = asyncio.get_running_loop()
        self.client = MinecraftClient(url, loop, on_event=self._on_mod_event)
        self._registry = build_minecraft_tools(self.client, self.notebook)
        self.agent = GameAgent(
            llm=self._body_model(),
            registry=self._registry,
            notebook=self.notebook,
            state_getter=self._latest_state,
            rules=self._body_rules,
            on_milestone=self._emit_milestone,
        )
        self.client.connect()
        self.active = True
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
        logger.info("MinecraftSurface stopped.")

    async def _perceive_loop(self) -> None:
        """Streams game events onto the bus.

        The periodic snapshot is marked `noise`: the state is always in
        live_state, so only real events (interrupts, deaths) wake the mind.
        """
        if self.client is None:
            return
        await self.client.wait_until_ready()
        self.bus.put(Perception(PerceptionKind.GAME, self.name,
                                "You just woke up inside Minecraft.", salience=0.4,
                                meta={"first_state": True}))
        while self.active and self.client is not None:
            await self.client.wait_for_event_or_timeout(10.0)
            if self.client is None:
                break
            events = self.client.drain_events()
            if not events:
                nudge = self._idle_nudge()
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

    # --- standing still with a plan ------------------------------------------

    def _idle_nudge(self) -> Optional[Perception]:
        """Her body reporting that it is standing around with work outstanding.

        The game heartbeat is deliberately noise, which is also why nothing ever
        pushed her to start playing: she only reacted. This is the one game
        perception that wakes her, and it only exists while the owner's plan has
        something open and the body has nothing to do.
        """
        if self.agent is None or self.agent.busy:
            self._idle_since = 0.0
            return None

        pending = self._pending_objectives()
        if not pending:
            self._idle_since = 0.0
            return None

        every = float(self.skill_config.get("idle_nudge_seconds", IDLE_NUDGE_SECONDS))
        if every <= 0:
            return None

        now = time.time()
        if not self._idle_since:
            self._idle_since = now
        waited = now - max(self._idle_since, self._last_nudge)
        if waited < every:
            return None

        self._last_nudge = now
        todo = "; ".join(f"#{o.id} {o.text}" for o in pending[:3])
        return Perception(
            PerceptionKind.GAME, self.name,
            f"Your body is standing still in Minecraft, doing nothing, and today's "
            f"plan still has: {todo}. Give it something to do with play_minecraft, "
            f"or say why you're not.",
            salience=0.8,
            # declared: a nudge that the gate filters out is a nudge that never
            # happens, and she would go back to waiting to be spoken to
            meta={"addressed": "idle-body", "event": "idle_body"},
        )

    def _pending_objectives(self) -> list:
        plan = getattr(getattr(self.context, "memory", None), "plan", None)
        if plan is None:
            return []
        try:
            return plan.open()
        except Exception as e:
            logger.error(f"Could not read the stream plan: {e}")
            return []

    # --- the social senses --------------------------------------------------

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
            f"Your body defended itself: fighting {event.get('attacker', 'something')}.",
            salience=0.85, meta={"event": "hurt", "source": "mob"},
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

    @property
    def context_section(self) -> Optional[str]:
        return self._rules or None

    def _body_model(self):
        model_for = getattr(self.context, "model_for", None)
        return model_for("background") if model_for else getattr(self.context, "llm", None)

    def _emit_milestone(self, text: str) -> None:
        """Something worth interrupting her for; the rest stays in the body."""
        self.bus.put(Perception(
            PerceptionKind.GAME, self.name, text, salience=0.6,
            meta={"event": "milestone"},
        ))

    # --- what the MIND can do (seven tools, not twenty-five) ----------------

    def tools(self) -> List[Tool]:
        if not self.active or self.client is None:
            return []

        def body(action: str, rename: Optional[dict] = None):
            """Binds a mod action, renaming arguments where the mod calls them
            something else (LookSkill takes `player`, not `name`)."""
            rename = rename or {}

            async def handler(**kwargs):
                args = {rename.get(k, k): v for k, v in kwargs.items()}
                return await self.client.execute(action, args)
            return handler

        return [
            Tool(
                "play_minecraft",
                "Give your body something to achieve in the game (\"get a stone pickaxe\", "
                "\"build a shelter before dark\", \"find iron\"). It goes and does it while "
                "you carry on doing whatever else you're doing, and tells you when something "
                "worth knowing happens. One goal at a time — a new one replaces the old.",
                {"type": "object", "properties": {
                    "goal": {"type": "string", "description": "what you want done, in plain words"}},
                 "required": ["goal"]},
                self._tool_play, long_running=True, surface=self.name,
            ),
            Tool(
                "mc_chat",
                "TYPE a message in the game chat. The players there read it — a different "
                "audience from your voice. Use it to answer them; use `speak` to comment "
                "for your stream. Both in the same turn is usually right.",
                {"type": "object", "properties": {"message": {"type": "string"}},
                 "required": ["message"]},
                self._tool_chat,
            ),
            Tool(
                "mc_stop",
                "Put your body down: it stops whatever it was doing and stands still.",
                {"type": "object", "properties": {}, "required": []},
                self._tool_stop,
            ),
            Tool(
                "mc_goto_player",
                "Walk over to a player and stop next to them. They move; you keep up.",
                {"type": "object", "properties": {"name": {"type": "string"}},
                 "required": ["name"]},
                body("goto_player"), long_running=True, surface=self.name,
            ),
            Tool(
                "mc_follow_player",
                "Stay with a player, a few blocks behind, until you stop. Gives up on its "
                "own if you lose them.",
                {"type": "object", "properties": {"name": {"type": "string"}},
                 "required": ["name"]},
                body("follow_player"), long_running=True, surface=self.name,
            ),
            Tool(
                "mc_look_at_player",
                "Turn and look at a player. Staring at someone is communication — use it "
                "when you want them to know you noticed.",
                {"type": "object", "properties": {"name": {"type": "string"}},
                 "required": ["name"]},
                body("look_at", {"name": "player"}), long_running=True, surface=self.name,
            ),
            Tool(
                "mc_give_item",
                "Take something to a player: you walk over and drop it at their feet "
                "(vanilla has no way to hand something over directly). Omit `count` to give "
                "them everything you have of it.",
                {"type": "object", "properties": {
                    "name": {"type": "string"}, "item": {"type": "string"},
                    "count": {"type": "integer"}},
                 "required": ["name", "item"]},
                body("give_item"), long_running=True, surface=self.name,
            ),
        ]

    async def _tool_play(self, goal: str) -> str:
        if self.agent is None:
            return "FAILED: your body isn't connected."
        return await self.agent.pursue(goal)

    async def _tool_chat(self, message: str) -> str:
        if self.client is None:
            return "FAILED: your body isn't connected."
        await self.client.execute("chat", {"message": message}, instant=True)
        return "Typed it in game chat."

    async def _tool_stop(self) -> str:
        if self.client is None:
            return "FAILED: your body isn't connected."
        await self.client.execute("stop_moving", {}, instant=True)
        return "Body stopped."


    def live_state(self) -> Optional[str]:
        if not self.active:
            return None
        parts = []
        # where she is, always true: not an event that should make her think
        body = render_state(self._latest_state())
        doing = self.agent.describe() if self.agent else ""
        if doing:
            body = f"- {doing}\n{body}" if body else f"- {doing}"
        if body:
            parts.append("YOUR BODY IN MINECRAFT (right now):\n" + body)
        return "\n\n".join(parts)
