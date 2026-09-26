import asyncio
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
from src.core.language import directive, speaks_first
from src.core.mind.correlation import CorrelationRegistry
from src.core.mind.handoff import HandoffWorker
from src.core.mind.moods import DEFAULT_MOOD, normalize_mood
from src.core.mind.operating import unarmed
from src.core.mind.routing import STAGE, channel_of, conversation_key, platform_of
from src.core.mind.single_context import SingleContext
from src.core.mind.token_budget import budget_from_config
from src.core.mind.tools import MindTools
from src.core.mind.turnlog import TurnLog, turn_record
from src.core.perception.types import Perception, PerceptionKind
from src.core.skills.voice.latency import MIND, TTS
from src.utils.logger import get_logger
from src.utils.prompts import compose
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.consciousness")

# the handoff recap as a settings row: the window mirror holds entries, and
# the prose that opens the next window is not one — without this a restart
# restores the evening without its head
HANDOFF_PROSE_KEY = "handoff_prose"

# how many written perception ids the double-write guard keeps: the bus pops,
# so seeing the same id twice is a caller bug worth surviving cheaply
_STREAM_ID_CAP = 5000


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


def _tool_failed(call: Dict[str, Any]) -> bool:
    """A tool observation that says the call did not land."""
    return str(call.get("result", "")).startswith(("ERROR", "FAILED"))


# how a game action says it did not get there
_WENT_WRONG = ("FAILURE", "FAILED", "ERROR", "TIMEOUT", "INTERRUPTED")


def _went_wrong(result: str) -> bool:
    return result.lstrip().upper().startswith(_WENT_WRONG)


class Consciousness:
    """The single, always-on mind.

    One context, one loop: it drains perceptions from every surface, orders
    them by priority, reasons over the one sliding window, and acts through
    unified tools. Speaking is non-blocking and game actions run async, so she
    can talk and play at once. A telegram DM and a minecraft session live in
    the same window — answering one never forgets the other.
    """

    # output tools that end a turn: no follow-up llm call needed after them.
    # written channels mirror voice: send_message may continue (multi-step
    # written turns), but saying nothing anywhere ends the turn.
    _TERMINAL_TOOLS = {"speak", "stay_silent", "say_nothing"}

    # how long shutdown waits for a message still being typed out
    _DELIVERY_GRACE = 10.0

    # how long one skill may hold the shutdown. Sequential and unbounded meant
    # a single hung connection (telegram polling, the game socket) ate the
    # whole stop and starved every skill after it — including the discord bot.
    _SURFACE_STOP_TIMEOUT = 5.0

    # one rescue, not a loop: plain text is private thinking, so a text-only
    # answer means nobody heard her. Rather than staying mute, she gets told once.
    _NO_TOOL_NUDGE = (
        "[NOTICE — nobody saw your last message: plain text is private thinking. "
        "Call speak/send_message/react now with your answer, or stay_silent/say_nothing "
        "if it needs none.]"
    )

    def __init__(self, *, config, llm, bus, expression, surfaces, history_manager,
                 event_manager, soul_getter, operating_getter, memory, profiler,
                 attention=None, affect=None):
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
        # is ever built from it) and the background profiler of person cards.
        # required, not optional: a defaulted `memory=None` let a refactor drop
        # the wiring and every write return at its own first line, for days
        self.memory = memory
        self.profiler = profiler
        self._get_soul = soul_getter
        self._get_operating = operating_getter
        self.background_llm: Optional[LLMClient] = None

        cc = config.consciousness
        # the one sliding window: every turn is mirrored here for the budget,
        # and the handoff prose it produces comes back as continuity
        budget, hot = budget_from_config(cc)
        self.sliding_window = SingleContext(budget, hot_tokens=hot, store=memory.window)
        # the loop the window belongs to: a resize posted from a dashboard
        # thread has to land on it, never run beside it
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._handoff = HandoffWorker(language=getattr(config, "language", ""))
        self._handoff_task: Optional[asyncio.Task] = None
        # every persist in flight, not just the latest: a fast pair of turns
        # must not orphan the first write while the second is awaited
        self._persist_tasks: set = set()
        self._read_knobs(cc)
        # the follow-up gate reads the one window, never sqlite: without this
        # the gate is blind and every "are they answering me" is a flat no
        if attention is not None and getattr(attention, "window", None) is None:
            attention.window = self.sliding_window

        # what provoked the turn in flight: `speak` needs it to know who to pin
        # a strong reaction on, and a tool handler is not handed the batch
        self._batch: List[Perception] = []
        # ids already on the stream: a second write of the same perception is
        # a caller bug, not a second event — skip it instead of duplicating
        self._stream_ids: Dict[str, None] = {}
        self.total_tokens = 0
        self.total_calls = 0
        self.alive = False
        self.sleeping = False
        self._loop_task: Optional[asyncio.Task] = None
        self._action_task: Optional[asyncio.Task] = None
        # what her hands still have to do, in the order she asked, and the step
        # that asked: things asked in one breath queue, a later step replaces them
        self._action_queue: List[Tuple[Tool, Dict[str, Any]]] = []
        self._action_step = -1
        self._steps_taken = 0
        # the calls of this step that only set something going in the background
        self._backgrounded: set = set()
        # this turn has already been given its one extra step by a skill
        self._pushed = False
        # a line already on its way out while the tool call that asked for it is
        # still being written
        self._live: Optional[LiveLine] = None
        # the turn in flight, so the call can call it off: somebody went on
        # talking before she had said or done anything about the first half
        self._turn_task: Optional[asyncio.Task] = None
        self._start_over = False
        # the tool running right now, if any: one half way through is never cut
        self._dispatching: Optional[str] = None

        # what this turn has done so far, for the record written at the end of it
        self._thought: List[str] = []
        self._acted: List[Dict[str, Any]] = []
        self._said: Optional[Dict[str, Any]] = None
        self._sent: List[Dict[str, Any]] = []
        # words she wrote that no tool has carried anywhere yet: the rescue
        # at the end of the turn is owed to them, and the log must be able
        # to say a turn ended mute and why
        self._unheard_words = False
        self._rescued = False
        self._pushed = False
        # shown to her mid-turn, these never come back as a turn of their own
        self._owed: set = set()
        self._bg_tasks: set = set()
        # the written answers still going out: shutdown waits for these, so a
        # conversation does not end halfway through her own sentence
        self._deliveries: set = set()
        self.turns = TurnLog(
            cc.get("turn_log_dir", "data/turns"), cc.get("turn_log_days", 14),
        ) if cc.get("turn_log", True) else None

        # a request lifecycle, not part of thinking
        self.correlations = CorrelationRegistry()

        self.tools = MindTools(surfaces, speak=self._speak, stay_silent=self._stay_silent,
                               send_text=self._send_text, react_to=self._react_to,
                               say_nothing=self._say_nothing)
        # the skill sections the promise check last looked at: it only has
        # something to say when they change, and they change rarely
        self._promised: str = ""

    def _read_knobs(self, cc: Dict[str, Any]) -> None:
        """The live knobs, read the same way at start and on every reload."""
        self._handoff_enabled = bool(cc.get("context_handoff", True))
        # ram first: the turn only marks the window dirty, and the write
        # happens behind it — never inside it
        self._persist_after_turn = bool(cc.get("window_persist_after_turn", True))
        # how long a turn waits for retrieved context before answering
        # without it: the disk must never hold the conversation hostage
        self._dynamic_timeout = float(cc.get("dynamic_context_timeout", 5.0))
        self.idle_after = cc.get("idle_after", 30.0)
        self.burst_steps = cc.get("burst_steps", 6)
        self.correlation_timeout = cc.get("correlation_timeout", 90.0)
        # whether a line starts being spoken while the model is still writing it
        self.stream_speech = bool(cc.get("stream_speech", True))

    # --- lifecycle ----------------------------------------------------------

    async def start(self):
        self.alive = True
        self._loop = asyncio.get_running_loop()
        # before the first turn, not after: the follow-up gate and the
        # cooldowns read the window, and a restart used to leave them blind to
        # a conversation that was two minutes old
        restored = self.sliding_window.restore()
        if restored:
            logger.info(f"Window restored: {restored} entr(ies) from the last run.")
        self._load_bridge()
        for s in self.surfaces.all():
            try:
                await s.start()
            except Exception as e:
                logger.error(f"Surface '{s.name}' failed to start: {e}")
        self._listen_to_the_call()
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
        logger.info(f"Surface '{name}' -> {'active' if s.active else 'inactive'}.")

    async def stop(self):
        self.alive = False
        # a written answer is handed over and not waited on, so at shutdown
        # there may be lines of it still going out at a human pace. Dropping
        # them would end a conversation halfway through her own sentence.
        await self._drain_deliveries()
        # background flushes still in flight must land first: otherwise one
        # could overwrite with an older snapshot what is flushed below
        pending = [t for t in self._persist_tasks if not t.done()]
        self._persist_tasks.clear()
        for task in pending:
            try:
                await asyncio.shield(task)
            except (asyncio.CancelledError, Exception):
                pass
        # the one synchronous write: stopping is the moment blocking on the
        # disk is correct, and this is what a restart wakes up to
        try:
            if self.sliding_window.flush():
                logger.info("Window flushed at shutdown.")
            self._save_bridge()
        except Exception as e:
            logger.warning(f"Could not flush the window at shutdown: {e}")
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
        await self._cancel_background()
        await asyncio.gather(*(self._stop_surface(s) for s in self.surfaces.all()))
        logger.info("Consciousness stopped.")

    async def _stop_surface(self, s) -> None:
        """Stops one skill without letting it hold the shutdown hostage."""
        try:
            await asyncio.wait_for(s.stop(), timeout=self._SURFACE_STOP_TIMEOUT)
        except (asyncio.TimeoutError, TimeoutError):
            logger.error(f"Surface '{s.name}' did not stop in "
                         f"{self._SURFACE_STOP_TIMEOUT:.0f}s; carrying on.")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # said out loud: a skill that fails to stop may leave a process behind
            logger.error(f"Surface '{s.name}' failed to stop: {e}")

    async def _cancel_background(self) -> None:
        """Cancels an action of hers, a profile pass or a line still playing."""
        pending = [t for t in (self._action_task, *self._bg_tasks) if t is not None and not t.done()]
        self._action_task = None
        for task in pending:
            task.cancel()
        # consumed, so none of them is reported as an exception never retrieved
        await asyncio.gather(*pending, return_exceptions=True)

    # --- HTTP correlation ---------------------------------------------------

    def register_correlation(self, route: str = "local") -> "tuple[str, asyncio.Future]":
        """Lets an HTTP caller wait for Bea's next spoken reply to its input."""
        return self.correlations.register(route)

    # --- the loop -----------------------------------------------------------

    async def run(self):
        while self.alive:
            started_over = False
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

                # written down before any gate decides it deserved a turn: what
                # she is asked about tomorrow is what happened, not what she
                # chose to answer
                self._remember(batch)

                # asleep: she stops reacting, not perceiving. The stream above
                # keeps everything for the consolidation; the window stays out
                # of it, because she is not there to experience any of it.
                if self.sleeping or not batch:
                    continue

                # texture, not events: game snapshots already live in the live
                # state, and reasoning over every heartbeat would burn the
                # budget for nothing. Everything else wakes the one loop.
                if not self._needs_mind(batch):
                    continue

                started_over = await self._run_turn(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:
                # the message alone names neither the line nor the skill it came
                # from, and this is the one place every turn fails through
                # a timeout's message is empty: the type is then all there is
                logger.error(f"Consciousness loop error: {type(e).__name__}: {e}",
                             exc_info=True)
                self.events.publish(EventCategory.ERROR, "consciousness",
                                    f"A turn failed: {type(e).__name__}: {e}")
                await asyncio.sleep(1)
            finally:
                # a turn that raised must not leave its caller hanging for the
                # whole correlation timeout. One started over is still owed its
                # answer: the same callers come back with the same batch.
                if not started_over:
                    self.correlations.release()
                await self._drop_unspoken()

    async def _run_turn(self, batch: List[Perception]) -> bool:
        """One turn, in a task the call can call off. True when it was started over.

        Waited on rather than awaited, so a turn called off from outside and the
        loop itself being stopped stay two different things.
        """
        # what `_can_start_over` reads, true of this turn from its first moment
        # rather than from wherever `_turn` gets round to resetting it
        self._batch = list(batch)
        self._thought, self._acted, self._said, self._sent = [], [], None, []
        self._owed = set()
        self._start_over = False
        task = asyncio.create_task(self._turn(batch))
        self._turn_task = task
        try:
            await asyncio.wait({task})
        except asyncio.CancelledError:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        finally:
            self._turn_task = None
        if task.cancelled():
            if not self._start_over:
                raise asyncio.CancelledError()
            # what they said so far goes back on the bus, where it waits for the
            # rest of the sentence and comes back as one turn
            for p in self._batch or batch:
                self.bus.put(p)
            return True
        error = task.exception()
        if error is not None:
            raise error
        return False

    # --- somebody in the call went on talking --------------------------------

    def _listen_to_the_call(self) -> None:
        voice = self.surfaces.get("voice:discord")
        channel = getattr(voice, "channel", None)
        if channel is not None:
            channel.on_hearing = self._on_hearing

    def _on_hearing(self, user_id: str, state: str) -> None:
        """The rest of somebody's sentence is on its way: start over, if nothing is lost.

        Only `sent` counts. A cough or a breath also starts somebody talking,
        and her line simply waits for it to be over; a turn on its way to the
        transcriber is words, and answering what came before them is answering
        half of what was meant.
        """
        if state != "sent" or not self._can_start_over():
            return
        logger.info("They kept talking before she said anything: "
                    "starting the turn over with the rest of it.")
        self._start_over = True
        if self._turn_task is not None:
            self._turn_task.cancel()

    def _can_start_over(self) -> bool:
        """Whether calling this turn off costs nothing but the thinking.

        Nothing said, nothing sent, no tool run or half way through, nothing of
        hers in the room — and the turn is about the call at all.
        """
        task = self._turn_task
        if task is None or task.done():
            return False
        if not any(p.kind == PerceptionKind.VOICE for p in self._batch):
            return False
        if self._acted or self._said is not None or self._sent:
            return False
        if self._dispatching not in (None, "speak"):
            return False
        if self.expression.is_speaking:
            return False
        return not self._line_heard(self._live)

    @staticmethod
    def _line_heard(line: Optional[LiveLine]) -> bool:
        """Whether any of this line has already left for the room."""
        if line is None:
            return False
        return bool(line.spoken) or getattr(line, "state", {}).get("seq", 0) > 0

    async def _turn(self, batch: List[Perception]) -> None:
        """One batch, one frame, one turn."""
        is_idle = all(p.kind == PerceptionKind.IDLE for p in batch)
        if not is_idle:
            logger.info(f"batch of {len(batch)} perception(s): "
                        f"{', '.join(p.surface for p in batch)}")

        # a voice input barges in on an ongoing monologue; text is just queued.
        # The call answers how far she got only once its fade is over, and the
        # frame is the one thing that needs the answer: the context is built
        # while she fades rather than after
        barge: Optional[asyncio.Task] = None
        if self.expression.is_speaking and any(p.kind == PerceptionKind.VOICE for p in batch):
            barge = asyncio.create_task(self.expression.interrupt())

        try:
            annotated = self._annotate(batch)
            t_ctx = time.perf_counter()
            system = self._system_message()
            # replayed as plain text, her past lines taught her to answer in it
            window_msgs = self.sliding_window.replay()
            briefing = await self._build_briefing(batch, is_idle=is_idle)
            if not is_idle:
                logger.info(f"context built in {(time.perf_counter() - t_ctx) * 1000:.0f}ms")
        finally:
            if barge is not None:
                await barge
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
        self._thought, self._acted, self._said, self._sent = [], [], None, []
        self._owed = set()
        self._unheard_words = False
        self._rescued = False
        last: Optional[AssistantMessage] = None
        for _ in range(self.burst_steps):
            steer = await self._steering()
            if steer:
                self.correlations.extend_batch(steer)
                self._remember(steer)
                if self._needs_mind(steer):
                    answered = self._answered()
                    still_coming = [p for p in steer if conversation_key(p) not in answered]
                    after_reply = [p for p in steer if conversation_key(p) in answered]
                    for part, after in ((still_coming, False), (after_reply, True)):
                        if not part:
                            continue
                        steered = self._annotate(part)
                        steer_frame = self._frame(steered, steering=True, after_reply=after)
                        context.append(steer_frame)
                        frames.append((steer_frame, steered))
                    self._owed |= {conversation_key(p) for p in after_reply if p.is_memorable}
                    self._batch.extend(steer)
            if not self._batch:
                break

            steps += 1
            assistant = await self._step(context, label="" if is_idle else f"step {steps}")
            last = assistant
            spent = spent + assistant.usage
            if not self._turn_is_over(assistant):
                continue
            undone = self._left_undone()
            if undone is None:
                break
            # a world still waiting on her (a game she only talked about
            # playing) gets one more step, and only one
            context.append({"role": "user", "content": undone})

        # nobody heard her: either she only wrote plain text, which is
        # private thinking, or every tool she reached for failed. Both
        # end the same way and both get the same one rescue — the
        # question is whether anything landed, never whether she tried
        owed = self._still_owed(last)
        if (self._needs_answer(batch) and not self._reached_someone()) or owed:
            # said out loud on the way in: a turn that ends mute must read as
            # a failure in the log, never as her choice to stay quiet
            self._rescued = True
            reason = (self._silence_reason() if not owed else
                      f"unanswered since her reply: {', '.join(sorted(owed))}")
            logger.warning(f"A turn reached nobody ({reason}) - asking once more.")
            context.append({"role": "user", "content": self._NO_TOOL_NUDGE})
            steps += 1
            assistant = await self._step(context)
            spent = spent + assistant.usage
            if not self._reached_someone() or self._still_owed(assistant):
                logger.error(
                    "Still unheard after the rescue: this turn ends with nobody there.")
                self.events.publish(
                    EventCategory.ERROR, "consciousness",
                    "A turn ended with words nobody heard, even after the one rescue.",
                    metadata={"thought": (self._thought or [""])[-1][:300],
                              "tools": [c["tool"] for c in self._acted]},
                )

        if not is_idle:
            elapsed_ms = (time.perf_counter() - t_turn) * 1000
            logger.info(f"turn done: {steps} llm call(s), {spent.total} tokens, "
                        f"in {elapsed_ms:.0f}ms")
            self._publish_cost(steps, spent, elapsed_ms)
            self._write_down(context, self._batch, steps, spent, elapsed_ms,
                             rescued=self._rescued)
            self._profile_background(self._batch)
        self._record_window(frames)
        self._schedule_persist()
        self._schedule_handoff()

    async def _step(self, context: List[Dict[str, Any]], label: str = "") -> AssistantMessage:
        """One model call, and every tool it asked for. `label` names it in the log."""
        self._steps_taken += 1
        self._backgrounded = set()
        t_llm = time.perf_counter()
        assistant = await self._think(context)
        if label:
            tools = (" (tools: " + ", ".join(c.name for c in assistant.tool_calls) + ")"
                     if assistant.tool_calls else " (final)")
            logger.info(f"llm {label} took {(time.perf_counter() - t_llm) * 1000:.0f}ms{tools}")
        context.append(assistant_to_message(assistant))
        self._think_aloud(assistant.content)
        # a final answer written as plain text is words nobody heard: the
        # think-aloud before a tool call is thinking, not an answer, so only
        # the final message counts - otherwise every action turn with a lively
        # inner monologue would earn a rescue it does not need
        if assistant.is_final and assistant.content and str(assistant.content).strip():
            self._unheard_words = True
        if assistant.is_final:
            return assistant

        for call in assistant.tool_calls:
            obs = await self._dispatch(call)
            context.append(tool_result_message(call, obs))
        # she started a line and then did something else with the
        # turn: nobody is going to finish it
        await self._drop_unspoken()
        return assistant

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
            return await self.llm.complete(messages, tools=self.tools.schemas())

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
            if words:
                if line is None:
                    line = self._open_line(reader.mood)
                    if line is None:
                        readers[index] = None
                        return
                    spoken = index
                line.say(words)
            # the closing quote is the end of the line. Waiting for the response
            # to finish as well held her last sentence — on a one-sentence
            # answer, all of it — behind the usage block and any tool after it
            if line is not None and spoken == index and reader.finished:
                line.close_input()

        try:
            return await self.llm.stream_complete(
                messages, tools=self.tools.schemas(), on_tool_delta=on_delta)
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

    async def _steering(self) -> List[Perception]:
        """What arrived mid-turn and still belongs to this turn.

        Something that lands while she is thinking is steering: she has not
        answered yet, and reading it now is what stops her replying to a
        question the room has already moved past. A written line that lands
        in a conversation she has **already** answered is the next thing that
        person said: it goes in at the next step too, once they have stopped
        typing, rather than waiting behind every step she has left.

        A call keeps the steering it had. Nothing there waits for a typist,
        and anything from a conversation she has answered goes back on the
        bus for the next turn; so does anything that is not written text.
        """
        in_call = any(p.kind is PerceptionKind.VOICE for p in self._batch)
        arrived = await self.bus.steer(wait_for_typing=not in_call)
        answered = self._answered()
        steer: List[Perception] = []
        for p in arrived:
            if conversation_key(p) in answered and (in_call or p.kind is not PerceptionKind.CHAT):
                self.bus.put(p)
            else:
                steer.append(p)
        return steer

    def _turn_is_over(self, assistant: AssistantMessage) -> bool:
        """Whether this step ended the turn, before any skill has had its say."""
        if assistant.is_final:
            return True
        calls = assistant.tool_calls
        # she spoke or chose silence: a new message becomes its own next turn.
        # anything else keeps the turn going, so she acts first and talks after
        if not calls:
            return False
        if all(c.name in self._TERMINAL_TOOLS for c in calls):
            return True
        # actions started in the background only answer "started": once she has
        # also spoken, in this step or before, another call would learn nothing
        spoken = self._said is not None or bool(self._sent) or any(
            c.name in self._TERMINAL_TOOLS for c in calls)
        return spoken and all(
            c.name in self._TERMINAL_TOOLS or c.id in self._backgrounded for c in calls)

    def _left_undone(self) -> Optional[str]:
        """What the active skills say is still waiting on her, once per turn."""
        if self._pushed:
            return None
        said = self.surfaces.left_undone(self._batch, self._acted)
        if not said:
            return None
        self._pushed = True
        logger.info("The turn was ending with a skill's world left waiting: one more step.")
        return "\n".join(said)

    def _still_owed(self, last: Optional[AssistantMessage]) -> set:
        """Conversations shown a line after her reply that got no answer since.

        Choosing silence for them is an answer; plain text or simply stopping
        is not.
        """
        if not self._owed or last is None:
            return set()
        if any(c.name in ("stay_silent", "say_nothing") for c in last.tool_calls):
            return set()
        return set(self._owed)

    @property
    def turn_batch(self) -> List[Perception]:
        """What the turn in progress is answering.

        For a tool that finishes after its turn is over: its result has to come
        back to the conversation that asked, not to wherever she is by then.
        """
        return list(self._batch)

    def _answered(self) -> set:
        """The conversations she has already replied in, this turn."""
        keys = {f"{sent['platform']}:{sent['channel']}" for sent in self._sent}
        if self._said:
            keys.add(STAGE)
        return keys

    # --- attention: order, never filter -------------------------------------

    @staticmethod
    def _needs_mind(batch: List[Perception]) -> bool:
        """Does this batch deserve a reasoning cycle at all.

        Texture the loop already sees elsewhere (a game snapshot flagged as
        noise, already carried by the live state) does not wake the model.
        Everything else — chat from anywhere, voice, events, idle, system —
        enters the one frame.
        """
        return any(not p.is_noise for p in batch)

    @staticmethod
    def _needs_answer(batch: List[Perception]) -> bool:
        """Could someone be waiting on words, as opposed to texture or time."""
        return any(p.is_memorable for p in batch)

    def _silence_reason(self) -> str:
        """What went wrong with the turn, in the words the log should carry."""
        tools = ", ".join(str(c["tool"]) for c in self._acted) or "no tool"
        if self._unheard_words:
            return f"plain text nobody heard (tools: {tools})"
        if self._acted and all(_tool_failed(c) for c in self._acted):
            return f"every tool failed ({tools})"
        failed_audience = [str(c["tool"]) for c in self._acted
                           if bool(c.get("reaches")) and _tool_failed(c)]
        if failed_audience:
            return f"audience tool failed ({', '.join(failed_audience)}; tools: {tools})"
        return f"nothing landed (tools: {tools})"

    def _reached_someone(self) -> bool:
        """Did anything she did this turn actually get to somebody.

        Landing means output: she said or wrote it, or a tool that declares it
        reaches an audience (a react, `mc_chat`, `discord_send_message`) did.
        Everything else she can reach for - a plan objective, a body action,
        a recall - is something she *did*, and must never stand in for the
        answer she has not given yet.
        """
        if self._said or self._sent:
            return True
        if any(bool(c.get("reaches")) and not _tool_failed(c) for c in self._acted):
            return True
        if self._unheard_words:
            return False
        if any(bool(c.get("reaches")) and _tool_failed(c) for c in self._acted):
            return False
        # side effects only: she acted and kept quiet, which is her right -
        # nothing of hers is waiting to be delivered, so there is no rescue
        return any(not _tool_failed(c) for c in self._acted)

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
        # what she thought rather than said, when the provider reports it: it is
        # the difference between a long answer and a long silence before one
        thought = f", {spent.reasoning_tokens} reasoning" if spent.reasoning_tokens else ""
        self.events.publish(
            EventCategory.SYSTEM, "cost",
            f"turn: {steps} call(s), {spent.total} tokens, {elapsed_ms:.0f}ms{cached}{thought}",
            metadata={
                "steps": steps,
                "prompt_tokens": spent.prompt_tokens,
                "completion_tokens": spent.completion_tokens,
                "cached_tokens": spent.cached_tokens,
                "reasoning_tokens": spent.reasoning_tokens,
                "tokens": spent.total,
                "ms": round(elapsed_ms),
                "session_tokens": self.total_tokens,
                "session_calls": self.total_calls,
            },
        )

    def _think_aloud(self, content: Optional[str]) -> None:
        """Her inner monologue: shown live, and kept for the record.

        Plain text is private thinking — nobody hears it, and every token of it
        is a token of delay before she says anything. Keeping it is what makes
        "why did she go quiet" and "why was that turn slow" answerable after
        the fact instead of the following stream.
        """
        if not content:
            return
        self._thought.append(content)
        self.events.publish(EventCategory.THOUGHT, "consciousness", content)

    def _write_down(self, context: List[Dict[str, Any]], batch: List[Perception],
                    steps: int, spent: Usage, elapsed_ms: float,
                    rescued: bool = False) -> None:
        """Files the turn away, for the questions that only come up afterwards."""
        if self.turns is None or not self.turns.enabled:
            return
        try:
            self.turns.write(turn_record(
                context=context,
                perceptions=[p.render() for p in batch],
                thought=self._thought,
                calls=self._acted,
                spoke=self._heard(),
                usage=spent,
                steps=steps,
                ms=elapsed_ms,
                model=getattr(self.llm, "model_name", "") or "",
                rescued=rescued,
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
        """Builds it off the loop: a slow retrieval must not stall speech.

        Bounded, not just background: if the disk hangs, the turn goes on
        without the retrieved block rather than late with it.
        """
        dynamic: List[str] = []
        if batch:
            try:
                dynamic = await asyncio.wait_for(
                    asyncio.to_thread(self.surfaces.dynamic_context, batch),
                    timeout=self._dynamic_timeout)
            except asyncio.TimeoutError:
                logger.warning("Dynamic context timed out; answering without it.")
            except Exception as e:
                logger.warning(f"Dynamic context failed; answering without it: {e}")
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
        self._check_promises(sections)
        # right after who she is, and in the cached half on purpose: which
        # language to answer in is true for the whole session, and a Japanese
        # line came back in English 5 times out of 8 without it — the prompt
        # around it is ~16k characters of English and outweighed one message
        language = directive(getattr(self.config, "language", ""))
        return {"role": "system",
                "content": compose(self._get_soul(), language,
                                   self._get_operating(), *sections)}

    def _check_promises(self, sections: List[str]) -> None:
        """Complains when a skill offers her a tool the schema does not carry.

        Only the code-generated sections, never the soul or the manual: those
        are files somebody edits, and naming a tool from a capability that is
        switched off is their business. A skill describing a door she is not
        given is always a bug, and it is the kind that only shows up once the
        world moves — she joins a call, the owner writes the plan.
        """
        promised = "\n".join(sections)
        if promised == self._promised:
            return
        self._promised = promised
        missing = unarmed(promised, self.tools.names())
        if missing:
            logger.error(
                f"The prompt offers tools the mind has not been given: "
                f"{', '.join(missing)}. She will call them and be told they do not exist.")

    def _briefing(self, batch: List[Perception], is_idle: bool = False,
                  dynamic: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Everything that is only true right now, as one block she is told once.

        It sits directly above the perceptions it describes and is taken back out
        at the end of the turn: what she was told about this moment is not part
        of the conversation, and leaving it in would have her answering a memory
        retrieved for a question somebody asked ten minutes ago.

        The clock lives in exactly one place — `ClockSkill.live_state()`, which
        already carries the day, the time and the configured zone. A second date
        line here used the machine clock instead, so the two disagreed around
        midnight in a UTC container.
        """
        parts: List[str] = []

        # whether anyone has written to her is something the loop knows, so it
        # is told rather than inferred: the system prompt only ever says to
        # mirror, and this is the turn where there is nobody to mirror
        if not any(p.author for p in batch):
            opening = speaks_first(getattr(self.config, "language", ""))
            if opening:
                parts.append(opening)

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
               steering: bool = False, after_reply: bool = False) -> Dict[str, Any]:
        """The one frame: everything that arrived, tagged with where it came from.

        One turn, one frame per batch: a telegram DM and a minecraft death are
        read together, ordered by priority. The `[via ...]` tag is the
        transplanted `place_header` — deterministic self-awareness of where she
        is and with whom, injected from code rather than hoped from prose — and
        the destination a `send_message` must name back.
        """
        if after_reply:
            header = ("[NEW MESSAGE — arrived after you already replied in this "
                      "conversation: it is the next thing they said. Answer it where "
                      "it arrived, once; do not repeat what you already sent.]")
        elif steering:
            header = ("[STILL COMING IN — this arrived while you were mid-action, "
                      "and you have not answered it yet. Fold it into the answer you "
                      "are about to give; do not send a separate reply for it.]")
        else:
            header = "[PERCEPTIONS — answer where each arrived: `speak` for voice/stage, `send_message(platform, channel, text)` for the rest]"
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
        if key == STAGE:
            if p.kind is PerceptionKind.VOICE:
                return "via voice call"
            if p.surface == "chat:ui":
                return "via dashboard"
            if p.kind is PerceptionKind.GAME or p.surface == "game:mc":
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
            if key == STAGE or key in seen:
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

    async def _dispatch(self, call: ToolCall) -> str:
        """Runs one tool and says, on the record, how it went.

        The call and its outcome are one event, published once the outcome is
        known. Published on the way in, a tool that came back
        `ERROR: unknown tool` looked on the dashboard exactly like one that
        worked, which is the worst possible thing for the log to be doing while
        a capability is quietly missing.
        """
        registry = self.tools.registry()
        self._dispatching = call.name
        try:
            result = await self._run_tool(call, registry)
        finally:
            self._dispatching = None
        tool = registry.get(call.name)
        self._acted.append({"tool": call.name, "arguments": call.arguments,
                            "result": result,
                            # whether this could stand in for an answer: a tool
                            # that talks to an audience declares it, a tool that
                            # merely does something does not
                            "reaches": bool(getattr(tool, "reaches", False))})
        failed = result.startswith(("ERROR", "FAILED"))
        self.events.publish(
            EventCategory.ERROR if failed else EventCategory.TOOL, "consciousness",
            f"{call.name}({call.arguments}) → {result}" if failed
            else f"{call.name}({call.arguments})",
            metadata={"tool": call.name, "arguments": call.arguments, "result": result},
        )
        return result

    async def _run_tool(self, call: ToolCall, registry=None) -> str:
        registry = registry if registry is not None else self.tools.registry()
        tool = registry.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool '{call.name}'."

        if tool.long_running:
            self._backgrounded.add(call.id)
            return self._start_action(tool, call.arguments)

        return await registry.dispatch(call)

    def _start_action(self, tool: Tool, args: Dict[str, Any]) -> str:
        """Starts an action that takes time, beside her.

        One pair of hands: what she asks for in the same step is done in that
        order, and a later decision replaces whatever is still going.
        """
        running = self._action_task is not None and not self._action_task.done()
        if running and self._action_step == self._steps_taken:
            self._action_queue.append((tool, args))
            return f"{tool.name} queued: you do it right after the one before."
        if running and self._action_task is not None:
            self._action_task.cancel()
        self._action_step = self._steps_taken
        self._action_queue = [(tool, args)]
        self._action_task = asyncio.create_task(self._run_actions(self._action_queue))
        return f"{tool.name} started (running in the background; its result will reach you as a perception)."

    async def _run_actions(self, queue: List[Tuple[Tool, Dict[str, Any]]]):
        """Does each queued action in turn and reports them together once over.

        One report, not one per action: each would wake her mid-sequence, and a
        new decision there would cancel the rest of what she had just asked for.
        """
        lines: List[str] = []
        surface = queue[0][0].surface if queue else ""
        index = 0
        while index < len(queue):
            tool, args = queue[index]
            index += 1
            try:
                result = tool.handler(**args)
                if asyncio.iscoroutine(result):
                    result = await result
            except asyncio.CancelledError:
                return
            except Exception as e:
                result = f"ERROR: {e}"
            lines.append(f"[{tool.name}] result: {result}")
            if _went_wrong(str(result)) and index < len(queue):
                rest = ", ".join(t.name for t, _ in queue[index:])
                lines.append(f"not done: {rest} (after the failure above)")
                break
        # attributed to the surface that owns the tool, not to minecraft
        self.bus.put(Perception(
            PerceptionKind.ACTION, surface or "body", "\n".join(lines), salience=0.7,
        ))

    # --- speaking (non-blocking) -------------------------------------------

    async def _speak(self, mood: str, message: str) -> str:
        # whatever of this line is already on its way out. Taken here rather than
        # in the loop so the two can never both own it.
        line, self._live = self._live, None
        kept_heard: Optional[str] = None
        if line is not None and line.spoiled:
            # she met her own scaffolding before a word was heard: throw the
            # line away and say the finished message, which cleans whole
            await line.cancel()
            line = None
        if line is not None and not line.tainted and line.written != message:
            # a model that died mid-line was answered for by another; a tainted line is short on purpose.
            # the two texts are logged because this path pays for the line twice, and a
            # drift between what streamed and what settled is otherwise invisible
            if line.spoken:
                # something of the dead model's line is already in the room. Saying
                # the settled answer whole now would have the room hear half of one
                # sentence and then all of another; the line it heard stands, and the
                # drift is an error because the mind will believe it said the other
                logger.error(
                    "The line on its way out is not the one she settled on, and it was "
                    f"already heard; keeping what streamed (streamed {line.written[:60]!r}, "
                    f"settled {message[:60]!r}).")
                kept_heard = line.spoken or line.written
            else:
                logger.warning(
                    "The line on its way out is not the one she settled on; saying hers "
                    f"(streamed {line.written[:60]!r}, settled {message[:60]!r}).")
                await line.cancel()
                line = None

        # nothing of it has reached the room yet: while somebody is still
        # talking it waits, before it becomes something she said — so the turn
        # can still be started over with the rest of their sentence, and there
        # is nothing to take back from her history when it is
        if not self._line_heard(line):
            try:
                await self.expression.wait_for_floor()
            except asyncio.CancelledError:
                if line is not None:
                    await line.cancel()
                raise

        # the model invents moods; an avatar that silently fails to change is
        # worse than landing on the nearest one she actually has
        mood = normalize_mood(mood)
        # redundant with the client-side clean: last gate before the audience
        message = clean_model_output(message)
        if kept_heard:
            # the room heard the streamed line, not the fallback's answer: the
            # history, the window and the turn log must believe what was heard
            heard = clean_model_output(kept_heard) or kept_heard.strip()
            if heard:
                message = heard
        if not message:
            logger.warning("speak() had nothing left after sanitizing; staying silent.")
            if line is not None:
                await line.cancel()
            return await self._stay_silent("nothing sayable")
        if self.attention:
            self.attention.mark_spoke()
        self.history.add_message("assistant", message, mood=mood, source="consciousness")
        self._remember_spoken(message)
        self.events.publish(EventCategory.OUTPUT, "consciousness", message, metadata={"mood": mood})
        self._said = {"mood": mood, "message": message}
        self._owed.discard(STAGE)

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
                self._in_background(self._finish_line(line))
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
            self._in_background(self._speak_local_safe(mood, message, feeling))

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
        return self.tools.writer(platform)

    async def _send_text(self, platform: str, channel: str, text: str,
                         reply_to: str = "") -> str:
        """Writes where it arrived. The destination rides in the arguments.

        Handed to the platform and not waited on. Every line is sent with a
        typing pause in front of it — up to four seconds each, on purpose, so
        it reads like somebody writing — and waiting for that inside the tool
        call held the whole mind for as long as the answer was long. A turn
        answering three lines sat there for ten seconds while everything that
        arrived in the meantime piled up behind it. Her voice has worked this
        way since it existed; this is the written half catching up.
        """
        skill = self._skill_for_platform(platform)
        if skill is None:
            return (f"FAILED: no active skill for platform '{platform}'. "
                    f"Use speak for voice/stage.")
        messages = skill.message_count(text)
        if not messages:
            return "FAILED: there was nothing to send."

        key = f"{platform}:{channel}"
        self._sent.append({"platform": platform, "channel": str(channel), "text": text})
        self._owed.discard(key)
        if self.attention:
            self.attention.mark_spoke(key)
        self._log_outgoing(key, platform, str(channel), text)
        task = self._in_background(self._deliver(skill, platform, str(channel), text,
                                                  reply_to or None))
        self._deliveries.add(task)
        task.add_done_callback(self._deliveries.discard)
        return f"Sending ({messages} message(s))."

    async def _deliver(self, skill, platform: str, channel: str, text: str,
                       reply_to: Optional[str]) -> None:
        """One written answer, out at a human pace, off the mind's clock."""
        try:
            sent = await skill.deliver(channel, text, reply_to=reply_to)
        except Exception as e:
            sent = []
            logger.warning(f"send_message to {platform}:{channel} failed: {e}")
        if sent:
            return
        # she has been told it went; the only honest thing left is to say so
        # where somebody can see it
        self.events.publish(
            EventCategory.ERROR, "consciousness",
            f"Nothing reached {platform}:{channel} — the message was lost.",
            metadata={"platform": platform, "channel": channel, "text": text},
        )

    async def _react_to(self, platform: str, channel: str, message_id: str,
                        emoji: str) -> str:
        skill = self._skill_for_platform(platform)
        if skill is None:
            return f"FAILED: no active skill for platform '{platform}'."
        if not skill.supports_reactions:
            return f"FAILED: reactions are switched off on {platform}; write instead."
        try:
            ok = await skill.react(str(channel), str(message_id), emoji)
        except Exception as e:
            return f"FAILED: {e}"
        if ok:
            self._owed.discard(f"{platform}:{channel}")
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
                    content = (f"({p.kind.value.upper()}) [{self._provenance(p)}] "
                               f"{p.render(now=now, kept=True)}")
                    self.sliding_window.append("user", content, key=key, author=author)
            for sent in self._sent:
                key = f"{sent['platform']}:{sent['channel']}"
                self.sliding_window.append("assistant", sent["text"], key=key,
                                           addressee=self._addressee_for(key))
            if self._said and self._said.get("message"):
                self.sliding_window.append("assistant", str(self._said["message"]),
                                           key=STAGE, mood=str(self._said.get("mood", "")))
        except Exception as e:
            logger.warning(f"Could not mirror the turn into the window: {e}")

    @property
    def _session_id(self) -> str:
        """The sitting this all belongs to, for the consolidation to read back."""
        return str(getattr(self.history, "session_id", "") or "")

    def _remember(self, batch: List[Perception]) -> None:
        """The stream, written down as it leaves the bus.

        Append-only and durable: the dream, recall and the dashboard read it,
        and no context is ever built from it. One transaction per drain, not
        one per row: N small commits would serialize the conversation behind
        fsyncs, and the dream reads this minutes later — never mid-turn.
        """
        session = self._session_id
        try:
            fresh = [p for p in batch
                     if p.is_memorable and p.id not in self._stream_ids]
            entries = []
            for p in fresh:
                author = p.author
                entries.append({
                    "conversation_key": conversation_key(p),
                    "role": "user" if author else "world",
                    "kind": p.kind.value, "surface": p.surface, "content": p.kept,
                    "platform": author.platform if author else "",
                    "channel_id": str((p.meta or {}).get("channel_id", "")),
                    "author_identity": author.identity if author else None,
                    "display_name": author.display_name if author else "",
                    "session_id": session, "ts": p.ts,
                })
            self.memory.conversations.add_many(entries)
            for p in fresh:
                self._stream_ids[p.id] = None
        except Exception as e:
            logger.warning(f"Could not write the stream down: {e}")
        if len(self._stream_ids) > _STREAM_ID_CAP:
            for old in list(self._stream_ids)[: len(self._stream_ids) - _STREAM_ID_CAP]:
                del self._stream_ids[old]

    def _remember_spoken(self, message: str) -> None:
        """Her voice belongs in the same stream as everything she heard."""
        try:
            self.memory.conversations.add(
                conversation_key=STAGE, role="bea", kind="voice", surface="stage",
                content=message, display_name="bea",
                addressee_identity=self._addressee_for(STAGE),
                session_id=self._session_id,
            )
        except Exception as e:
            logger.warning(f"Could not write down what she said: {e}")

    def _log_outgoing(self, key: str, platform: str, channel: str, text: str) -> None:
        """Her written lines, next to what she was answering."""
        try:
            self.memory.conversations.add(
                conversation_key=key, role="bea", kind="chat", surface=f"chat:{platform}",
                content=text, platform=platform, channel_id=channel, display_name="bea",
                addressee_identity=self._addressee_for(key),
                session_id=self._session_id,
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

        self._in_background(work())

    async def _drain_deliveries(self) -> None:
        """Lets the messages still on their way out finish, within reason."""
        pending = [t for t in self._deliveries if not t.done()]
        if not pending:
            return
        logger.info(f"Waiting for {len(pending)} message(s) still being sent.")
        done, late = await asyncio.wait(pending, timeout=self._DELIVERY_GRACE)
        del done
        for task in late:
            task.cancel()
        if late:
            logger.warning(f"{len(late)} message(s) were still being sent at shutdown.")

    def _in_background(self, coroutine) -> "asyncio.Task":
        """Runs something the turn should not wait for, and keeps a reference.

        Without the reference the task is only referred to by the event loop
        and may be collected mid-flight, which is a message that silently
        never goes out.
        """
        task = asyncio.create_task(coroutine)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def _schedule_persist(self) -> None:
        """Carries the ram window over to the disk, behind the turn.

        The snapshot is built on the loop thread — plain data, no io — and
        the single transaction runs elsewhere. Each snapshot takes a rising
        write seq as it is built, so one that was overtaken — by a swap, by a
        later turn, by the shutdown flush — is dropped by the store instead of
        landing on top of what overtook it.
        """
        if not self._persist_after_turn or not self.sliding_window.needs_flush:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # not now; shutdown flushes what is left
        snapshot = self.sliding_window.flush_snapshot()
        if snapshot is None:
            return
        rows, version, write_seq = snapshot

        async def work() -> None:
            try:
                written = await asyncio.to_thread(
                    self.memory.window.replace, rows, version, write_seq=write_seq)
                if not written:
                    self.sliding_window.mark_dirty()
            except asyncio.CancelledError:
                self.sliding_window.mark_dirty()
                raise
            except Exception as e:
                logger.warning(f"Background window persist failed: {e}")
                self.sliding_window.mark_dirty()

        task = self._in_background(work())
        self._persist_tasks.add(task)
        task.add_done_callback(self._persist_tasks.discard)

    def _save_bridge(self) -> None:
        """Mirrors the handoff recap to disk. A restart restores it in start()."""
        try:
            prose = self._handoff.last_prose or ""
            if prose:
                self.memory.db.put_setting(HANDOFF_PROSE_KEY, prose)
            else:
                self.memory.db.drop_setting(HANDOFF_PROSE_KEY)
        except Exception as e:
            logger.warning(f"Could not save the handoff bridge: {e}")

    def _load_bridge(self) -> None:
        """Restores the handoff recap saved by _save_bridge, if any."""
        try:
            prose = self.memory.db.get_setting(HANDOFF_PROSE_KEY)
            self._handoff.last_prose = str(prose or "")
        except Exception as e:
            logger.warning(f"Could not restore the handoff bridge: {e}")

    def forget_window(self, bridge: str = "") -> None:
        """Empties the one window, leaving the bridge the consolidation wrote.

        The single caller is the dream: sleeping is what starts her over, and
        nothing else in the system is allowed to take the evening away from
        her. A pending handoff is cancelled first — landing a swap onto a
        window that has just been emptied would put the evening back.
        """
        if self._handoff_task and not self._handoff_task.done():
            self._handoff_task.cancel()
            self._handoff_task = None
        self._handoff.last_prose = ""
        self._save_bridge()
        self.sliding_window.clear(bridge)
        logger.info("Window cleared by the consolidation.")

    def apply_budget(self) -> None:
        """Re-reads the live knobs from the config and resizes the window.

        Called on every reload, so a ceiling changed in the dashboard takes
        effect on the next turn rather than at the next restart. Everything
        runs inside `resize` on the loop thread: the resize may evict, and an
        eviction racing an append would lose the running total. A caller on
        another thread has it posted to the loop; with no loop to post to
        (start-up, tests) it runs inline.
        """
        def resize() -> None:
            cc = self.config.consciousness
            budget, hot = budget_from_config(cc)
            self._read_knobs(cc)
            if self.sliding_window.retarget(budget, hot):
                logger.info(
                    f"Window resized: ceiling {budget.max_tokens:,}, handoff at "
                    f"{budget.trigger_tokens:,}, hot {self.sliding_window.hot_tokens:,}."
                )
                # a ceiling raised past the trigger can leave a window that is
                # already due for one: ask now instead of waiting for a turn
                self._schedule_handoff()

        loop = self._loop
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if loop is None or loop.is_closed() or running is loop:
            resize()
            return
        loop.call_soon_threadsafe(resize)

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
                self._save_bridge()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Window handoff failed: {e}")

        self._handoff_task = asyncio.create_task(work())
