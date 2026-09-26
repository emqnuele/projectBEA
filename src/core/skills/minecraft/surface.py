import asyncio
import time
from typing import Any, Dict, List, Optional

from src.core.agent.registry import MINECRAFT
from src.core.agent.tools import Tool
from src.core.perception.types import Author, Perception, PerceptionKind
from src.core.persona import persona_of
from src.core.skills.base import Skill
from src.core.skills.minecraft.agent import STEPS_PER_GOAL, TICK_SECONDS, GameAgent
from src.core.skills.minecraft.client import MinecraftClient
from src.core.skills.minecraft.context import KEEP_ROUNDS
from src.core.skills.minecraft.goal import ABANDONED, DONE, Goal
from src.core.skills.minecraft.notebook import Notebook
from src.core.skills.minecraft.places import DEATH, Places, server_of
from src.core.skills.minecraft.state import render_state
from src.core.skills.minecraft.tools import build_minecraft_tools
from src.utils.logger import get_logger
from src.utils.prompts import prompt_for

logger = get_logger("bea.skills.minecraft")

# how long the body may stand still with unfinished objectives before her own
# body tells her about it. 0 turns the nudge off.
IDLE_NUDGE_SECONDS = 90.0

# how often she is asked to say something while the body is busy. Milestones
# are minutes apart, and a streamer who goes quiet for minutes is the whole
# problem this exists to solve. 0 turns it off.
COMMENTARY_SECONDS = 20.0

# the shortest gap between two milestones reaching her. The body can finish
# things faster than anyone can react to them, and a mind interrupted twice a
# second is not a mind that is playing, it is one being shouted at
MILESTONE_GAP = 8.0


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
            prompt_for(cfg, "system_prompt", "data/prompts/minecraft.md"))
        # recipe trees belong to the body, not in her head
        self._body_rules = persona.fill(
            prompt_for(cfg, "body_prompt", "data/prompts/minecraft_body.md"))
        self.client: Optional[MinecraftClient] = None
        self.notebook = Notebook()
        self.places: Optional[Places] = None
        self._saving: set = set()
        # her own mc_follow_player calls still going: each holds the body's goal until it ends
        self._following = 0
        self._registry = None
        self.agent: Optional[GameAgent] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._idle_since: float = 0.0
        self._last_nudge: float = 0.0
        self._last_commentary: float = 0.0
        self._last_milestone: str = ""
        self._last_milestone_at: float = 0.0

    @property
    def skill_config(self) -> dict:
        return self.config.skills.get("minecraft", {})

    async def start(self) -> None:
        if not self.enabled:
            logger.info("MinecraftSurface inactive (minecraft skill disabled).")
            return
        url = self.skill_config.get("server_url", "ws://127.0.0.1:8080")
        loop = asyncio.get_running_loop()
        cfg = self.skill_config
        self.client = MinecraftClient(url, loop, on_event=self._on_mod_event)
        self.places = await asyncio.to_thread(Places)
        self._registry = build_minecraft_tools(
            self.client, self.notebook, build_scripts=bool(cfg.get("build_scripts", True)),
            places=self.places)
        self.agent = GameAgent(
            llm=self._body_model(),
            registry=self._registry,
            notebook=self.notebook,
            state_getter=self._latest_state,
            rules=self._body_rules,
            on_milestone=self._emit_milestone,
            on_goal_closed=self._on_goal_closed,
            steps_per_goal=int(cfg.get("steps_per_goal", STEPS_PER_GOAL)),
            tick_seconds=float(cfg.get("tick_seconds", TICK_SECONDS)),
            keep_rounds=int(cfg.get("body_context_rounds", KEEP_ROUNDS)),
            places=self._places_line,
        )
        self.client.connect()
        self.active = True
        # the body's loop lives as long as the skill does: it idles for free
        # until she gives it something, and never needs restarting after
        self.agent.start()
        self._poll_task = asyncio.create_task(self._perceive_loop())
        logger.info("MinecraftSurface started.")

    async def stop(self) -> None:
        self.active = False
        # the body first: a loop that outlives the socket it acts through
        # spends a minute timing out on every move it tries to make
        if self.agent:
            await self.agent.stop()
            self.agent = None
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

    # --- her body reporting in -----------------------------------------------

    def _nudge(self) -> Optional[Perception]:
        """The game heartbeat is noise, so nothing in the world ever makes her
        speak on its own. These two perceptions do, in the two situations where
        a silent streamer is the wrong answer: the body working unwatched, and
        the body standing around with the plan unfinished.
        """
        agent = self.agent
        if agent is None:
            return None
        if agent.busy:
            # the idle clock only starts once the body actually stops
            self._idle_since = 0.0
            return self._working_nudge(agent)
        return self._idle_nudge()

    def _working_nudge(self, agent: GameAgent) -> Optional[Perception]:
        """The body is mid-goal, and only milestones were reaching her.

        Between two of those, minutes of nothing: she stands there mining while
        the people watching hear silence.
        """
        every = float(self.skill_config.get("commentary_seconds", COMMENTARY_SECONDS))
        if every <= 0:
            return None

        now = time.time()
        goal = agent.goal
        # the turn that set the goal already said something: start the clock there
        since = max(goal.set_at if goal else 0.0, self._last_commentary)
        if now - since < every:
            return None
        self._last_commentary = now
        return self._commentary(agent)

    def ask_for_a_word(self) -> bool:
        """The owner pressing "what are you doing?" on the dashboard.

        The same perception the clock produces, off the clock, so what the
        button does and what she does on her own can never drift apart. It
        works with the body standing still too: that is a fair question to ask
        of someone standing still.
        """
        agent = self.agent
        if not self.active or agent is None:
            return False
        self._last_commentary = time.time()
        self.bus.put(self._commentary(agent, asked=True))
        return True

    def _commentary(self, agent: GameAgent, asked: bool = False) -> Perception:
        """What the body is doing, and a request for words rather than a decision."""
        working = agent.busy
        lines = [f"Your body is {agent.describe()}." if working
                 else "Your body is standing still in Minecraft, with nothing to do."]
        if working and agent.last_thought:
            lines.append(f'It is thinking: "{agent.last_thought}"')
        lines.append("Someone watching just asked what you are up to. Tell them."
                     if asked else
                     "Say what is going on — out loud for the stream, in game chat, or both.")
        if working:
            # a second goal replaces the running one: she must not answer with one
            lines.append("Don't hand it a new goal: it is already working.")
        else:
            lines.append("If you want it doing something, that is what play_minecraft is for.")
        return Perception(
            PerceptionKind.GAME, self.name, " ".join(lines), salience=0.5,
            # declared: commentary the gate drops is a streamer who goes quiet
            meta={"addressed": "body-commentary", "event": "body_commentary"},
        )

    def _idle_nudge(self) -> Optional[Perception]:
        """Her body reporting that it is standing around with work outstanding.

        It only exists while the owner's plan has something open: with an empty
        plan she has nothing she is supposed to be doing, and inventing one
        would be noise.
        """
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
        elif kind == "reflex":
            self._on_reflex(data)
        elif kind == "progress":
            self._on_progress(data)
        elif kind == "activity":
            self._on_activity(data)
        elif kind == "connection_lost":
            self._on_connection_lost()

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
            f"Your body defended itself: fighting {event.get('attacker', 'something')}.",
            salience=0.85, meta={"event": "hurt", "source": "mob"},
        ))

    def _on_reflex(self, data: dict) -> None:
        """The body did something nobody asked for: eat, fight, clutch, get unstuck.

        The body reads it before its next move, so an interruption is never a
        mystery. Fighting and dying are also hers to hear about.
        """
        reflex = str(data.get("reflex") or "reflex")
        message = " ".join(str(data.get("message") or "").split())
        if not message:
            return
        agent = self.agent
        if agent is not None:
            agent.note_reflex(f"{reflex}: {message}")
        if reflex in ("defend", "respawn") and data.get("event") == "started":
            self._emit_milestone(f"your body, on its own: {message}")

    def _on_progress(self, data: dict) -> None:
        """A long action saying how far it has got: what the body is thinking now.

        Commentary reads the body's latest thought, so a build narrates itself
        without a word of it becoming an interruption.
        """
        agent = self.agent
        message = " ".join(str(data.get("message") or "").split())
        if agent is not None and message:
            agent.note_progress(message)

    def _on_activity(self, data: dict) -> None:
        """Something answered when it started, following someone, has ended.

        The body hears it before its next move. When it was her own
        mc_follow_player, the goal it had put down is picked back up, and she
        hears it too unless it was simply replaced or stopped (she knows that).
        """
        action = str(data.get("action") or "activity").replace("_", " ")
        message = " ".join(str(data.get("message") or "").split())
        agent = self.agent
        if agent is not None and message:
            agent.note_reflex(f"{action} ended: {message}")
        if data.get("action") == "follow_player" and self._following > 0:
            self._following -= 1
            if agent is not None:
                agent.give_back(f"she had you following someone; {message}")
            if data.get("result") != "INTERRUPTED" and message:
                self._emit_milestone(f"your body stopped following: {message}")

    def _on_connection_lost(self) -> None:
        """The game went away mid-follow: no end of it will ever arrive, so the goal comes back now."""
        while self._following > 0:
            self._following -= 1
            if self.agent is not None:
                self.agent.give_back("the connection to the game dropped")

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

    def _body_model(self):
        """What the body thinks with.

        Its own pool when one is configured, and otherwise hers: playing well
        is not clerical work, and a body on the cheap background model spent
        its steps failing to work out that a pickaxe needs sticks.
        """
        model_for = getattr(self.context, "model_for", None)
        return model_for(MINECRAFT) if model_for else getattr(self.context, "llm", None)

    def _emit_milestone(self, text: str) -> None:
        """Something worth interrupting her for; the rest stays in the body.

        The same line twice is never news, and two in the same breath is the
        body talking over itself. A death does not come through here — it has
        its own perception at full salience — so nothing that matters is lost
        to the gap.
        """
        now = time.time()
        if text == self._last_milestone or now - self._last_milestone_at < MILESTONE_GAP:
            logger.debug(f"milestone held back: {text}")
            return
        self._last_milestone, self._last_milestone_at = text, now
        self.bus.put(Perception(
            PerceptionKind.GAME, self.name, text, salience=0.6,
            meta={"event": "milestone"},
        ))

    def _on_goal_closed(self, goal: Goal) -> None:
        """The body reached the end of what she gave it, one way or the other.

        She replaced it herself, so she already knows — anything else is news,
        and being stuck is news she has to answer: nothing else will move the
        body until she does.
        """
        if goal.status == ABANDONED:
            return
        done = goal.status == DONE
        if done:
            content = (f"Your body finished what you gave it — {goal.text}: {goal.outcome}. "
                       f"Say something about it, and give it the next thing if there is one.")
        else:
            content = (f"Your body got stuck on {goal.text}: {goal.outcome}. It has stopped "
                       f"and it is waiting on you. Work out what it does instead.")
        self.bus.put(Perception(
            PerceptionKind.GAME, self.name, content,
            salience=0.75 if done else 0.9,
            meta={"addressed": "body-goal",
                  "event": "goal_done" if done else "goal_stuck"},
        ))

    def body_snapshot(self) -> Dict[str, Any]:
        """What her body is up to, for the dashboard."""
        connected = bool(self.client is not None and self.client.is_connected)
        base: Dict[str, Any] = {
            "active": bool(self.active),
            "connected": connected,
            "mod_version": self.client.mod_version if self.client else "",
        }
        base.update(self.agent.snapshot() if self.agent else
                    {"goal": "", "status": "off", "steps": 0, "steps_budget": 0,
                     "elapsed": 0.0, "outcome": "", "thought": "", "notebook": ""})
        return base

    # --- what the MIND can do (seven tools, not twenty-five) ----------------

    def tools(self) -> List[Tool]:
        if not self.active or self.client is None:
            return []

        # bound now rather than read when a tool fires: she can be disconnected
        # from the world between being handed a tool and reaching for it
        client = self.client

        def body(action: str, rename: Optional[dict] = None):
            """Binds a mod action, renaming arguments where the mod calls them
            something else (LookSkill takes `player`, not `name`).

            The goal is put down for the duration and picked back up after: one
            body, and two things wanting it at once is two sets of movement
            orders arriving at the same legs. An action the mod runs beside the
            current one (a glance) leaves the goal alone.
            """
            rename = rename or {}
            why = action.replace("_", " ")

            async def handler(**kwargs):
                args = {rename.get(k, k): v for k, v in kwargs.items()}
                if action in client.concurrent:
                    return await client.execute(action, args)
                agent = self.agent
                if agent is not None:
                    agent.borrow()
                held = False
                try:
                    answer = await client.execute(action, args)
                    # following goes on after its answer: the goal waits until it ends (_on_activity)
                    held = action == "follow_player" and answer.startswith("SUCCESS")
                    if held:
                        self._following += 1
                    return answer
                finally:
                    if agent is not None and not held:
                        agent.give_back(f"she had you {why}")
            return handler

        return [
            Tool(
                "play_minecraft",
                "Point your body at something (\"get a stone pickaxe\", \"build a shelter "
                "before dark\", \"find iron\"). It works at it without stopping while you "
                "carry on doing whatever else you're doing, and tells you when it finishes, "
                "gets stuck, or something worth knowing happens. One goal at a time — a new "
                "one replaces the old one immediately.",
                {"type": "object", "properties": {
                    "goal": {"type": "string", "description": "what you want done, in plain words"},
                    "have": {
                        "type": "object",
                        "description": (
                            "Optional. What it should be holding when it is done, like "
                            "{\"iron_ingot\": 5} or {\"log\": 4}. Your body cannot call a goal "
                            "finished until the game agrees it has them, so use it whenever "
                            "the goal is about getting something."
                        ),
                        "additionalProperties": {"type": "integer"},
                    }},
                 "required": ["goal"]},
                self._tool_play,
            ),
            Tool(
                "mc_chat",
                "TYPE a message in the game chat. The players there read it — a different "
                "audience from your voice. Use it to answer them; use `speak` to comment "
                "for your stream. Both in the same turn is usually right.",
                {"type": "object", "properties": {"message": {"type": "string"}},
                 "required": ["message"]},
                self._tool_chat,
                reaches=True,
            ),
            Tool(
                "mc_stop",
                "Put your body down: it drops the goal it was working on and stands still "
                "until you give it another one.",
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

    async def _tool_play(self, goal: str, have: Optional[Dict[str, Any]] = None) -> str:
        """Hands the body a direction and comes straight back.

        It used to wait here until the whole goal was over, which is why a tool
        that claimed not to block her spent twenty minutes doing exactly that.
        """
        if self.agent is None:
            return "FAILED: your body isn't connected."
        return self.agent.set_goal(goal, requires=have)

    async def _tool_chat(self, message: str) -> str:
        if self.client is None:
            return "FAILED: your body isn't connected."
        # the mod types it beside whatever the body is doing; it no longer stops it
        said = await self.client.execute("chat", {"message": message})
        if said.startswith(("SUCCESS", "SENT")):
            return "Typed it in game chat."
        return said

    async def _tool_stop(self) -> str:
        if self.client is None or self.agent is None:
            return "FAILED: your body isn't connected."
        said = self.agent.clear_goal("she told it to stop")
        await self.client.execute("stop_moving", {})
        return said


    def live_state(self) -> Optional[str]:
        """Where she is and what her body is on, in every frame she thinks in.

        This is the difference between a mind that can answer "what are you
        doing" and one that has to be told. It is deliberately three lines and
        a state dump: the body's reasoning stays in the body.
        """
        if not self.active:
            return None
        agent = self.agent
        lines = []
        doing = agent.describe() if agent else ""
        if doing:
            lines.append(f"- {doing}")
            if agent is not None and agent.last_thought:
                lines.append(f'- it is thinking: "{agent.last_thought}"')
        else:
            lines.append("- no goal: your body is standing still, waiting on you")
        state = render_state(self._latest_state())
        if state:
            lines.append(state)
        return "YOUR BODY IN MINECRAFT (right now):\n" + "\n".join(lines)
