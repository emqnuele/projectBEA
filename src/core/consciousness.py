import asyncio
import datetime
import time
from typing import Any, Dict, List, Optional

from src.core.agent.messages import assistant_to_message, tool_result_message
from src.core.agent.tools import Tool
from src.core.agent.types import ToolCall, Usage
from src.core.events import EventCategory
from src.core.mind.correlation import CorrelationRegistry
from src.core.mind.routing import route
from src.core.mind.tools import MindTools
from src.core.perception.types import Perception, PerceptionKind
from src.utils.logger import get_logger
from src.utils.prompts import compose
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.consciousness")


class Consciousness:
    """The single, always-on mind.

    One context, one loop. It drains perceptions from every surface, folds new
    ones in mid-burst (steering), reasons, and acts through tools. Speaking is
    non-blocking and body actions run async (single-slot), so Bea can talk and
    play at the same time — and decide for herself whether a new input is worth
    interrupting what she's doing.
    """

    # output tools that end a turn: no follow-up llm call needed after them
    _TERMINAL_TOOLS = {"speak", "stay_silent"}

    def __init__(self, *, config, llm, bus, expression, surfaces, history_manager,
                 event_manager, soul_getter, operating_getter, attention=None,
                 conversations=None):
        self.config = config
        self.llm = llm
        self.bus = bus
        self.expression = expression
        self.surfaces = surfaces
        self.history = history_manager
        self.events = event_manager
        self.attention = attention
        self.conversations = conversations
        self._get_soul = soul_getter
        self._get_operating = operating_getter

        cc = config.consciousness
        self.idle_after = cc.get("idle_after", 30.0)
        self.window = cc.get("window", 0.3)
        self.burst_steps = cc.get("burst_steps", 6)
        self.history_limit = cc.get("history_limit", 30)
        self.correlation_timeout = cc.get("correlation_timeout", 30.0)

        self.context: List[Dict[str, Any]] = []
        self.total_tokens = 0
        self.total_calls = 0
        self.alive = False
        self.sleeping = False
        self._loop_task: Optional[asyncio.Task] = None
        self._body_task: Optional[asyncio.Task] = None

        # HTTP callers waiting on a reply. Its own concern: a request lifecycle,
        # not part of thinking.
        self.correlations = CorrelationRegistry()

        # rebuilt only when a capability is toggled, not twice per model step
        self.tools = MindTools(surfaces, speak=self._speak, stay_silent=self._stay_silent)

    # --- lifecycle ----------------------------------------------------------

    async def start(self):
        self.alive = True
        self.context = [self._system_message([])]
        for s in self.surfaces.all():
            try:
                await s.start()
            except Exception as e:
                logger.error(f"Surface '{s.name}' failed to start: {e}")
        self.tools.invalidate()
        self._loop_task = asyncio.create_task(self.run())
        logger.info("Consciousness started.")

    def sleep(self, reason: str = "") -> None:
        """Bea goes to sleep: stop reacting and show the sleeping avatar."""
        if self.sleeping:
            return
        self.sleeping = True
        try:
            self.expression.set_mood_avatar("sleeping")
        except Exception as e:
            logger.error(f"Failed to set sleeping avatar: {e}")
        self.events.publish(EventCategory.SYSTEM, "consciousness", f"Bea fell asleep ({reason}).")
        logger.info(f"Consciousness asleep ({reason}).")

    def wake(self) -> None:
        """Bea wakes up: resume reacting and restore the normal avatar."""
        if not self.sleeping:
            return
        self.sleeping = False
        try:
            self.expression.set_mood_avatar("normal")
        except Exception as e:
            logger.error(f"Failed to restore avatar on wake: {e}")
        self.events.publish(EventCategory.SYSTEM, "consciousness", "Bea woke up.")
        logger.info("Consciousness awake.")

    async def set_surface_active(self, name: str, state: bool) -> None:
        """Live capability toggle from the UI: arm/disarm a surface at runtime."""
        s = self.surfaces.get(name)
        if not s:
            return
        if state and not s.active:
            await s.start()
        elif not state and s.active:
            await s.stop()
        self.tools.invalidate()
        logger.info(f"Surface '{name}' -> {'active' if s.active else 'inactive'}.")

    async def stop(self):
        self.alive = False
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        for s in self.surfaces.all():
            try:
                await s.stop()
            except Exception:
                pass
        logger.info("Consciousness stopped.")

    # --- HTTP correlation ---------------------------------------------------

    def register_correlation(self, route: str = "local") -> "tuple[str, asyncio.Future]":
        """Lets an HTTP caller wait for Bea's next spoken reply to its input."""
        return self.correlations.register(route)

    # --- the loop -----------------------------------------------------------

    async def run(self):
        while self.alive:
            try:
                idle = self.surfaces.get("idle")
                if idle and idle.active:
                    batch = await self.bus.wait_or_idle(self.idle_after)
                else:
                    # monologue is off: block until something real happens, never self-trigger
                    batch = await self.bus.drain()

                # collected from the RAW batch: a caller the gate filtered out
                # must still be freed, not left hanging until its timeout
                self.correlations.start_batch(batch)

                # asleep: ignore the world (but free any waiting callers so they
                # don't hang) until the dreamer wakes her up
                if self.sleeping:
                    self.correlations.release()
                    continue

                batch, noted = self._filter(batch)
                if noted and self.attention:
                    self.attention.remember(noted)
                batch = self._route(batch)

                # a real input barges in on an ongoing monologue
                if self.expression.is_speaking and any(p.kind != PerceptionKind.IDLE for p in batch):
                    await self.expression.interrupt()

                if not batch:
                    self.correlations.release()
                    continue

                is_idle = bool(batch) and all(p.kind == PerceptionKind.IDLE for p in batch)
                if not is_idle:
                    logger.info(f"batch of {len(batch)} perception(s): "
                                f"{', '.join(p.surface for p in batch)}")

                t_ctx = time.perf_counter()
                self.context[0] = await self._build_system_message(batch, is_idle=is_idle)
                if not is_idle:
                    logger.info(f"context built in {(time.perf_counter() - t_ctx) * 1000:.0f}ms")
                self.context.append(self._frame(batch))

                t_turn = time.perf_counter()
                steps = 0
                spent = Usage()
                for _ in range(self.burst_steps):
                    steer = self.bus.drain_nowait()
                    if steer:
                        self.correlations.extend_batch(steer)
                        steer, steer_noted = self._filter(steer)
                        if steer_noted and self.attention:
                            self.attention.remember(steer_noted)
                        # a message for another channel is dispatched here, mid-burst:
                        # it does not have to wait for the game turn to finish
                        steer = self._route(steer)
                    if steer:
                        self.context.append(self._frame(steer, steering=True))

                    steps += 1
                    t_llm = time.perf_counter()
                    assistant = await self.llm.complete(self.context, tools=self._tool_schemas())
                    spent = spent + assistant.usage
                    if not is_idle:
                        logger.info(f"llm step {steps} took {(time.perf_counter() - t_llm) * 1000:.0f}ms"
                                    f"{' (tools: ' + ', '.join(c.name for c in assistant.tool_calls) + ')' if assistant.tool_calls else ' (final)'}")
                    self.context.append(assistant_to_message(assistant))
                    if assistant.content:
                        self.events.publish(EventCategory.THOUGHT, "consciousness", assistant.content)

                    if assistant.is_final:
                        break

                    for call in assistant.tool_calls:
                        obs = await self._dispatch(call)
                        self.context.append(tool_result_message(call, obs))

                    # once she's only spoken or chosen silence, the turn is over:
                    # don't burn another (slow) llm call just to confirm she's done.
                    # a message that arrives now becomes its own next turn.
                    if assistant.tool_calls and all(
                        c.name in self._TERMINAL_TOOLS for c in assistant.tool_calls
                    ):
                        break

                if not is_idle:
                    elapsed_ms = (time.perf_counter() - t_turn) * 1000
                    logger.info(f"turn done: {steps} llm call(s), {spent.total} tokens, "
                                f"in {elapsed_ms:.0f}ms")
                    self._publish_cost(steps, spent, elapsed_ms)
                self.correlations.release()
                self._trim()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consciousness loop error: {e}")
                await asyncio.sleep(1)

    # --- attention ----------------------------------------------------------

    def _filter(self, batch: List[Perception]) -> "tuple[List[Perception], List[Perception]]":
        """Splits a batch into what deserves a reasoning cycle and what does not.

        Without the gate every perception costs an LLM call — with the game on
        that is one every ten seconds, forever, and a person who deliberates
        over every stimulus does not read as a person.
        """
        if not self.attention:
            return batch, []
        react, noted = self.attention.judge(batch)
        if noted and not react:
            logger.debug(f"attention: noted {len(noted)}, nothing to react to")
        return react, noted

    def _route(self, batch: List[Perception]) -> List[Perception]:
        """Keeps what belongs on the stage; hands the rest to scoped turns.

        An explicit if/else, not two consumers of the same batch: a perception
        must reach exactly one turn, or Bea answers the same message twice from
        two contexts that know nothing about each other.
        """
        if not self.conversations or not batch:
            return batch
        stage, scoped = route(batch)
        for key, perceptions in scoped.items():
            logger.info(f"routing {len(perceptions)} perception(s) to conversation '{key}'")
            self.conversations.dispatch(key, perceptions)
        return stage

    def _publish_cost(self, steps: int, spent: Usage, elapsed_ms: float) -> None:
        """What the turn cost, for the dashboard.

        Not decoration: the whole point of the attention gate is spending fewer
        of these, and you cannot tune what you cannot see.
        """
        self.total_tokens += spent.total
        self.total_calls += steps
        self.events.publish(
            EventCategory.SYSTEM, "cost",
            f"turn: {steps} call(s), {spent.total} tokens, {elapsed_ms:.0f}ms",
            metadata={
                "steps": steps,
                "prompt_tokens": spent.prompt_tokens,
                "completion_tokens": spent.completion_tokens,
                "tokens": spent.total,
                "ms": round(elapsed_ms),
                "session_tokens": self.total_tokens,
                "session_calls": self.total_calls,
            },
        )

    def now_line(self) -> str:
        """One line for a scoped turn: what she is doing on stage right now.

        Deliberately one line. Cross-awareness is what keeps her coherent;
        pouring context between turns is what would make her one slow mind again.
        """
        if self.sleeping:
            return "you're asleep"
        doing = []
        if self._body_task and not self._body_task.done():
            doing.append("your body is busy in Minecraft")
        elif self.surfaces.get("game:mc") and self.surfaces.get("game:mc").active:
            doing.append("you're in Minecraft")
        if self.expression.is_speaking:
            doing.append("you're talking out loud right now")
        return ", ".join(doing)

    # --- context building ---------------------------------------------------

    async def _build_system_message(self, batch: List[Perception], is_idle: bool = False) -> Dict[str, Any]:
        """Async wrapper: dynamic context (RAG embeddings, network IO) is computed
        off the event loop so a slow retrieval never stalls speech/steering/body."""
        dynamic = await asyncio.to_thread(self.surfaces.dynamic_context, batch) if batch else []
        return self._system_message(batch, is_idle=is_idle, dynamic=dynamic)

    def _system_message(self, batch: List[Perception], is_idle: bool = False,
                        dynamic: Optional[List[str]] = None) -> Dict[str, Any]:
        soul = self._get_soul()
        operating = self._get_operating()

        # idle/monologue rules are a last resort: mount them only on a pure-idle frame
        sections = [
            s.context_section for s in self.surfaces.active()
            if s.context_section and (s.name != "idle" or is_idle)
        ]

        live = [s.live_state() for s in self.surfaces.active()]
        live = [x for x in live if x]

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if dynamic is None:
            dynamic = self.surfaces.dynamic_context(batch) if batch else []
        digest = self.attention.digest() if self.attention else ""
        elsewhere = self.conversations.recent_lines() if self.conversations else ""
        parts = [f"CURRENT DATE: {today}", soul, operating, *sections, *live, *dynamic]
        if digest:
            parts.append(digest)
        if elsewhere:
            parts.append(elsewhere)

        return {"role": "system", "content": compose(*parts)}

    def _frame(self, perceptions: List[Perception], steering: bool = False) -> Dict[str, Any]:
        header = "[NEW INPUT — arrived while you were mid-action; decide if it's worth reacting to now]" \
            if steering else "[PERCEPTIONS]"
        lines = [f"({p.kind.value.upper()}) {p.render()}" for p in perceptions]
        return {"role": "user", "content": header + "\n" + "\n".join(lines)}

    # --- tools --------------------------------------------------------------

    def _tool_schemas(self):
        return self.tools.schemas()

    async def _dispatch(self, call: ToolCall) -> str:
        self.events.publish(EventCategory.TOOL, "consciousness", f"{call.name}({call.arguments})")
        registry = self.tools.registry()
        tool = registry.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool '{call.name}'."

        if tool.long_running:
            return self._dispatch_body(tool, call.arguments)

        return await registry.dispatch(call)

    def _dispatch_body(self, tool: Tool, args: Dict[str, Any]) -> str:
        """Starts a BODY action async (single-slot, preempts the previous one)."""
        if self._body_task and not self._body_task.done():
            self._body_task.cancel()
        self._body_task = asyncio.create_task(self._run_body(tool, args))
        return f"{tool.name} started (running in the background; its result will reach you as a perception)."

    async def _run_body(self, tool: Tool, args: Dict[str, Any]):
        try:
            result = tool.handler(**args)
            if asyncio.iscoroutine(result):
                result = await result
        except asyncio.CancelledError:
            return
        except Exception as e:
            result = f"ERROR: {e}"
        # attributed to the surface that owns the tool: hardcoding "game:mc" here
        # mislabelled the result of every body action that was not minecraft
        self.bus.put(Perception(
            PerceptionKind.ACTION, tool.surface or "body",
            f"[{tool.name}] result: {result}", salience=0.7,
        ))

    # --- speaking (non-blocking) -------------------------------------------

    async def _speak(self, mood: str, message: str) -> str:
        mood = mood or "normal"
        # redundant with the client-side clean, deliberately: this is the last
        # gate before the audience hears it
        message = clean_model_output(message)
        if not message:
            logger.warning("speak() had nothing left after sanitizing; staying silent.")
            return await self._stay_silent("nothing sayable")
        if self.attention:
            self.attention.mark_spoke()
        self.history.add_message("assistant", message, mood=mood, source="consciousness")
        self.events.publish(EventCategory.OUTPUT, "consciousness", message, metadata={"mood": mood})

        routes = self.correlations.routes

        if "discord" in routes:
            audio = await self.expression.speak(mood, message, route="remote")
            self.correlations.resolve(lambda r: r == "discord",
                                      {"status": "success", "text": message, "audio": audio})

        if "discord" not in routes or "local" in routes:
            # local stream/OBS: fire-and-forget so reasoning keeps going
            asyncio.create_task(self._speak_local_safe(mood, message))
            self.correlations.resolve(lambda r: r != "discord",
                                      {"mood": mood, "message": message})

        return "Spoken."

    async def _speak_local_safe(self, mood: str, message: str) -> None:
        """Renders local speech without letting playback errors become unretrieved."""
        try:
            await self.expression.speak(mood, message, route="local")
        except Exception as e:
            logger.error(f"Local speech failed: {e}")

    async def _stay_silent(self, reason: str = "") -> str:
        self.correlations.resolve(lambda r: True, {"mood": "normal", "message": ""})
        return "Staying silent."

    def _trim(self):
        if len(self.context) <= self.history_limit + 1:
            return
        tail = self.context[-self.history_limit:]
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        self.context = [self.context[0]] + tail
