import asyncio
import datetime
import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.agent.llm_client import LLMClient
from src.core.agent.messages import assistant_to_message, tool_result_message
from src.core.agent.streaming import SpokenCall, spoken_call
from src.core.agent.tools import Tool
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.core.events import EventCategory
from src.core.expression.chunking import spoken_prefix
from src.core.expression.live import LiveLine
from src.core.mind.correlation import CorrelationRegistry
from src.core.mind.handoff import HandoffWorker
from src.core.mind.moods import DEFAULT_MOOD, normalize_mood
from src.core.mind.routing import channel_of, conversation_key, platform_of
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import TokenBudget
from src.core.mind.tools import MindTools
from src.core.mind.turnlog import TurnLog, turn_record
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.voice.latency import MIND, TTS
from src.utils.logger import get_logger
from src.utils.prompts import compose
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.consciousness")


def _block(what: str, produce) -> str:
    """One part of the briefing, or nothing when building it went wrong.

    Her context is assembled from a dozen independent sources, and any one of
    them raising used to cost the entire turn — she went silent, and the log
    said only what the exception had said. Losing one block is a worse answer;
    losing every turn is not an answer at all.
    """
    try:
        return produce() or ""
    except Exception as e:
        logger.error(f"Leaving {what} out of the briefing: {e}", exc_info=True)
        return ""


class Consciousness:
    """The single, always-on mind.

    One context, one loop: it drains perceptions from every surface, orders
    them by priority, reasons over the one sliding window, and acts through
    unified tools. Speaking is non-blocking and body actions run async, so she
    can talk and play at once. A telegram DM and a minecraft session live in
    the same window — answering one never forgets the other.
    """

    # output tools that end a turn: no follow-up llm call needed after them.
    # written channels mirror voice: send_message may continue (multi-step
    # written turns), but saying nothing anywhere ends the turn.
    _TERMINAL_TOOLS = {"speak", "stay_silent", "say_nothing"}

    # one rescue, not a loop: plain text is private thinking, so a text-only
    # answer means nobody heard her. Rather than staying mute, she gets told once.
    _NO_TOOL_NUDGE = (
        "[NOTICE — nobody saw your last message: plain text is private thinking. "
        "Call speak/send_message/react now with your answer, or stay_silent/say_nothing "
        "if it needs none.]"
    )

    def __init__(self, *, config, llm, bus, expression, surfaces, history_manager,
                 event_manager, soul_getter, operating_getter, attention=None,
                 affect=None, memory=None, profiler=None):
        self.config = config
        self.llm = llm
        self.bus = bus
        self.expression = expression
        self.surfaces = surfaces
        self.history = history_manager
        self.events = event_manager
        self.attention = attention
        self.affect = affect
        # append-only durable log (dream/recall/dashboard read it; no context
        # is ever built from it) and the background profiler of person cards
        self.memory = memory
        self.profiler = profiler
        self._get_soul = soul_getter
        self._get_operating = operating_getter
        self.background_llm: Optional[LLMClient] = None

        cc = config.consciousness
        # the one sliding window: every turn is mirrored here for the budget,
        # and the handoff prose it produces comes back as continuity
        self.sliding_window = SingleContext(TokenBudget(
            max_tokens=int(cc.get("context_max_tokens", 150_000)),
            trigger_tokens=int(cc.get("handoff_trigger_tokens", 120_000)),
            target_tokens=int(cc.get("handoff_target_tokens", 50_000)),
        ), hot_tokens=int(cc.get("hot_tokens", 30_000)),
            hot_seconds=float(cc.get("hot_seconds", 1800.0)))
        self._handoff = HandoffWorker()
        self._handoff_task: Optional[asyncio.Task] = None
        self._handoff_enabled = bool(cc.get("context_handoff", True))
        # the follow-up gate reads the one window, never sqlite: without this
        # the gate is blind and every "are they answering me" is a flat no
        if attention is not None and getattr(attention, "window", None) is None:
            attention.window = self.sliding_window
        self.idle_after = cc.get("idle_after", 30.0)
        self.window = cc.get("window", 0.3)
        self.burst_steps = cc.get("burst_steps", 6)
        self.correlation_timeout = cc.get("correlation_timeout", 30.0)
        # whether a line starts being spoken while the model is still writing it
        self.stream_speech = bool(cc.get("stream_speech", True))

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
        self._said: Optional[Dict[str, Any]] = None
        self._sent: List[Dict[str, Any]] = []
        self._bg_tasks: set = set()
        self.turns = TurnLog(
            cc.get("turn_log_dir", "data/turns"), cc.get("turn_log_days", 14),
        ) if cc.get("turn_log", True) else None

        # a request lifecycle, not part of thinking
        self.correlations = CorrelationRegistry()

        # rebuilt only when a capability is toggled, not twice per model step
        self.tools = MindTools(surfaces, speak=self._speak, stay_silent=self._stay_silent,
                               send_text=self._send_text, react_to=self._react_to,
                               say_nothing=self._say_nothing)

    # --- lifecycle ----------------------------------------------------------

    async def start(self):
        self.alive = True
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
        # a swap landing after shutdown would rewrite a window nobody reads;
        # cancel it and consume it so no exception goes unretrieved
        if self._handoff_task:
            self._handoff_task.cancel()
            try:
                await self._handoff_task
            except (asyncio.CancelledError, Exception):
                pass
            self._handoff_task = None
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

                # a caller the batch carries must still be freed, not left
                # hanging until its timeout
                self.correlations.start_batch(batch)

                # asleep: ignore the world until the dreamer wakes her up
                if self.sleeping:
                    continue

                if not batch:
                    continue

                # texture, not events: game snapshots already live in the live
                # state, and reasoning over every heartbeat would burn the
                # budget for nothing. Everything else wakes the one loop.
                if not self._needs_mind(batch):
                    continue

                is_idle = bool(batch) and all(p.kind == PerceptionKind.IDLE for p in batch)
                if not is_idle:
                    logger.info(f"batch of {len(batch)} perception(s): "
                                f"{', '.join(p.surface for p in batch)}")

                # a voice input barges in on an ongoing monologue; text is just queued
                if self.expression.is_speaking and any(p.kind == PerceptionKind.VOICE for p in batch):
                    await self.expression.interrupt()

                annotated = self._annotate(batch)
                t_ctx = time.perf_counter()
                system = self._system_message()
                window_msgs = self.sliding_window.messages()
                briefing = await self._build_briefing(batch, is_idle=is_idle)
                if not is_idle:
                    logger.info(f"context built in {(time.perf_counter() - t_ctx) * 1000:.0f}ms")
                context: List[Dict[str, Any]] = [system, *window_msgs]
                if briefing:
                    context.append(briefing)
                frame = self._frame(annotated)
                context.append(frame)
                self._batch = list(batch)
                frames = [(frame, annotated)]

                t_turn = time.perf_counter()
                steps = 0
                spent = Usage()
                self._acted, self._said, self._sent = [], None, []
                for _ in range(self.burst_steps):
                    steer = self.bus.drain_nowait()
                    if steer:
                        self.correlations.extend_batch(steer)
                        if self._needs_mind(steer):
                            steered = self._annotate(steer)
                            steer_frame = self._frame(steered, steering=True)
                            context.append(steer_frame)
                            frames.append((steer_frame, steered))
                            self._batch.extend(steer)
                    if not self._batch:
                        break

                    steps += 1
                    t_llm = time.perf_counter()
                    assistant = await self._think(context)
                    spent = spent + assistant.usage
                    if not is_idle:
                        logger.info(f"llm step {steps} took {(time.perf_counter() - t_llm) * 1000:.0f}ms"
                                    f"{' (tools: ' + ', '.join(c.name for c in assistant.tool_calls) + ')' if assistant.tool_calls else ' (final)'}")
                    context.append(assistant_to_message(assistant))
                    if assistant.content:
                        self.events.publish(EventCategory.THOUGHT, "consciousness", assistant.content)

                    if assistant.is_final:
                        break

                    for call in assistant.tool_calls:
                        obs = await self._dispatch(call)
                        context.append(tool_result_message(call, obs))
                    # she started a line and then did something else with the
                    # turn: nobody is going to finish it
                    await self._drop_unspoken()

                    # she spoke or chose silence: the turn is over, and a new
                    # message becomes its own next turn
                    if assistant.tool_calls and all(
                        c.name in self._TERMINAL_TOOLS for c in assistant.tool_calls
                    ):
                        break

                # text-only answer to something real: plain text is private
                # thinking, so nobody heard her — one rescue, not a loop
                if self._needs_answer(batch) and not self._acted:
                    context.append({"role": "user", "content": self._NO_TOOL_NUDGE})
                    assistant = await self._think(context)
                    spent = spent + assistant.usage
                    context.append(assistant_to_message(assistant))
                    if assistant.content:
                        self.events.publish(EventCategory.THOUGHT, "consciousness", assistant.content)
                    if not assistant.is_final:
                        for call in assistant.tool_calls:
                            obs = await self._dispatch(call)
                            context.append(tool_result_message(call, obs))
                        await self._drop_unspoken()

                if not is_idle:
                    elapsed_ms = (time.perf_counter() - t_turn) * 1000
                    logger.info(f"turn done: {steps} llm call(s), {spent.total} tokens, "
                                f"in {elapsed_ms:.0f}ms")
                    self._publish_cost(steps, spent, elapsed_ms)
                    self._write_down(context, self._batch, steps, spent, elapsed_ms)
                    self._record_window(frames)
                    self._log_memory(self._batch)
                    self._profile_background(self._batch)
                    self._schedule_handoff()
                else:
                    self._record_window(frames)
                    self._schedule_handoff()
            except asyncio.CancelledError:
                break
            except Exception as e:
                # the message alone names neither the line nor the skill it came
                # from, and this is the one place every turn fails through
                logger.error(f"Consciousness loop error: {e}", exc_info=True)
                await asyncio.sleep(1)
            finally:
                # a turn that raised must not leave its caller hanging for the
                # whole correlation timeout
                self.correlations.release()
                await self._drop_unspoken()

    # --- one model step -----------------------------------------------------

    async def _think(self, messages: List[Dict[str, Any]]) -> AssistantMessage:
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
            return await self.llm.complete(messages, tools=self._tool_schemas())

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
                messages, tools=self._tool_schemas(), on_tool_delta=on_delta)
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

    # --- attention: order, never filter -------------------------------------

    @staticmethod
    def _needs_mind(batch: List[Perception]) -> bool:
        """Does this batch deserve a reasoning cycle at all.

        Texture the loop already sees elsewhere (a game snapshot flagged as
        noise, already carried by the live state) does not wake the model.
        Everything else — chat from anywhere, voice, events, idle, system —
        enters the one frame.
        """
        return any(not (p.meta or {}).get("noise") for p in batch)

    @staticmethod
    def _needs_answer(batch: List[Perception]) -> bool:
        """Could someone be waiting on words, as opposed to texture or time."""
        return any(p.kind is not PerceptionKind.IDLE and not (p.meta or {}).get("noise")
                   for p in batch)

    def _annotate(self, batch: List[Perception]) -> List["tuple[Perception, float]"]:
        """Priority per perception, highest first. Nothing is ever dropped."""
        if not self.attention:
            return [(p, 0.5) for p in batch]
        return self.attention.annotate(batch)

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

    def _write_down(self, context: List[Dict[str, Any]], batch: List[Perception],
                    steps: int, spent: Usage, elapsed_ms: float) -> None:
        """Files the turn away, for the questions that only come up afterwards."""
        if self.turns is None or not self.turns.enabled:
            return
        try:
            self.turns.write(turn_record(
                context=context,
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

    def _heard(self) -> Optional[Dict[str, Any]]:
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
        # the monologue rules are only true on an idle turn, so they belong to
        # the briefing rather than in here
        sections = self.surfaces.context_sections(exclude=("idle",))
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

        parts.extend(self.surfaces.live_states())

        if dynamic is None:
            dynamic = self.surfaces.dynamic_context(batch) if batch else []

        feeling = _block("how she feels", lambda: self.affect.render() if self.affect else "")
        if feeling:
            parts.append(feeling)
        parts.extend(dynamic)
        return {"role": "system", "content": compose(*parts)}

    def _frame(self, annotated: List[Tuple[Perception, float]],
               steering: bool = False) -> Dict[str, Any]:
        """The one frame: everything that arrived, tagged with where it came from.

        One turn, one frame per batch: a telegram DM and a minecraft death are
        read together, ordered by priority. The `[via ...]` tag is the
        transplanted `place_header` — deterministic self-awareness of where she
        is and with whom, injected from code rather than hoped from prose — and
        the destination a `send_message` must name back.
        """
        header = "[NEW INPUT — arrived while you were mid-action; decide if it's worth reacting to now]" \
            if steering else "[PERCEPTIONS — answer where each arrived: `speak` for voice/stage, `send_message(platform, channel, text)` for the rest]"
        orientation = self._orientation(annotated)
        now = time.time()
        lines = [f"({p.kind.value.upper()}) [{self._provenance(p)}] {p.render(now=now)}"
                 for p, _ in annotated]
        body = "\n".join(lines)
        if orientation:
            body = f"{orientation}\n{body}"
        cut_off = self._interruption_note()
        if cut_off:
            body = f"{cut_off}\n{body}"
        return {"role": "user", "content": header + "\n" + body}

    @staticmethod
    def _provenance(p: Perception) -> str:
        """Where this line arrived, in the words the tools need back."""
        key = conversation_key(p)
        name = p.author.display_name if p.author else ""
        meta = p.meta or {}
        if key == "stage":
            if p.kind is PerceptionKind.VOICE:
                return "via voice call"
            if p.surface == "chat:ui":
                return "via dashboard"
            if p.kind is PerceptionKind.GAME:
                return "via minecraft"
            if p.kind is PerceptionKind.IDLE:
                return "via silence"
            if meta.get("amount") or (p.author and p.author.extra.get("amount")):
                return "via donation"
            return f"via {p.surface}"
        platform = platform_of(key)
        channel = channel_of(key) or "?"
        who = f" da {name}" if name else ""
        if meta.get("is_dm"):
            return f"via {platform} DM{who} (channel={channel})"
        return f"via {platform} {channel}{who} (channel={channel})"

    def _orientation(self, annotated: List[Tuple[Perception, float]]) -> str:
        """Deterministic grounding: where she is, with whom, on what.

        The transplanted `place_header`, generalized from one channel to the
        whole batch: with several destinations in one frame, hoping the model
        infers them from key formats is how she ends up claiming she has no
        telegram while answering on it.
        """
        seen: Dict[str, str] = {}
        for p, _ in annotated:
            key = conversation_key(p)
            if key == "stage" or key in seen:
                continue
            name = p.author.display_name if p.author else "someone"
            dm = " (DM)" if (p.meta or {}).get("is_dm") else ""
            seen[key] = (f"You are on {platform_of(key)} in conversation "
                         f"{channel_of(key) or '?'} with {name}{dm}. Answer here with "
                         f"send_message(platform={platform_of(key)!r}, "
                         f"channel={channel_of(key) or '?'!r}) — never claim otherwise.")
        if not seen:
            return ""
        return "[WHERE YOU ARE]\n" + "\n".join(seen.values())

    def _addressee_for(self, key: str) -> str:
        """Who she was answering in this conversation.

        A turn can answer several conversations at once; stamping every reply
        with the batch-dominant author misattributes all but one and blinds
        the follow-up gate on the rest.
        """
        for p in self._batch:
            if p.author is not None and conversation_key(p) == key:
                return p.author.identity
        return ""

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

    # --- unified text tools -------------------------------------------------

    def _skill_for_platform(self, platform: str):
        for skill in self.surfaces.active():
            if getattr(skill, "platform", None) == platform:
                return skill
        return None

    async def _send_text(self, platform: str, channel: str, text: str,
                         reply_to: str = "") -> str:
        """Writes where it arrived. The destination rides in the arguments."""
        skill = self._skill_for_platform(platform)
        if skill is None:
            return (f"FAILED: no active skill for platform '{platform}'. "
                    f"Use speak for voice/stage.")
        try:
            sent = await skill.deliver(str(channel), text,
                                       reply_to=reply_to or None)
        except Exception as e:
            logger.warning(f"send_message to {platform}:{channel} failed: {e}")
            return f"FAILED: {e}"
        if not sent:
            return "FAILED: nothing was sent."
        key = f"{platform}:{channel}"
        self._sent.append({"platform": platform, "channel": str(channel), "text": text})
        if self.attention:
            self.attention.mark_spoke(key)
        self._log_outgoing(key, platform, str(channel), text)
        return f"Sent ({len(sent)} message(s))."

    async def _react_to(self, platform: str, channel: str, message_id: str,
                        emoji: str) -> str:
        skill = self._skill_for_platform(platform)
        if skill is None:
            return f"FAILED: no active skill for platform '{platform}'."
        try:
            ok = await skill.react(str(channel), str(message_id), emoji)
        except Exception as e:
            return f"FAILED: {e}"
        if ok and self.attention:
            self.attention.mark_spoke(f"{platform}:{channel}")
        return "Reacted." if ok else "FAILED: could not react."

    async def _say_nothing(self, reason: str = "") -> str:
        return "Said nothing."

    # --- the window is the context ------------------------------------------

    def _record_window(self, frames: List[Tuple[Dict[str, Any],
                                                List[Tuple[Perception, float]]]]) -> None:
        """Mirrors the turn into the one sliding window.

        The perceptions go in as individual user entries tagged with their
        conversation keys; what she sent back goes in as assistant entries with
        the addressee she was answering — the follow-up gate reads exactly
        this. Boilerplate, idle turns and her own system nudges are not
        stored: a spontaneous poke is an instruction for this turn, not
        someone speaking, and keeping it as a user line would let the room
        stay "alive" on its own echoes.
        """
        try:
            now = time.time()
            for _, annotated in frames:
                for p, _ in annotated:
                    if p.kind is PerceptionKind.IDLE or p.kind is PerceptionKind.SYSTEM:
                        continue
                    key = conversation_key(p)
                    author = p.author.identity if p.author else ""
                    content = f"({p.kind.value.upper()}) [{self._provenance(p)}] {p.render(now=now)}"
                    self.sliding_window.append("user", content, key=key, author=author)
            for sent in self._sent:
                key = f"{sent['platform']}:{sent['channel']}"
                self.sliding_window.append("assistant", sent["text"], key=key,
                                           addressee=self._addressee_for(key))
            if self._said and self._said.get("message"):
                self.sliding_window.append("assistant", str(self._said["message"]),
                                           key="stage")
        except Exception as e:
            logger.warning(f"Could not mirror the turn into the window: {e}")

    def _log_memory(self, batch: List[Perception]) -> None:
        """Append-only durable log: dream/recall/dashboard read it, no context
        is ever built from it."""
        if self.memory is None:
            return
        try:
            conversations = self.memory.conversations
            for p in batch:
                if p.author is None:
                    continue
                conversations.add(
                    conversation_key=conversation_key(p), role="user",
                    content=p.content,
                    platform=p.author.platform, channel_id=str((p.meta or {}).get("channel_id", "")),
                    author_identity=p.author.identity, display_name=p.author.display_name,
                    ts=p.ts,
                )
        except Exception as e:
            logger.warning(f"Could not log the turn to memory: {e}")

    def _log_outgoing(self, key: str, platform: str, channel: str, text: str) -> None:
        """Her written lines, next to what she was answering."""
        if self.memory is None:
            return
        try:
            addressee = self._addressee_for(key)
            self.memory.conversations.add(
                conversation_key=key, role="bea", content=text,
                platform=platform, channel_id=channel, display_name="bea",
                addressee_identity=addressee,
            )
        except Exception as e:
            logger.warning(f"Could not log her reply to memory: {e}")

    def _profile_background(self, batch: List[Perception]) -> None:
        """Keeps person cards fresh after answering, never in the way of it."""
        if self.profiler is None:
            return
        identities = {p.author.identity for p in batch if p.author}
        if not identities:
            return
        profiler = self.profiler

        async def work():
            for identity in identities:
                try:
                    await profiler.maybe_profile(identity)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"Background profiling failed: {e}")

        task = asyncio.create_task(work())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def window_status(self) -> Dict[str, Any]:
        """Budget state for the dashboard."""
        return {
            **self.sliding_window.status(),
            "handoff_enabled": self._handoff_enabled,
            "handoff_running": self._handoff_task is not None and not self._handoff_task.done(),
            "handoff_swaps": self._handoff.swaps,
            "last_prose": self._handoff.last_prose,
            "continuity_chars": len(self._handoff.last_prose),
        }

    def _schedule_handoff(self) -> None:
        """Hands off in the background: the mind never waits on its own memory.

        When the worker finishes, its prose opens the next window under
        [EARLIER] — the window breathes instead of pinning at the ceiling.
        """
        if not self._handoff_enabled:
            return
        if self._handoff_task and not self._handoff_task.done():
            return
        if not self.sliding_window.status()["needs_handoff"]:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # not now; the window keeps everything and the next turn tries again

        async def work():
            try:
                self._handoff.set_llm(self.background_llm or self.llm)
                await self._handoff.maybe_swap(self.sliding_window)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Window handoff failed: {e}")

        self._handoff_task = asyncio.create_task(work())
