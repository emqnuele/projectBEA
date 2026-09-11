import asyncio
import datetime
import time
from typing import Any, Dict, List, Optional

from src.core.agent.llm_client import LLMClient
from src.core.agent.messages import assistant_to_message, tool_result_message
from src.core.agent.streaming import SpokenCall, spoken_call
from src.core.agent.tools import Tool
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.core.events import EventCategory
from src.core.expression.chunking import spoken_prefix
from src.core.expression.live import LiveLine
from src.core.mind.correlation import CorrelationRegistry
from src.core.mind.moods import DEFAULT_MOOD, normalize_mood
from src.core.mind.recap import SessionRecap
from src.core.mind.routing import route
from src.core.mind.tools import MindTools
from src.core.mind.turnlog import TurnLog, turn_record
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.voice.latency import MIND, TTS
from src.utils.logger import get_logger
from src.utils.prompts import compose
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.consciousness")


class Consciousness:
    """The single, always-on mind.

    One context, one loop: it drains perceptions from every surface, folds new
    ones in mid-burst (steering), reasons, and acts through tools. Speaking is
    non-blocking and body actions run async, so she can talk and play at once.
    """

    # output tools that end a turn: no follow-up llm call needed after them
    _TERMINAL_TOOLS = {"speak", "stay_silent"}

    def __init__(self, *, config, llm, bus, expression, surfaces, history_manager,
                 event_manager, soul_getter, operating_getter, attention=None,
                 conversations=None, affect=None):
        self.config = config
        self.llm = llm
        self.bus = bus
        self.expression = expression
        self.surfaces = surfaces
        self.history = history_manager
        self.events = event_manager
        self.attention = attention
        self.conversations = conversations
        self.affect = affect
        self._get_soul = soul_getter
        self._get_operating = operating_getter
        # what scrolled out of the rolling context, in one line she keeps
        self.recap = SessionRecap()
        self.background_llm: Optional[LLMClient] = None
        self._recap_task: Optional[asyncio.Task] = None

        cc = config.consciousness
        self.idle_after = cc.get("idle_after", 30.0)
        self.window = cc.get("window", 0.3)
        self.burst_steps = cc.get("burst_steps", 6)
        self.history_limit = cc.get("history_limit", 30)
        self.correlation_timeout = cc.get("correlation_timeout", 30.0)
        # whether a line starts being spoken while the model is still writing it
        self.stream_speech = bool(cc.get("stream_speech", True))

        self.context: List[Dict[str, Any]] = []
        # what provoked the turn in flight: `speak` needs it to know who to pin
        # a strong reaction on, and a tool handler is not handed the batch
        self._batch: List[Perception] = []
        self.total_tokens = 0
        self.total_calls = 0
        self.alive = False
        self.sleeping = False
        self._loop_task: Optional[asyncio.Task] = None
        self._body_task: Optional[asyncio.Task] = None
        # a line already on its way out while the tool call that asked for it is
        # still being written
        self._live: Optional[LiveLine] = None

        # what this turn has done so far, for the record written at the end of it
        self._acted: List[Dict[str, Any]] = []
        self._said: Optional[Dict[str, str]] = None
        self.turns = TurnLog(
            cc.get("turn_log_dir", "data/turns"), cc.get("turn_log_days", 14),
        ) if cc.get("turn_log", True) else None

        # a request lifecycle, not part of thinking
        self.correlations = CorrelationRegistry()

        # rebuilt only when a capability is toggled, not twice per model step
        self.tools = MindTools(surfaces, speak=self._speak, stay_silent=self._stay_silent)

    # --- lifecycle ----------------------------------------------------------

    async def start(self):
        self.alive = True
        self.context = [self._system_message()]
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
            self.expression.set_state("sleeping")
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
            self.expression.set_state("idle", mood=DEFAULT_MOOD)
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
            briefing: Optional[Dict[str, Any]] = None
            try:
                idle = self.surfaces.get("idle")
                if idle and idle.active:
                    batch = await self.bus.wait_or_idle(self.idle_after)
                else:
                    # monologue is off: block until something real happens, never self-trigger
                    batch = await self.bus.drain()

                # from the RAW batch: a caller the gate filtered out must still
                # be freed, not left hanging until its timeout
                self.correlations.start_batch(batch)

                # asleep: ignore the world until the dreamer wakes her up
                if self.sleeping:
                    continue

                batch, noted = self._filter(batch)
                if noted and self.attention:
                    self.attention.remember(noted)
                batch = self._route(batch)

                # a real input barges in on an ongoing monologue
                if self.expression.is_speaking and any(p.kind != PerceptionKind.IDLE for p in batch):
                    await self.expression.interrupt()

                if not batch:
                    continue

                is_idle = bool(batch) and all(p.kind == PerceptionKind.IDLE for p in batch)
                if not is_idle:
                    logger.info(f"batch of {len(batch)} perception(s): "
                                f"{', '.join(p.surface for p in batch)}")

                t_ctx = time.perf_counter()
                self.context[0] = self._system_message()
                briefing = await self._build_briefing(batch, is_idle=is_idle)
                if not is_idle:
                    logger.info(f"context built in {(time.perf_counter() - t_ctx) * 1000:.0f}ms")
                if briefing:
                    self.context.append(briefing)
                self.context.append(self._frame(batch))
                self._batch = list(batch)

                t_turn = time.perf_counter()
                steps = 0
                spent = Usage()
                self._acted, self._said = [], None
                for _ in range(self.burst_steps):
                    steer = self.bus.drain_nowait()
                    if steer:
                        self.correlations.extend_batch(steer)
                        steer, steer_noted = self._filter(steer)
                        if steer_noted and self.attention:
                            self.attention.remember(steer_noted)
                        # dispatched mid-burst: another channel does not wait
                        # for the game turn to finish
                        steer = self._route(steer)
                    if steer:
                        self.context.append(self._frame(steer, steering=True))
                        self._batch.extend(steer)

                    steps += 1
                    t_llm = time.perf_counter()
                    assistant = await self._think()
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
                    # she started a line and then did something else with the
                    # turn: nobody is going to finish it
                    await self._drop_unspoken()

                    # she spoke or chose silence: the turn is over, and a new
                    # message becomes its own next turn
                    if assistant.tool_calls and all(
                        c.name in self._TERMINAL_TOOLS for c in assistant.tool_calls
                    ):
                        break

                if not is_idle:
                    elapsed_ms = (time.perf_counter() - t_turn) * 1000
                    logger.info(f"turn done: {steps} llm call(s), {spent.total} tokens, "
                                f"in {elapsed_ms:.0f}ms")
                    self._publish_cost(steps, spent, elapsed_ms)
                    self._write_down(batch, steps, spent, elapsed_ms)
                self._drop(briefing)
                self._trim()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consciousness loop error: {e}")
                await asyncio.sleep(1)
            finally:
                # a turn that raised must not leave its caller hanging for the
                # whole correlation timeout
                self.correlations.release()
                self._drop(briefing)
                await self._drop_unspoken()

    # --- one model step -----------------------------------------------------

    async def _think(self) -> AssistantMessage:
        """One model step, with the line already on its way out as it is written.

        A spoken turn used to exist all at once: the model finished the whole
        tool call, and only then did anything reach the engine. The words are
        there long before that — sitting inside a JSON string with no closing
        quote — so the first sentence leaves as soon as it is a whole sentence.

        Everything here is best-effort. A provider that cannot stream, a model
        that writes the message before the mood, an engine that is busy: any of
        those simply means no line was opened, and the turn is spoken by
        `_speak` exactly as it was before.
        """
        if not self.stream_speech:
            return await self.llm.complete(self.context, tools=self._tool_schemas())

        # one reader per tool call, because a provider may write two of them at
        # once. Sharing one meant a second call's arguments were read as more of
        # the first's message — she said the brace and lost the rest of the line.
        readers: Dict[int, Optional[SpokenCall]] = {}
        line: Optional[LiveLine] = None
        spoken: Optional[int] = None

        def on_delta(index: int, name: str, delta: str) -> None:
            nonlocal line, spoken
            if index not in readers:
                readers[index] = spoken_call(name)
            reader = readers[index]
            # only one line can be on its way out at a time: a second `speak` in
            # the same turn is said the ordinary way, once this one has finished
            if reader is None or (spoken is not None and spoken != index):
                return

            words = reader.push(delta)
            if not words:
                return
            if line is None:
                line = self._open_line(reader.mood)
                if line is None:
                    readers[index] = None
                    return
                spoken = index
            line.say(words)

        try:
            return await self.llm.stream_complete(
                self.context, tools=self._tool_schemas(), on_tool_delta=on_delta)
        finally:
            self._live = line

    def _open_line(self, mood: str) -> Optional[LiveLine]:
        """A line to start speaking into, or None when speaking early cannot work."""
        try:
            route = "call" if self.expression.call_is_live else "local"
            feeling = self.affect.current if self.affect else None
            return self.expression.open_line(
                normalize_mood(mood), route=route, feeling=feeling)
        except Exception as e:
            logger.error(f"Could not start speaking early: {e}")
            return None

    async def _drop_unspoken(self) -> None:
        """Throws away a line she started and then decided against."""
        line, self._live = self._live, None
        if line is None:
            return
        logger.info("A line was started and never spoken; dropping it.")
        try:
            await line.cancel()
        except Exception as e:
            logger.error(f"Could not drop the unspoken line: {e}")

    # --- attention ----------------------------------------------------------

    def _filter(self, batch: List[Perception]) -> "tuple[List[Perception], List[Perception]]":
        """Splits a batch into what deserves a reasoning cycle and what does not."""
        if not self.attention:
            return batch, []
        react, noted = self.attention.judge(batch)
        if noted and not react:
            logger.debug(f"attention: noted {len(noted)}, nothing to react to")
        return react, noted

    def _route(self, batch: List[Perception]) -> List[Perception]:
        """Keeps what belongs on the stage; hands the rest to scoped turns."""
        if not self.conversations or not batch:
            return batch
        stage, scoped = route(batch)
        for key, perceptions in scoped.items():
            logger.info(f"routing {len(perceptions)} perception(s) to conversation '{key}'")
            self.conversations.dispatch(key, perceptions)
        return stage

    def _publish_cost(self, steps: int, spent: Usage, elapsed_ms: float) -> None:
        """What the turn cost, for the dashboard: the gate cannot be tuned blind."""
        self.total_tokens += spent.total
        self.total_calls += steps
        cached = f", {round(spent.cache_hit * 100)}% cached" if spent.cached_tokens else ""
        self.events.publish(
            EventCategory.SYSTEM, "cost",
            f"turn: {steps} call(s), {spent.total} tokens, {elapsed_ms:.0f}ms{cached}",
            metadata={
                "steps": steps,
                "prompt_tokens": spent.prompt_tokens,
                "completion_tokens": spent.completion_tokens,
                "cached_tokens": spent.cached_tokens,
                "tokens": spent.total,
                "ms": round(elapsed_ms),
                "session_tokens": self.total_tokens,
                "session_calls": self.total_calls,
            },
        )

    def _write_down(self, batch: List[Perception], steps: int, spent: Usage,
                    elapsed_ms: float) -> None:
        """Files the turn away, for the questions that only come up afterwards."""
        if self.turns is None or not self.turns.enabled:
            return
        try:
            self.turns.write(turn_record(
                context=self.context,
                perceptions=[p.render() for p in batch],
                calls=self._acted,
                spoke=self._heard(),
                usage=spent,
                steps=steps,
                ms=elapsed_ms,
                model=getattr(self.llm, "model_name", "") or "",
            ))
        except Exception as e:
            # writing down is for later, and must never cost the turn it describes
            logger.warning(f"Could not write the turn down: {e}")

    def _heard(self) -> Optional[Dict[str, str]]:
        """What the room actually heard, not what the whole sentence was.

        An interruption from the call is proof the tail never reached the room:
        the log claiming it did is how she ends up referred to a second half
        nobody heard. `_interruption_note` reads the same record next turn.
        """
        heard = dict(self._said) if self._said else None
        if not heard or "message" not in heard:
            return heard
        utterance = getattr(self.expression, "interrupted", None)
        if utterance is None or getattr(utterance, "complete", True):
            return heard
        if getattr(utterance, "text", None) != heard["message"]:
            return heard
        cut = spoken_prefix(utterance.text, utterance.played_ms, utterance.sent_ms)
        if cut:
            heard["message"] = cut
        else:
            # the sentence was cut off before a single word of it landed
            heard.pop("message", None)
            heard["cut_off"] = True
        return heard

    def now_line(self) -> str:
        """One line for a scoped turn: what she is doing on stage right now.

        One line on purpose — pouring context between turns would make her one
        slow mind again.
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
        discord = self.surfaces.get("voice:discord")
        if discord is not None and getattr(discord, "voice_channel", None):
            doing.append("you're sitting in a voice call")
        return ", ".join(doing)

    # --- context building ---------------------------------------------------

    async def _build_briefing(self, batch: List[Perception],
                              is_idle: bool = False) -> Optional[Dict[str, Any]]:
        """Builds it off the loop: a slow retrieval must not stall speech."""
        dynamic = await asyncio.to_thread(self.surfaces.dynamic_context, batch) if batch else []
        return self._briefing(batch, is_idle=is_idle, dynamic=dynamic)

    def _system_message(self) -> Dict[str, Any]:
        """Who she is and how she works: the half that does not move.

        Everything a provider can cache lives here, and it is worth keeping it
        that way. Caching matches on the longest common prefix of a request, so
        one volatile line at the top — the date, a retrieved memory, how she
        happens to feel — costs the whole prompt on every single turn. That is
        why the rest of it is a separate message further down: see `_briefing`.
        """
        sections = [
            s.context_section for s in self.surfaces.active()
            # the monologue rules are only true on an idle turn, so they belong
            # to the briefing rather than in here
            if s.context_section and s.name != "idle"
        ]
        return {"role": "system",
                "content": compose(self._get_soul(), self._get_operating(), *sections)}

    def _briefing(self, batch: List[Perception], is_idle: bool = False,
                  dynamic: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Everything that is only true right now, as one block she is told once.

        It sits directly above the perceptions it describes and is taken back out
        at the end of the turn: what she was told about this moment is not part
        of the conversation, and leaving it in would have her answering a memory
        retrieved for a question somebody asked ten minutes ago.
        """
        parts: List[str] = [
            f"CURRENT DATE: {datetime.datetime.now().strftime('%Y-%m-%d')}"
        ]

        if is_idle:
            idle = self.surfaces.get("idle")
            if idle is not None and idle.active and idle.context_section:
                parts.append(idle.context_section)

        parts.extend(x for x in (s.live_state() for s in self.surfaces.active()) if x)

        if dynamic is None:
            dynamic = self.surfaces.dynamic_context(batch) if batch else []

        feeling = self.affect.render() if self.affect else ""
        if feeling:
            parts.append(feeling)
        parts.extend(dynamic)
        for block in (self.recap.render(),
                      self.attention.digest() if self.attention else "",
                      self.conversations.recent_lines() if self.conversations else ""):
            if block:
                parts.append(block)

        return {"role": "system", "content": compose(*parts)}

    def _frame(self, perceptions: List[Perception], steering: bool = False) -> Dict[str, Any]:
        header = "[NEW INPUT — arrived while you were mid-action; decide if it's worth reacting to now]" \
            if steering else "[PERCEPTIONS]"
        # anything old enough says so; a batch that arrived at once stays clean
        now = time.time()
        lines = [f"({p.kind.value.upper()}) {p.render(now=now)}" for p in perceptions]
        body = "\n".join(lines)
        cut_off = self._interruption_note()
        if cut_off:
            body = f"{cut_off}\n{body}"
        return {"role": "user", "content": header + "\n" + body}

    def _interruption_note(self) -> Optional[str]:
        """Tells her where a barge-in actually cut her off, once.

        Her history records the whole line she asked for, always. When someone
        talks over her, the room heard the first half — and she goes on referring
        to the second half as if it had been said. That, more than any latency,
        is what breaks the illusion that there is a person there.
        """
        utterance = getattr(self.expression, "interrupted", None)
        if utterance is None:
            return None
        self.expression.interrupted = None
        if getattr(utterance, "complete", True):
            return None

        heard = spoken_prefix(utterance.text, utterance.played_ms, utterance.sent_ms)
        if not heard:
            return "[YOU WERE CUT OFF] You were talked over before a word of that landed. Nobody heard any of it."
        return (f'[YOU WERE CUT OFF] You got as far as "{heard}" and stopped there. '
                "Nobody heard the rest, so do not talk as if they did.")

    # --- tools --------------------------------------------------------------

    def _tool_schemas(self):
        return self.tools.schemas()

    async def _dispatch(self, call: ToolCall) -> str:
        self.events.publish(EventCategory.TOOL, "consciousness", f"{call.name}({call.arguments})")
        result = await self._run_tool(call)
        self._acted.append({"tool": call.name, "arguments": call.arguments, "result": result})
        return result

    async def _run_tool(self, call: ToolCall) -> str:
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
        # attributed to the surface that owns the tool, not to minecraft
        self.bus.put(Perception(
            PerceptionKind.ACTION, tool.surface or "body",
            f"[{tool.name}] result: {result}", salience=0.7,
        ))

    # --- speaking (non-blocking) -------------------------------------------

    async def _speak(self, mood: str, message: str) -> str:
        # whatever of this line is already on its way out. Taken here rather than
        # in the loop so the two can never both own it.
        line, self._live = self._live, None
        if line is not None and line.spoiled:
            # she met her own scaffolding before a word was heard: throw the
            # line away and say the finished message, which cleans whole
            await line.cancel()
            line = None

        # the model invents moods; an avatar that silently fails to change is
        # worse than landing on the nearest one she actually has
        mood = normalize_mood(mood)
        # redundant with the client-side clean: last gate before the audience
        message = clean_model_output(message)
        if not message:
            logger.warning("speak() had nothing left after sanitizing; staying silent.")
            if line is not None:
                await line.cancel()
            return await self._stay_silent("nothing sayable")
        if self.attention:
            self.attention.mark_spoke()
        self.history.add_message("assistant", message, mood=mood, source="consciousness")
        self.events.publish(EventCategory.OUTPUT, "consciousness", message, metadata={"mood": mood})
        self._said = {"mood": mood, "message": message}

        latency = self._voice_latency
        # how she felt when she decided on this line, before it moves her
        feeling = self.affect.current if self.affect else None

        if line is not None:
            # she is already saying it: all that is left is the end of the line
            if latency:
                latency.mark(MIND)
            if line.route == "call":
                await line.close()
                if latency:
                    latency.mark(TTS)
            else:
                # fire-and-forget so reasoning keeps going
                asyncio.create_task(self._finish_line(line))
        elif self.expression.call_is_live:
            # every sentence of a turn goes to the room, not just the first: the
            # call is a sink she pushes into, not one reply she hands back
            if latency:
                latency.mark(MIND)
            await self.expression.speak(mood, message, route="call", feeling=feeling)
            if latency:
                latency.mark(TTS)
        else:
            # fire-and-forget so reasoning keeps going
            asyncio.create_task(self._speak_local_safe(mood, message, feeling))

        # whoever is blocked on a written answer gets one either way
        self.correlations.resolve(lambda r: True, {"mood": mood, "message": message})

        # after the voice, not before: this line is already coloured by its own
        # mood, and counting it twice would make the first sharp remark shout
        if self.affect:
            self.affect.spoke(mood, self._batch)

        return "Spoken."

    @property
    def _voice_latency(self):
        """The stopwatch of the voice turn in flight, when there is a call."""
        return getattr(self.surfaces.get("voice:discord"), "latency", None)

    async def _finish_line(self, line: LiveLine) -> None:
        """Waits out a line that is already being heard, without holding the mind."""
        try:
            await line.close()
        except Exception as e:
            logger.error(f"Local speech failed: {e}")

    async def _speak_local_safe(self, mood: str, message: str, feeling=None) -> None:
        """Local speech in a task: a playback error must not go unretrieved."""
        try:
            await self.expression.speak(mood, message, route="local", feeling=feeling)
        except Exception as e:
            logger.error(f"Local speech failed: {e}")

    async def _stay_silent(self, reason: str = "") -> str:
        # she said nothing: there is no time-to-first-sound to report
        latency = self._voice_latency
        if latency:
            latency.abandon()
        self.correlations.resolve(lambda r: True, {"mood": DEFAULT_MOOD, "message": ""})
        return "Staying silent."

    def _drop(self, message: Optional[Dict[str, Any]]) -> None:
        """Takes a per-turn message back out of the context.

        By identity, not by value: two briefings a minute apart can be the same
        text, and removing the wrong one would leave a stale retrieval in the
        conversation for the rest of the session.
        """
        if message is None:
            return
        for index, existing in enumerate(self.context):
            if existing is message:
                del self.context[index]
                return

    def _trim(self):
        if len(self.context) <= self.history_limit + 1:
            return
        tail = self.context[-self.history_limit:]
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        # what falls out here is what she would otherwise simply never have
        # heard: hand it over before dropping it
        kept = len(tail)
        self.recap.drop(self.context[1:-kept] if kept else self.context[1:])
        self.context = [self.context[0]] + tail
        if self.recap.due:
            self._schedule_recap()

    def _schedule_recap(self) -> None:
        """Condenses in the background: the mind never waits on its own memory.

        `_trim` is synchronous and can be reached from outside the loop, so a
        missing loop means "not now" rather than an error — the turns are kept
        and the next trim schedules it.
        """
        if self._recap_task and not self._recap_task.done():
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # not now; the turns are kept and the next trim tries again

        async def work():
            try:
                await self.recap.condense(self.background_llm or self.llm)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Session recap failed: {e}")

        self._recap_task = asyncio.create_task(work())
