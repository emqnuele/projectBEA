"""Model pools per role: round-robin to spread load, fallback so one dead
provider does not make Bea mute.

Today a single 429 from OpenRouter silences her completely, and the dreamer runs
on the same model as the mind — competing with it for rate limit and latency.

A pool is a list of `provider:model` specs. The split is on the FIRST `:`, so
OpenRouter ids keep their `/` and their `:free` suffix intact.

Two roles:
- `mind`       — the consciousness. MUST support tool calling: Bea speaks only
                 through tools, so a model without tool use would never say
                 anything at all.
- `background` — diary, dreamer, summaries, person profiles. Batch work that
                 tolerates a slow, cheap model and must never compete with the mind.
"""

import asyncio
import re
from typing import Any, Dict, List, Optional

from src.core.agent.llm_client import LLMClient
from src.core.agent.types import AssistantMessage
from src.utils.logger import get_logger

logger = get_logger("bea.agent.registry")

MIND = "mind"
BACKGROUND = "background"

# a provider saying "this model has no tool support" is a configuration mistake,
# not a hiccup: it will fail identically forever, so it is logged loudly
_NO_TOOLS_RE = re.compile(
    r"(tool|function)[\s_-]*(call|use|choice)?.{0,40}(not|un)[\s_-]*(support|available|allowed)"
    r"|does not support tools",
    re.IGNORECASE,
)


class ModelPoolError(RuntimeError):
    """No usable model for a role, or every model in the pool failed."""


def looks_like_missing_tool_support(error: BaseException) -> bool:
    return bool(_NO_TOOLS_RE.search(str(error)))


class RotatingClient(LLMClient):
    """Rotates through a pool on each call; on failure, tries the next one."""

    def __init__(self, clients: List[LLMClient], *, name: str = "") -> None:
        if not clients:
            raise ModelPoolError("RotatingClient needs at least one client")
        self._clients = clients
        self._index = 0
        self.name = name or f"pool[{len(clients)}]"

    @property
    def clients(self) -> List[LLMClient]:
        return list(self._clients)

    def _order(self) -> List[LLMClient]:
        """The pool starting at the next client, then everyone else as fallback."""
        n = len(self._clients)
        start = self._index
        # advancing here (not on success) is what actually spreads the load
        self._index = (start + 1) % n
        return [self._clients[(start + i) % n] for i in range(n)]

    async def complete(self, messages, tools=None, response_format=None) -> AssistantMessage:
        return await self._attempt(
            lambda c: c.complete(messages, tools=tools, response_format=response_format),
            tools_needed=bool(tools),
        )

    async def complete_json(self, user_input, system_prompt=None, history=None):
        return await self._attempt(
            lambda c: c.complete_json(user_input, system_prompt, history),
            tools_needed=False,
        )

    async def _attempt(self, call, *, tools_needed: bool):
        last: Optional[BaseException] = None
        for client in self._order():
            label = _label(client)
            try:
                return await call(client)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last = e
                if tools_needed and looks_like_missing_tool_support(e):
                    logger.error(
                        f"Model {label} does not support tool calling and cannot serve the "
                        f"mind. Remove it from the 'mind' pool."
                    )
                else:
                    logger.warning(f"Model {label} failed, trying the next one: {e}")
        raise ModelPoolError(f"every model in {self.name} failed. Last error: {last}")

    def reload_config(self, config) -> None:
        for client in self._clients:
            try:
                client.reload_config(config)
            except Exception as e:
                logger.error(f"Reload failed for {_label(client)}: {e}")


class ModelRegistry:
    """Builds and caches one client (or pool) per role."""

    def __init__(self, config, stt=None) -> None:
        self.config = config
        self.stt = stt
        self._cache: Dict[str, LLMClient] = {}

    def get(self, role: str = MIND) -> LLMClient:
        cached = self._cache.get(role)
        if cached is not None:
            return cached

        clients = [c for spec in self._specs(role) if (c := self._build(spec)) is not None]
        if not clients:
            raise ModelPoolError(
                f"No usable model for role '{role}'. Check config.models['{role}'] "
                f"and the matching API keys."
            )
        client = clients[0] if len(clients) == 1 else RotatingClient(
            clients, name=f"{role}[{', '.join(_label(c) for c in clients)}]"
        )
        self._cache[role] = client
        logger.info(f"Role '{role}': {len(clients)} model(s) — {_label(client)}")
        return client

    def reload_config(self, config) -> None:
        """Config changed: drop the cache so new specs and keys take effect."""
        self.config = config
        for client in self._cache.values():
            try:
                client.reload_config(config)
            except Exception as e:
                logger.error(f"Reload failed for {_label(client)}: {e}")
        self._cache.clear()

    # --- spec resolution ----------------------------------------------------

    def _specs(self, role: str) -> List[str]:
        specs = (getattr(self.config, "models", None) or {}).get(role) or []
        if specs:
            return [s for s in specs if s]
        return self._legacy_specs(role)

    def _legacy_specs(self, role: str) -> List[str]:
        """Falls back to the pre-pool `llm_provider` + `<provider>_model` fields.

        Existing configs must keep working untouched after an upgrade.
        """
        provider = getattr(self.config, "llm_provider", "openrouter")
        model = getattr(self.config, f"{provider}_model", "")
        if not model:
            return []
        logger.info(f"Role '{role}': no pool configured, using {provider}:{model}")
        return [f"{provider}:{model}"]

    def _build(self, spec: str) -> Optional[LLMClient]:
        provider, sep, model = spec.partition(":")
        provider, model = provider.strip().lower(), model.strip()
        if not sep or not model:
            logger.warning(f"Invalid model spec (expected 'provider:model'): {spec!r}")
            return None

        from src.modules.llm.factory import LLMConfigError, build_client
        try:
            return build_client(provider, model, self.config, stt=self.stt)
        except LLMConfigError as e:
            logger.warning(f"Skipping {spec}: {e}")
            return None


def _label(client: Any) -> str:
    name = getattr(client, "name", "")
    if name:
        return str(name)
    model = getattr(client, "model_name", "")
    return f"{type(client).__name__}({model})" if model else type(client).__name__


__all__ = [
    "ModelRegistry", "RotatingClient", "ModelPoolError", "MIND", "BACKGROUND",
    "looks_like_missing_tool_support",
]
