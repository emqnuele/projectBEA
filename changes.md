# Complete Implementation Plan: LLM Provider Expansion for Updated projectBEA

This document contains the complete blueprint and reference implementation for adding the 5 new LLM providers to the updated version of **projectBEA**. It is designed so that you (or an AI assistant in a new IDE instance) can follow it step-by-step to re-apply the changes cleanly onto the fresh upstream clone.

---

## 1. Overview of Providers Added

| Provider Key | Provider Name | Base URL / Wire Format | Default Model | Key Required? |
|---|---|---|---|---|
| `google_ai_studio` (aliases: `google`, `gemini`) | Google AI Studio | `https://generativelanguage.googleapis.com/v1beta/openai/` (OpenAI Chat API) | `gemini-2.0-flash` | Yes (`GOOGLE_AI_STUDIO_KEY` / `GEMINI_API_KEY`) |
| `openai_compat` (alias: `openai_compatible`) | OpenAI Compatible (Generic) | User-defined (e.g. `http://localhost:8000/v1`, Together, vLLM) (OpenAI Chat API) | `gpt-4o-mini` | No / Optional (`OPENAI_COMPAT_API_KEY`) |
| `local` (aliases: `ollama`, `lmstudio`) | Local LLM | `http://localhost:11434/v1` (Ollama) or `http://localhost:1234/v1` (LM Studio) | `llama3.2` (Ollama) or `local-model` (LM Studio) | No / Optional (`LOCAL_API_KEY`) |
| `claude` (alias: `anthropic`) | Claude API | `https://api.anthropic.com/v1` (Anthropic Messages API) | `claude-3-7-sonnet-latest` | Yes (`ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`) |
| `anthropic_compat` (alias: `anthropic_compatible`) | Anthropic Compatible (Generic) | User-defined (Anthropic Messages API proxy/gateway) | `claude-3-7-sonnet-latest` | No / Optional (`ANTHROPIC_COMPAT_API_KEY`) |

---

## 2. Invariants & Architecture Rules

1. **Zero New Dependencies**: Do NOT add packages to `pyproject.toml`.
   - OpenAI-compatible endpoints use the existing `openai` client package.
   - Anthropic endpoints use standard library `json`, `asyncio`, and existing `requests` for SSE streaming and HTTP.
2. **Secrets Protection**:
   - Every secret key must be listed in `BrainConfig.SECRET_KEYS` and `SECRET_ENV_VARS` in `src/core/config.py`.
   - Keys are stripped from `config.json` and saved strictly to `.env`.
3. **Optional Authentication for Local/Proxies**:
   - `local`, `openai_compat`, and `anthropic_compat` must NOT throw errors when `api_key` is empty or absent. Default internal key to `"not-needed"`.
   - `doctor.py` must skip checking required keys for these providers.
4. **Role Pools**:
   - All provider names and their aliases must resolve correctly in `models.mind` and `models.background` (`"provider:model"`).

---

## 3. Files to Create (New Files)

### 3.1. `src/modules/llm/google_ai_studio_llm.py`
Subclass of `OpenAICompatibleClient` configured for Google AI Studio's official OpenAI endpoint:
- **Base URL**: `https://generativelanguage.googleapis.com/v1beta/openai/`
- **Default model**: `gemini-2.0-flash`
- **Config reload**: Updates client when `google_ai_studio_key` changes; updates `model_name` when `google_ai_studio_model` changes.

```python
from typing import Optional
from openai import OpenAI
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.google_ai_studio")
GOOGLE_AI_STUDIO_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"

class GoogleAIStudioLLM(OpenAICompatibleClient):
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.api_key = api_key
        super().__init__(
            OpenAI(api_key=api_key, base_url=GOOGLE_AI_STUDIO_BASE_URL),
            model_name,
            stt_interface,
            reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "google_ai_studio_key", None)
        model = getattr(config, "google_ai_studio_model", None)
        if key and key != self.api_key:
            self.api_key = key
            self.client = OpenAI(api_key=self.api_key, base_url=GOOGLE_AI_STUDIO_BASE_URL)
        if model and model != self.model_name:
            self.model_name = model
```

---

### 3.2. `src/modules/llm/openai_compat_generic_llm.py`
Generic OpenAI-compatible client for any third-party or self-hosted endpoint:
- **Default Base URL**: `http://localhost:8000/v1`
- **Default Model**: `gpt-4o-mini`
- **Key**: Defaults to `"not-needed"` if empty.
- **Config reload**: Recreates `OpenAI` client if `openai_compat_key` or `openai_compat_base_url` change.

```python
from typing import Optional
from openai import OpenAI
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.openai_compat_generic")

class OpenAICompatibleGenericLLM(OpenAICompatibleClient):
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o-mini",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.base_url = (base_url or "http://localhost:8000/v1").rstrip("/")
        self.api_key = api_key or "not-needed"
        super().__init__(
            OpenAI(api_key=self.api_key, base_url=self.base_url),
            model_name,
            stt_interface,
            reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "openai_compat_key", None) or "not-needed"
        base_url = (getattr(config, "openai_compat_base_url", None) or self.base_url).rstrip("/")
        model = getattr(config, "openai_compat_model", None)

        rebuild = False
        if key != self.api_key:
            self.api_key = key
            rebuild = True
        if base_url != self.base_url:
            self.base_url = base_url
            rebuild = True

        if rebuild:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        if model and model != self.model_name:
            self.model_name = model
```

---

### 3.3. `src/modules/llm/local_llm.py`
Dedicated client for Ollama, LM Studio, or local servers:
- **Default Base URL**: `http://localhost:11434/v1`
- **Default Model**: `llama3.2`
- **Key**: Defaults to `"not-needed"` if empty.
- **Config reload**: Updates when `local_base_url`, `local_key`, or `local_model` change.

```python
from typing import Optional
from openai import OpenAI
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.openai_compat import OpenAICompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.local")

class LocalLLM(OpenAICompatibleClient):
    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: Optional[str] = None,
        model_name: str = "llama3.2",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        self.base_url = (base_url or "http://localhost:11434/v1").rstrip("/")
        self.api_key = api_key or "not-needed"
        super().__init__(
            OpenAI(api_key=self.api_key, base_url=self.base_url),
            model_name,
            stt_interface,
            reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "local_key", None) or "not-needed"
        base_url = (getattr(config, "local_base_url", None) or self.base_url).rstrip("/")
        model = getattr(config, "local_model", None)

        rebuild = False
        if key != self.api_key:
            self.api_key = key
            rebuild = True
        if base_url != self.base_url:
            self.base_url = base_url
            rebuild = True

        if rebuild:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        if model and model != self.model_name:
            self.model_name = model
```

---

### 3.4. `src/modules/llm/anthropic_compat.py`
Shared client for Anthropic Messages API compatible endpoints. Implements `LLMClient` and `LLMInterface`.
- Converts OpenAI-style function definitions to Anthropic `input_schema` tools.
- Converts chat messages: separates `system` messages into top-level `system` parameter; maps `assistant` tool calls to `tool_use` blocks; maps `tool` responses to user `tool_result` blocks. Coalesces consecutive same-role turns to preserve alternating user/assistant structure.
- Handles both non-streaming `complete()` and SSE streaming `stream_complete()` with `on_tool_delta` speech callbacks.
- Supports legacy methods `chat`, `chat_audio`, `generate_json`, `complete_json`.

*(See `src/modules/llm/anthropic_compat.py` in the previous session for the full implementation).*

---

### 3.5. `src/modules/llm/claude_llm.py`
Direct client for Anthropic's Claude API, subclassing `AnthropicCompatibleClient`:
- **Default Base URL**: `https://api.anthropic.com/v1`
- **Default Model**: `claude-3-7-sonnet-latest`

```python
from typing import Optional
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.anthropic_compat import AnthropicCompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.claude")
CLAUDE_BASE_URL = "https://api.anthropic.com/v1"

class ClaudeLLM(AnthropicCompatibleClient):
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-3-7-sonnet-latest",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        super().__init__(
            api_key=api_key,
            base_url=CLAUDE_BASE_URL,
            model_name=model_name,
            stt_interface=stt_interface,
            reasoning=reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "claude_key", None)
        model = getattr(config, "claude_model", None)
        if key and key != self.api_key:
            self.api_key = key
        if model and model != self.model_name:
            self.model_name = model
```

---

### 3.6. `src/modules/llm/anthropic_compat_llm.py`
Generic Anthropic-compatible proxy client:

```python
from typing import Optional
from src.interfaces.base_interfaces import STTInterface
from src.modules.llm.anthropic_compat import AnthropicCompatibleClient
from src.modules.llm.reasoning import ReasoningStyle
from src.utils.logger import get_logger

logger = get_logger("bea.llm.anthropic_compat_llm")

class AnthropicCompatLLM(AnthropicCompatibleClient):
    def __init__(
        self,
        base_url: str = "https://api.anthropic.com/v1",
        api_key: Optional[str] = None,
        model_name: str = "claude-3-7-sonnet-latest",
        stt_interface: Optional[STTInterface] = None,
        reasoning: Optional[ReasoningStyle] = None,
    ):
        super().__init__(
            api_key=api_key or "not-needed",
            base_url=base_url,
            model_name=model_name,
            stt_interface=stt_interface,
            reasoning=reasoning,
        )

    def reload_config(self, config) -> None:
        key = getattr(config, "anthropic_compat_key", None) or "not-needed"
        base_url = (getattr(config, "anthropic_compat_base_url", None) or self.base_url).rstrip("/")
        model = getattr(config, "anthropic_compat_model", None)

        if key != self.api_key:
            self.api_key = key
        if base_url != self.base_url:
            self.base_url = base_url
        if model and model != self.model_name:
            self.model_name = model
```

---

### 3.7. `tests/test_new_llm_providers.py`
Comprehensive test suite testing:
- Factory instantiation for all 5 providers and aliases.
- Missing key exceptions for Google AI Studio and Claude.
- No-key allowance for local and compatible clients.
- Config reload dynamically swapping client base URLs and keys.
- OpenAI-to-Anthropic tool schema and message conversion.
- CLI argument parsing to `BrainConfig` fields.
- Doctor check skipping optional key verification for local.

---

## 4. Existing Files to Modify

### 4.1. `src/modules/llm/factory.py`
- Add to `_PROVIDERS`:
  ```python
  "google_ai_studio": ("google_ai_studio_key", "google_ai_studio_model"),
  "google": ("google_ai_studio_key", "google_ai_studio_model"),
  "gemini": ("google_ai_studio_key", "google_ai_studio_model"),
  "openai_compat": ("openai_compat_key", "openai_compat_model"),
  "openai_compatible": ("openai_compat_key", "openai_compat_model"),
  "local": ("local_key", "local_model"),
  "ollama": ("local_key", "local_model"),
  "lmstudio": ("local_key", "local_model"),
  "claude": ("claude_key", "claude_model"),
  "anthropic": ("claude_key", "claude_model"),
  "anthropic_compat": ("anthropic_compat_key", "anthropic_compat_model"),
  "anthropic_compatible": ("anthropic_compat_key", "anthropic_compat_model"),
  ```
- Define `OPTIONAL_KEY_PROVIDERS`:
  ```python
  OPTIONAL_KEY_PROVIDERS = {
      "local", "ollama", "lmstudio",
      "openai_compat", "openai_compatible",
      "anthropic_compat", "anthropic_compatible",
  }
  ```
- In `build_client()`:
  - Skip raising `LLMConfigError` if provider is in `OPTIONAL_KEY_PROVIDERS`.
  - Add instantiation branches for `google_ai_studio`, `openai_compat`, `local`, `claude`, `anthropic_compat`.

---

### 4.2. `src/core/config.py`
- Add fields to `BrainConfig`:
  ```python
  # google ai studio
  google_ai_studio_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_AI_STUDIO_KEY") or os.getenv("GEMINI_API_KEY"))
  google_ai_studio_model: str = "gemini-2.0-flash"

  # openai compatible (generic)
  openai_compat_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_COMPAT_API_KEY"))
  openai_compat_base_url: str = "http://localhost:8000/v1"
  openai_compat_model: str = "gpt-4o-mini"

  # local (ollama / lm studio / custom)
  local_key: Optional[str] = field(default_factory=lambda: os.getenv("LOCAL_API_KEY"))
  local_base_url: str = "http://localhost:11434/v1"
  local_model: str = "llama3.2"

  # claude api
  claude_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or os.getenv("CLAUDE_API_KEY"))
  claude_model: str = "claude-3-7-sonnet-latest"

  # anthropic compatible
  anthropic_compat_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_COMPAT_API_KEY"))
  anthropic_compat_base_url: str = "https://api.anthropic.com/v1"
  anthropic_compat_model: str = "claude-3-7-sonnet-latest"
  ```
- Add to `SECRET_ENV_VARS`:
  ```python
  "google_ai_studio_key": "GOOGLE_AI_STUDIO_KEY",
  "openai_compat_key": "OPENAI_COMPAT_API_KEY",
  "local_key": "LOCAL_API_KEY",
  "claude_key": "ANTHROPIC_API_KEY",
  "anthropic_compat_key": "ANTHROPIC_COMPAT_API_KEY",
  ```
- Add to `BrainConfig.SECRET_KEYS`:
  ```python
  "google_ai_studio_key", "openai_compat_key", "local_key",
  "claude_key", "anthropic_compat_key",
  ```

---

### 4.3. `src/cli.py`
- In `parse_args()`:
  - Add all new provider identifiers to `--llm-provider` `choices`:
    ```python
    "openrouter", "openai", "groq",
    "google_ai_studio", "google", "gemini",
    "openai_compat", "openai_compatible",
    "local", "ollama", "lmstudio",
    "claude", "anthropic",
    "anthropic_compat", "anthropic_compatible",
    ```
  - Add CLI arguments:
    - `--google-ai-studio-key`, `--google-ai-studio-model`
    - `--openai-compat-key`, `--openai-compat-base-url`, `--openai-compat-model`
    - `--local-key`, `--local-base-url`, `--local-model`
    - `--claude-key`, `--claude-model`
    - `--anthropic-compat-key`, `--anthropic-compat-base-url`, `--anthropic-compat-model`
- In `apply_cli_overrides()`:
  - Add mapping for each new CLI argument to the config attribute.

---

### 4.4. `src/setup/config_plan.py`
- Add to `PROVIDER_KEYS` and `PROVIDER_MODELS`:
  ```python
  "google_ai_studio": ("google_ai_studio_key", "GOOGLE_AI_STUDIO_KEY"),
  "openai_compat": ("openai_compat_key", "OPENAI_COMPAT_API_KEY"),
  "local": ("local_key", "LOCAL_API_KEY"),
  "claude": ("claude_key", "ANTHROPIC_API_KEY"),
  "anthropic_compat": ("anthropic_compat_key", "ANTHROPIC_COMPAT_API_KEY"),
  ```
  ```python
  "google_ai_studio": ("google_ai_studio_model", "gemini-2.0-flash"),
  "openai_compat": ("openai_compat_model", "gpt-4o-mini"),
  "local": ("local_model", "llama3.2"),
  "claude": ("claude_model", "claude-3-7-sonnet-latest"),
  "anthropic_compat": ("anthropic_compat_model", "claude-3-7-sonnet-latest"),
  ```
- In `apply_answers()`:
  - Save `base_url` to corresponding provider if set.

---

### 4.5. `src/setup/wizard.py`
- Add new providers to `PROVIDERS` list.
- Add test URLs to `KEY_TEST_URLS` for `google_ai_studio` and `claude`.
- In `_ask_llm()`:
  - If `provider == "local"`: Prompt preset choice between Ollama (`http://localhost:11434/v1`, `llama3.2`), LM Studio (`http://localhost:1234/v1`, `local-model`), or Custom. Key prompt is optional.
  - If `provider == "openai_compat"` or `"anthropic_compat"`: Ask for Base URL and optional Key.
  - Test keys for `google_ai_studio` and `claude` (with Anthropic headers).

---

### 4.6. `src/setup/doctor.py`
- In `_env_var()`: Map new providers to their respective environment variables.
- In `_key_for()`: Resolve keys using fallback env vars (`GEMINI_API_KEY`, `CLAUDE_API_KEY`, and default `"local"` for local).
- In `check_keys()`: Include `local`, `ollama`, `lmstudio`, `openai_compat`, `anthropic_compat` in `optional_key_providers` so missing keys don't fail diagnostics.

---

### 4.7. `src/web/routers/status.py`
- In `_engine_summary()`: Map new providers to `config.<provider>_model`.

---

### 4.8. `src/web/frontend/src/pages/settings/sections.jsx` & `parts.jsx`
- In `EngineSection`:
  - Extend `keyField`, `modelField`, `keyPlaceholder`, `modelPlaceholder` maps.
  - In `ProviderChoice`, pass `columns={4}` and options for all 8 providers.
  - When `isLocal`: Render **[ 🦙 Ollama ]** and **[ 🧪 LM Studio ]** preset buttons.
  - Render editable Base URL fields when `isLocal`, `isOpenAICompat`, or `isAnthropicCompat`.
- In `parts.jsx`:
  - Update `ProviderChoice` grid classes: `columns === 4 ? 'lg:grid-cols-4 sm:grid-cols-2' : ...`.

---

### 4.9. Documentation & Configuration Templates
- `.env.example`: Add comment blocks and examples for `GOOGLE_AI_STUDIO_KEY`, `OPENAI_COMPAT_API_KEY`, `LOCAL_API_KEY`, `ANTHROPIC_API_KEY`, `ANTHROPIC_COMPAT_API_KEY`.
- `config.example.json`: Add default model and base URL fields.
- `docs/modules/llm.md`: Update architecture tree and provider key table.
- `docs/configuration.md`: Update environment variable and CLI argument tables.

---

### 4.10. `tests/test_registry.py` (Gotcha Fix)
- In `test_an_unknown_provider_is_skipped`: Change `"ollama:llama3"` to `"unknownprovider:llama3"` (since `ollama` is now a recognized provider alias).

---

## 5. Verification Checklist

1. **Linter**:
   ```bash
   uv run ruff check src tests
   ```
2. **Provider Unit Tests**:
   ```bash
   uv run pytest tests/test_new_llm_providers.py -v
   ```
3. **Full Project Test Suite**:
   ```bash
   uv run pytest -q
   ```
4. **Compile Web Dashboard**:
   ```bash
   uv run bea --install-node
   # or: cd src/web/frontend && npm install && npm run build
   ```
5. **Launch & Verify UI**:
   ```bash
   uv run bea --web
   ```
   Open `http://localhost:8000/` and navigate to Settings > Engine to verify provider cards, preset buttons, and dynamic fields.

---

## 6. Bugfix: Settings Save Error ("persona: not writable here")

### 6.1. Symptom & Error
When attempting to change any setting on the dashboard settings page (`/dashboard/settings/*`), saving failed with:
- **UI Toast**: `"Nothing was saved - persona: not writable here"`
- **CLI Log**: `INFO: 127.0.0.1:<port> - "POST /config HTTP/1.1" 422 Unprocessable Entity`

### 6.2. Root Cause
1. `GET /config` returns `BrainConfig.public_dict()`, which includes the `persona` dictionary (`{"name": "...", "pronouns": "..."}`).
2. `SettingsPage.jsx` stores this full config in state and submits the whole `config` object back to `POST /config` upon clicking **Save**.
3. In `src/core/config_write.py`, `GUARDED = frozenset({"persona"})` exists because persona modifications are owned by `PUT /persona` with its own safety checks.
4. `plan_config()` checked `if key in GUARDED: errors[key] = "not writable here"` unconditionally for any key in the payload. Thus, even if `persona` was untouched, any save carrying the read-back config was rejected with a `422`.

### 6.3. Solution & Modifications
1. **Backend Validation (`src/core/config_write.py`)**:
   In `plan_config()`, check if the guarded field's value matches the running configuration:
   ```python
   for key, raw in sorted(payload.items()):
       if key in GUARDED:
           if raw == getattr(config, key, None):
               continue
           errors[key] = "not writable here"
           continue
   ```
   If the client echoes back the existing `persona` unmodified, it is safely ignored (not staged, not rejected). If an actual modification to `persona` is attempted via `POST /config`, it continues to be rejected with `"not writable here"`.

2. **Frontend Clean Payload (`src/web/frontend/src/api.js`)**:
   In `api.saveConfig()`, strip `persona` before posting to `/config` so the frontend does not send unnecessary guarded fields:
   ```javascript
   saveConfig: (config) => {
       const { persona, ...cleanConfig } = config || {};
       return request('/config', { method: 'POST', body: { config: cleanConfig } });
   },
   ```

3. **Production Build**:
   Recompiled the frontend assets into `src/web/frontend/dist` with `npm run build`.

4. **Automated Tests**:
   - `tests/test_config_write.py`: Added `test_an_untouched_persona_in_a_whole_save_is_ignored`.
   - `tests/test_settings_api.py`: Added `test_saving_a_full_config_from_get_does_not_fail_on_persona`.
   - Verified all 71 config/settings tests and the complete project suite (1935 passed).
