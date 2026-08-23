"""A scoped turn: Bea answering in one channel, without taking the stage.

One mind, several threads of conversation. "One mind" is a constraint on
*identity* — the same soul, the same self-lore, the same people, the same
memory — not on *concurrency*. A real person holds a conversation at the bar and
answers a message on their phone; the mind is one, the threads are several.

What a scoped turn deliberately does NOT get:

- **`speak`** — this is not the stage. Answering a written message out loud was a
  real failure mode (B5); here it is impossible by construction rather than by
  a rule in the prompt that a model can ignore.
- **body actions** — the game is the live loop's business.
- **the live loop's context** — it gets its own, built from this conversation.
  Cross-awareness is one line each way, on purpose: start pouring context between
  turns and you are back to one giant shared context, with more machinery.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool, ToolRegistry
from src.core.agent.types import AssistantMessage
from src.core.events import EventCategory
from src.core.mind.routing import channel_of, platform_of
from src.core.perception.types import Perception
from src.utils.logger import get_logger
from src.utils.prompts import compose

logger = get_logger("bea.mind.conversation")

# how many past messages of this channel go into the turn
HISTORY_LIMIT = 16

# a scoped turn is a reply, not an expedition: it needs far fewer steps than
# the live loop, which also has a body to drive
MAX_STEPS = 3

CONVERSATION_RULES = """## THIS IS A WRITTEN CONVERSATION
You are reading and answering messages in one specific place. You are NOT on
stage here: you have no voice in this turn, and no body — just text.

- Answer with the tools you have (`reply`, `send_message`, `react`). Anything you
  write as plain text is private thinking, and nobody sees it.
- Every LINE you send becomes its own message, with a typing pause between them.
  Write like you text: short lines, one thought each.
- You are not obliged to answer. `say_nothing` is a real option, and often the
  right one — a person does not reply to everything.
- Whatever you are doing elsewhere keeps happening; you are just also on your
  phone."""


INITIATIVE_FRAME = """[NOBODY IS TALKING TO YOU]
Nothing new here — this one has just gone quiet, and you thought of it. If there
is something you actually want to say, say it: pick up something from earlier,
ask about a thing someone left hanging, complain about your day.

If nothing genuinely comes to mind, `say_nothing`. Posting for the sake of it is
worse than staying quiet, and everyone can tell the difference."""


class ConversationMind:
    """Runs scoped conversation turns and remembers one line about each."""

    def __init__(self, *, config, llm, memory, surfaces, soul_getter, operating_getter,
                 scheduler, event_manager=None, profiler=None, now_line=None,
                 attention=None):
        self.config = config
        self.llm = llm
        self.memory = memory
        self.surfaces = surfaces
        self.scheduler = scheduler
        self.events = event_manager
        self.profiler = profiler
        self.attention = attention
        self._get_soul = soul_getter
        self._get_operating = operating_getter
        # one line describing what the live loop is up to, injected into a turn
        self._now_line = now_line or (lambda: "")

        cc = getattr(config, "consciousness", {}) or {}
        self.history_limit = int(cc.get("conversation_history", HISTORY_LIMIT))
        self.max_steps = int(cc.get("conversation_steps", MAX_STEPS))

        # what she just did elsewhere, for the live loop's cross-awareness
        self._recent: List[str] = []
        self._pending: Dict[str, List[Perception]] = {}
        self._tasks: set = set()

    # --- entry point --------------------------------------------------------

    def dispatch(self, key: str, perceptions: List[Perception]) -> None:
        """Queues perceptions for `key` and makes sure a turn is running.

        Fire-and-forget on purpose: the live loop must never block waiting for a
        conversation in another channel.
        """
        if not perceptions:
            return
        self._pending.setdefault(key, []).extend(perceptions)
        self._record_incoming(key, perceptions)

        task = asyncio.create_task(self._run(key))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def turn_now(self, key: str, perceptions: List[Perception], *,
                       first: bool = True, initiative: bool = False) -> None:
        """Queues and runs one turn, awaiting it.

        The awaitable twin of `dispatch`, for callers that need the reply to have
        landed before they continue. With `initiative` she may open the
        conversation herself, with nothing new to answer.
        """
        if perceptions:
            self._pending.setdefault(key, []).extend(perceptions)
            self._record_incoming(key, perceptions)
        await self.scheduler.submit(
            key, lambda first_run: self.turn(key, first=first_run, initiative=initiative)
        )

    async def _run(self, key: str) -> None:
        try:
            await self.scheduler.submit(key, lambda first: self.turn(key, first=first))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Conversation turn '{key}' failed: {e}")

    async def drain(self, timeout: float = 5.0) -> None:
        """Waits for the turns in flight, including ones not yet started.

        `dispatch` is fire-and-forget: waiting only on the scheduler would return
        immediately for a turn whose task has not had a chance to run yet.
        """
        if self._tasks:
            await asyncio.wait(set(self._tasks), timeout=timeout)
        await self.scheduler.drain(timeout)

    # --- the turn -----------------------------------------------------------

    async def turn(self, key: str, *, first: bool = True, initiative: bool = False) -> None:
        incoming = self._pending.pop(key, [])
        if not incoming and first and not initiative:
            return

        skill = self._skill_for(key)
        if skill is None:
            logger.warning(f"No active skill can answer '{key}'.")
            return

        tools = self._tools(skill, key, incoming)
        if not tools:
            logger.warning(f"No tools available for '{key}'; skipping the turn.")
            return

        context = await asyncio.to_thread(self._build_context, key, incoming, first, initiative)
        sent = await self._reason(key, context, tools)

        if sent:
            self._record_outgoing(key, sent)
        self._schedule_background(key, incoming)

    async def _reason(self, key: str, context: List[Dict[str, Any]],
                      registry: ToolRegistry) -> List[str]:
        schemas = registry.schemas() or None
        sent: List[str] = []

        for _ in range(self.max_steps):
            assistant: AssistantMessage = await self.llm.complete(context, tools=schemas)
            context.append(_assistant_message(assistant))
            if assistant.content and self.events:
                self.events.publish(EventCategory.THOUGHT, f"conversation:{key}",
                                    assistant.content)
            if assistant.is_final:
                break

            terminal = False
            for call in assistant.tool_calls:
                if self.events:
                    self.events.publish(EventCategory.TOOL, f"conversation:{key}",
                                        f"{call.name}({call.arguments})")
                observation = await registry.dispatch(call)
                context.append({"role": "tool", "tool_call_id": call.id,
                                "name": call.name, "content": observation})
                if call.name in ("reply", "send_message"):
                    text = str(call.arguments.get("text", "")).strip()
                    if text and not observation.startswith("FAILED"):
                        sent.append(text)
                if call.name in ("reply", "send_message", "say_nothing"):
                    terminal = True
            if terminal:
                break
        return sent

    # --- context ------------------------------------------------------------

    def _build_context(self, key: str, incoming: List[Perception],
                       first: bool, initiative: bool = False) -> List[Dict[str, Any]]:
        """The system message for a scoped turn. Runs off the loop: it queries
        the database and may embed."""
        parts = [
            f"CURRENT DATE: {time.strftime('%Y-%m-%d')}",
            self._get_soul(),
            self._get_operating(),
            CONVERSATION_RULES,
        ]

        who = self._who(incoming)
        if who:
            parts.append(who)

        recalled = self._recall(incoming)
        if recalled:
            parts.append(recalled)

        summary = self.memory.conversations.summary(key)
        if summary:
            parts.append(f"[WHAT THIS CONVERSATION HAS BEEN ABOUT]\n{summary}")

        # cross-awareness, one line: enough to be coherent, not enough to bleed
        now = (self._now_line() or "").strip()
        if now:
            parts.append(f"[WHAT YOU'RE DOING RIGHT NOW]\n{now}")

        messages: List[Dict[str, Any]] = [{"role": "system", "content": compose(*parts)}]

        # the incoming messages were already written to history (the coalescing
        # re-run needs them there), so they are trimmed off the tail here — they
        # come back below as an explicit frame instead of appearing twice
        history = self.memory.conversations.history(
            key, limit=self.history_limit + len(incoming)
        )
        if incoming:
            history = history[: -len(incoming)]
        for entry in history[-self.history_limit:]:
            if entry["role"] == "bea":
                messages.append({"role": "assistant", "content": entry["content"]})
            else:
                name = entry["display_name"] or "someone"
                messages.append({"role": "user", "content": f"[{name}] {entry['content']}"})

        if incoming:
            header = "[NEW MESSAGES]" if first else \
                "[MORE ARRIVED WHILE YOU WERE WRITING — answer everything at once]"
            lines = "\n".join(p.render() for p in incoming)
            messages.append({"role": "user", "content": f"{header}\n{lines}"})
        elif initiative:
            messages.append({"role": "user", "content": INITIATIVE_FRAME})
        return messages

    def _who(self, incoming: List[Perception]) -> str:
        cards = {}
        for p in incoming:
            if p.author is None or p.author.is_owner:
                continue
            card = self.memory.people.get_by_identity(p.author.identity)
            if card:
                cards[card.person_id] = card
        if not cards:
            return ""
        lines = "\n".join(c.render() for c in list(cards.values())[:5])
        return f"[WHO YOU'RE TALKING TO]\n{lines}"

    def _recall(self, incoming: List[Perception]) -> str:
        rag = getattr(self.memory, "rag", None)
        if rag is None or not incoming:
            return ""
        query = " ".join(p.content for p in incoming)
        try:
            facts, hers = rag.recall_split(query, scope="diary", k=2)
        except Exception as e:
            logger.warning(f"Recall failed for a conversation turn: {e}")
            return ""
        blocks = []
        if facts:
            blocks.append("[LONG TERM MEMORY]\n" + "\n".join(f"- {r.render()}" for r in facts))
        if hers:
            blocks.append(
                "[THINGS YOU SAID BEFORE — your own past lines, not established facts]\n"
                + "\n".join(f"- {r.text}" for r in hers)
            )
        return "\n\n".join(blocks)

    # --- tools --------------------------------------------------------------

    def _skill_for(self, key: str):
        platform = platform_of(key)
        for skill in self.surfaces.active():
            if getattr(skill, "platform", None) == platform:
                return skill
        return None

    def _tools(self, skill, key: str, incoming: List[Perception]) -> Optional[ToolRegistry]:
        channel = channel_of(key)
        reply_to = next((p.meta.get("message_id") for p in reversed(incoming)
                         if p.meta.get("message_id")), None)

        registry = ToolRegistry()
        for tool in skill.conversation_tools(channel, reply_to=reply_to):
            registry.register(tool)
        if not len(registry):
            return None

        social = self.surfaces.get("social")
        if social is not None and social.active:
            for tool in social.tools():
                if tool.name == "remember_person":
                    registry.register(tool)

        registry.add(
            "say_nothing",
            "Decide this doesn't need an answer from you. Perfectly normal — a "
            "person doesn't reply to everything.",
            {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
            lambda reason="": "Said nothing.",
        )
        return registry

    # --- bookkeeping --------------------------------------------------------

    def _record_incoming(self, key: str, perceptions: List[Perception]) -> None:
        for p in perceptions:
            author = p.author
            self.memory.conversations.add(
                conversation_key=key, role="user",
                content=_strip_prefix(p.content, author.display_name if author else ""),
                platform=platform_of(key), channel_id=channel_of(key) or "",
                author_identity=author.identity if author else None,
                display_name=author.display_name if author else "",
                ts=p.ts,
            )

    def _record_outgoing(self, key: str, sent: List[str]) -> None:
        for text in sent:
            self.memory.conversations.add(
                conversation_key=key, role="bea", content=text,
                platform=platform_of(key), channel_id=channel_of(key) or "",
                display_name="Bea",
            )
        if self.attention:
            # scoped: answering in one channel is not a reason to go quiet everywhere
            self.attention.mark_spoke(key)
        # one line for the live loop, so she knows what she just did elsewhere
        self._recent.append(f"{key}: you replied — {_clip(sent[-1])}")
        self._recent = self._recent[-5:]

    def _schedule_background(self, key: str, incoming: List[Perception]) -> None:
        """Profile and summarize AFTER answering, so neither is ever in the way."""
        if self.profiler is None:
            return
        identities = {p.author.identity for p in incoming if p.author}

        async def work():
            try:
                await self.profiler.maybe_summarize(key)
                for identity in identities:
                    await self.profiler.maybe_profile(identity)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Background pass for '{key}' failed: {e}")

        task = asyncio.create_task(work())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def recent_lines(self, max_lines: int = 3) -> str:
        """`[OTHER CONVERSATIONS]` for the live loop. Consumed on read."""
        if not self._recent:
            return ""
        lines = self._recent[-max_lines:]
        self._recent = []
        return "[ELSEWHERE, JUST NOW]\n" + "\n".join(f"- {line}" for line in lines)


def _assistant_message(msg: AssistantMessage) -> Dict[str, Any]:
    import json
    out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": c.id, "type": "function",
             "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
            for c in msg.tool_calls
        ]
    return out


def _strip_prefix(content: str, name: str) -> str:
    """Drops the rendered "[marco] (discord text, channel_id=…): " routing prefix.

    The history is per-channel and already carries the author, so repeating the
    ids in every stored line is noise that the model would learn to imitate.
    """
    if not name:
        return content
    marker = "): "
    if content.startswith(f"[{name}]") and marker in content:
        return content.split(marker, 1)[1]
    prefix = f"[{name}] "
    return content[len(prefix):] if content.startswith(prefix) else content


def _clip(text: str, limit: int = 60) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


__all__ = ["ConversationMind", "Tool", "CONVERSATION_RULES"]
