import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple, Union

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage, ToolCall, Usage
from src.interfaces.base_interfaces import LLMInterface, STTInterface
from src.modules.llm.reasoning import NO_STYLE, ReasoningStyle
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
from src.utils.sanitize import clean_model_output

logger = get_logger("bea.llm.openai_compat")


class OpenAICompatibleClient(LLMClient, LLMInterface):
    """Shared implementation for any provider exposing the OpenAI Chat API.

    Implements the tool-aware `complete()` used by the agent harness and keeps
    the legacy `chat`/`chat_audio`/`generate_json` helpers so existing callers
    (memory, monologue, the pre-agentic chat path) keep working unchanged.

    Subclasses only build `self.client`/`self.model_name` and implement
    `reload_config`.
    """

    def __init__(self, client, model_name: str, stt: Optional[STTInterface] = None,
                 reasoning: Optional[ReasoningStyle] = None):
        self.client = client
        self.model_name = model_name
        self.stt = stt
        self.reasoning = reasoning or NO_STYLE

    # --- the sdk call, with the reasoning fields negotiated ------------------

    def _call_sdk(self, **kwargs):
        """One sdk call, retried without the reasoning fields if refused.

        Some models force reasoning and answer 400 to anything that switches it
        off. Losing the turn over a latency hint is the wrong trade.
        """
        extra = self.reasoning.extra_body
        if extra:
            kwargs["extra_body"] = {**extra, **(kwargs.get("extra_body") or {})}
        try:
            return self.client.chat.completions.create(**kwargs)
        except Exception:
            if not self.reasoning.negotiable:
                raise
            logger.info(
                f"{self.model_name} refused the reasoning parameters; retrying without them."
            )
            kwargs["extra_body"] = self.reasoning.without_optional() or None
            return self.client.chat.completions.create(**kwargs)

    # --- tool-aware primitive (agent harness) ---

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> AssistantMessage:
        kwargs: Dict[str, Any] = {"model": self.model_name, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        if response_format:
            kwargs["response_format"] = response_format

        # the sdk call is blocking; keep the event loop free
        response = await asyncio.to_thread(self._call_sdk, **kwargs)
        message = response.choices[0].message

        tool_calls: List[ToolCall] = []
        for tc in getattr(message, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                logger.error(f"Bad tool arguments for {tc.function.name}: {tc.function.arguments}")
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        raw = getattr(response, "usage", None)
        usage = Usage(
            prompt_tokens=int(getattr(raw, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(raw, "completion_tokens", 0) or 0),
        )

        # cheap models leak <think> blocks and special tokens; unfiltered they
        # end up spoken out loud
        return AssistantMessage(content=clean_model_output(message.content),
                                tool_calls=tool_calls, usage=usage, model=self.model_name)

    # --- legacy helpers, implemented on top of the sync sdk ---

    def _create(self, messages: List[Dict[str, Any]], json_mode: bool = False):
        kwargs: Dict[str, Any] = {"model": self.model_name, "messages": messages}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self._call_sdk(**kwargs)

    def chat(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, dict]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            return parse_llm_json(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"API Error: {e}")
            return "sad", "There's some problem with my AI", {}

    def chat_audio(self, audio_path: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Tuple[str, str, dict]:
        if not self.stt:
            return "neutral", "I cannot hear you (STT module not configured).", {}
        transcription = self.stt.transcribe(audio_path)
        if not transcription:
            return "neutral", "I heard nothing.", {}
        return self.chat(transcription, system_prompt, history)

    def generate_json(self, user_input: str, system_prompt: Optional[str] = None, history: Optional[list] = None) -> Union[Dict, list]:
        messages = self._build_messages(user_input, system_prompt, history)
        try:
            response = self._create(messages, json_mode=True)
            _, _, data = parse_llm_json(response.choices[0].message.content)
            return data
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            return {}

    async def complete_json(self, user_input: str, system_prompt: Optional[str] = None,
                            history: Optional[list] = None) -> Union[Dict, list]:
        return await asyncio.to_thread(self.generate_json, user_input, system_prompt, history)

    @staticmethod
    def _build_messages(user_input: str, system_prompt: Optional[str], history: Optional[list]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_input})
        return messages

    def reload_config(self, config) -> None:  # pragma: no cover - overridden
        raise NotImplementedError
