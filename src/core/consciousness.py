import asyncio
import datetime
import uuid
from typing import Any, Dict, List, Optional

from src.core.agent.tools import Tool, ToolRegistry
from src.core.agent.types import AssistantMessage, ToolCall
from src.core.events import EventCategory
from src.core.perception.types import Perception, PerceptionKind
from src.utils.prompts import compose
from src.utils.logger import get_logger

logger = get_logger("bea.consciousness")


class Consciousness:
    """The single, always-on mind.

    One context, one loop. It drains perceptions from every surface, folds new
    ones in mid-burst (steering), reasons, and acts through tools. Speaking is
    non-blocking and body actions run async (single-slot), so Bea can talk and
    play at the same time — and decide for herself whether a new input is worth
    interrupting what she's doing.
    """

    def __init__(self, *, config, llm, bus, expression, surfaces, history_manager,
                 event_manager, memory_skill_getter, soul_getter, operating_getter):
        self.config = config
        self.llm = llm
        self.bus = bus
        self.expression = expression
        self.surfaces = surfaces
        self.history = history_manager
        self.events = event_manager
        self._get_memory = memory_skill_getter
        self._get_soul = soul_getter
        self._get_operating = operating_getter

        cc = config.consciousness
        self.idle_after = cc.get("idle_after", 30.0)
        self.window = cc.get("window", 0.3)
        self.burst_steps = cc.get("burst_steps", 6)
        self.history_limit = cc.get("history_limit", 30)
        self.correlation_timeout = cc.get("correlation_timeout", 30.0)

        self.context: List[Dict[str, Any]] = []
        self.alive = False
        self._loop_task: Optional[asyncio.Task] = None
        self._body_task: Optional[asyncio.Task] = None

        # correlations active for the current batch (HTTP callers waiting on a reply)
        self._correlations: Dict[str, Dict[str, Any]] = {}
        self._batch_correlations: List[str] = []

    # --- lifecycle ----------------------------------------------------------

    async def start(self):
        self.alive = True
        self.context = [self._system_message([])]
        for s in self.surfaces.all():
            try:
                await s.start()
            except Exception as e:
                logger.error(f"Surface '{s.name}' failed to start: {e}")
        self._loop_task = asyncio.create_task(self.run())
        logger.info("Consciousness started.")

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
        cid = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._correlations[cid] = {"future": fut, "route": route}
        return cid, fut

    # --- the loop -----------------------------------------------------------

    async def run(self):
        while self.alive:
            try:
                batch = await self.bus.wait_or_idle(self.idle_after)
                self._batch_correlations = [
                    p.meta["correlation_id"] for p in batch
                    if p.meta.get("correlation_id") in self._correlations
                ]
                self.context[0] = self._system_message(batch)
                self.context.append(self._frame(batch))

                for _ in range(self.burst_steps):
                    steer = self.bus.drain_nowait()
                    if steer:
                        self.context.append(self._frame(steer, steering=True))
                        self._batch_correlations += [
                            p.meta["correlation_id"] for p in steer
                            if p.meta.get("correlation_id") in self._correlations
                        ]

                    assistant = await self.llm.complete(self.context, tools=self._tool_schemas())
                    self.context.append(self._assistant_to_message(assistant))
                    if assistant.content:
                        self.events.publish(EventCategory.THOUGHT, "consciousness", assistant.content)

                    if assistant.is_final:
                        break

                    for call in assistant.tool_calls:
                        obs = await self._dispatch(call)
                        self.context.append(self._tool_result(call, obs))

                self._resolve_dangling_correlations()
                self._trim()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consciousness loop error: {e}")
                await asyncio.sleep(1)

    # --- context building ---------------------------------------------------

    def _system_message(self, batch: List[Perception]) -> Dict[str, Any]:
        soul = self._get_soul()
        operating = self._get_operating()
        sections = self.surfaces.context_sections()

        live = [s.live_state() for s in self.surfaces.active()]
        live = [x for x in live if x]

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        parts = [f"CURRENT DATE: {today}", soul, operating, *sections, *live]

        memory = self._get_memory()
        if memory and memory.enabled and batch:
            query = " ".join(p.render() for p in batch if p.kind in (PerceptionKind.CHAT, PerceptionKind.VOICE))
            if query.strip():
                ctx = memory.retrieve_context(query)
                if ctx:
                    parts.append(f"[LONG TERM MEMORY]\n{ctx}")

        return {"role": "system", "content": compose(*parts)}

    def _frame(self, perceptions: List[Perception], steering: bool = False) -> Dict[str, Any]:
        header = "[NEW INPUT — arrived while you were mid-action; decide if it's worth reacting to now]" \
            if steering else "[PERCEPTIONS]"
        lines = [f"({p.kind.value.upper()}) {p.render()}" for p in perceptions]
        return {"role": "user", "content": header + "\n" + "\n".join(lines)}

    # --- tools --------------------------------------------------------------

    def _tool_registry(self) -> ToolRegistry:
        reg = ToolRegistry()
        reg.add(
            "speak",
            "Say something out loud (with a facial expression). Non-blocking: you keep acting while it plays.",
            {"type": "object", "properties": {
                "mood": {"type": "string", "description": "normal, shock, love, cry, angry, ew, bored"},
                "message": {"type": "string"},
            }, "required": ["mood", "message"]},
            self._speak,
        )
        reg.add(
            "stay_silent",
            "Choose to say nothing right now.",
            {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
            self._stay_silent,
        )
        memory = self._get_memory()
        if memory and memory.enabled:
            reg.add(
                "recall_memory", "Search your long-term memory for relevant context.",
                {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
                lambda query: memory.retrieve_context(query),
            )
        for tool in self.surfaces.tools():
            reg.register(tool)
        return reg

    def _tool_schemas(self):
        return self._tool_registry().schemas() or None

    async def _dispatch(self, call: ToolCall) -> str:
        self.events.publish(EventCategory.TOOL, "consciousness", f"{call.name}({call.arguments})")
        reg = self._tool_registry()
        tool = reg.get(call.name)
        if tool is None:
            return f"ERROR: unknown tool '{call.name}'."

        if tool.long_running:
            return self._dispatch_body(tool, call.arguments)

        return await reg.dispatch(call)

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
        self.bus.put(Perception(
            PerceptionKind.ACTION, "game:mc",
            f"[{tool.name}] result: {result}", salience=0.7,
        ))

    # --- speaking (non-blocking) -------------------------------------------

    async def _speak(self, mood: str, message: str) -> str:
        mood = mood or "normal"
        self.history.add_message("assistant", message, mood=mood, source="consciousness")
        self.events.publish(EventCategory.OUTPUT, "consciousness", message, metadata={"mood": mood})

        routes = {self._correlations[c]["route"] for c in self._batch_correlations if c in self._correlations}

        if "discord" in routes:
            audio = await self.expression.speak(mood, message, route="remote")
            self._resolve(lambda r: r == "discord", {"status": "success", "text": message, "audio": audio})

        if "discord" not in routes or "local" in routes:
            # local stream/OBS: fire-and-forget so reasoning keeps going
            asyncio.create_task(self.expression.speak(mood, message, route="local"))
            self._resolve(lambda r: r != "discord", {"mood": mood, "message": message})

        return "Spoken."

    async def _stay_silent(self, reason: str = "") -> str:
        self._resolve(lambda r: True, {"mood": "normal", "message": ""})
        return "Staying silent."

    def _resolve(self, route_pred, payload):
        for cid in list(self._batch_correlations):
            c = self._correlations.get(cid)
            if not c or c["future"].done():
                continue
            if route_pred(c["route"]):
                c["future"].set_result(payload)
                self._correlations.pop(cid, None)
                self._batch_correlations.remove(cid)

    def _resolve_dangling_correlations(self):
        """If Bea ignored an HTTP caller this batch, free it (she said nothing)."""
        for cid in list(self._batch_correlations):
            c = self._correlations.pop(cid, None)
            if c and not c["future"].done():
                if c["route"] == "discord":
                    c["future"].set_result({"status": "ignored", "text": "", "audio": b""})
                else:
                    c["future"].set_result({"mood": "normal", "message": ""})
        self._batch_correlations = []

    # --- context plumbing (shared with AgentRunner conventions) -------------

    @staticmethod
    def _assistant_to_message(msg: AssistantMessage) -> Dict[str, Any]:
        import json
        out: Dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            out["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                for c in msg.tool_calls
            ]
        return out

    @staticmethod
    def _tool_result(call: ToolCall, observation: str) -> Dict[str, Any]:
        return {"role": "tool", "tool_call_id": call.id, "name": call.name, "content": observation}

    def _trim(self):
        if len(self.context) <= self.history_limit + 1:
            return
        tail = self.context[-self.history_limit:]
        while tail and tail[0].get("role") == "tool":
            tail.pop(0)
        self.context = [self.context[0]] + tail
