# LLM Modules

← [Back to README](../../README.md) | [Architecture](../architecture.md)

---

## Overview

The LLM layer is entirely defined by `LLMInterface` (`src/interfaces/base_interfaces.py`). The brain calls `llm.chat()` and never knows which concrete provider is behind it. Providers are instantiated in `main.py` based on the `--llm-provider` flag or `config.json`.

```
src/modules/llm/
├── gemini_llm.py      Google Gemini (google-genai SDK)
├── openai_llm.py      OpenAI / any OpenAI-compatible API
├── groq_llm.py        Groq (OpenAI-compatible, fast inference)
└── glm_llm.py         GLM-4.7 by Z.AI (OpenAI-compatible)
```

---

## Interface Contract

```python
class LLMInterface(ABC):
    def chat(user_input: str, system_prompt: Optional[str] = None, history: list = None) -> (mood, message, metadata)
    def chat_audio(audio_path: str, system_prompt: Optional[str] = None, history: list = None) -> (mood, message, metadata)
    def generate_json(user_input: str, system_prompt: Optional[str] = None, history: list = None) -> dict
    def reload_config(config: BrainConfig) -> None
```

Every LLM must return a **structured tuple**:
- `mood` (`str`) — one of the defined mood IDs (`normal`, `angry`, `bored`, `cry`, `ew`, `love`, `shock`)
- `message` (`str`) — the spoken text response
- `metadata` (`dict`) — any extra fields from the JSON response

---

## Expected LLM Response Format

The system prompt instructs the AI to always reply in JSON:

```json
{
  "mood": "normal",
  "message": "The spoken response text."
}
```

All providers use `src/utils/llm_utils.parse_llm_json()` to robustly extract this JSON from the raw response, handling:
- Fenced code blocks (` ```json ... ``` `)
- Raw JSON strings
- Nested braces (finds first balanced `{ }` block)

If parsing fails, mood defaults to `"normal"` and the raw string is used as the message.

---

## Providers

### Gemini (`gemini_llm.py`)

**SDK:** `google-genai`  
**Config key:** `gemini_model` (default: `gemini-3-flash-preview`)  
**Env var:** `GEMINI_API_KEY`

Supports **multimodal input** — can accept both text and audio inline (base64 bytes). This is the only provider that natively supports `chat_audio()` without requiring a separate STT step.

```python
llm = GeminiLLM(api_key="...", model_name="gemini-3-flash-preview")
mood, message, meta = llm.chat("Hello!", system_prompt="...", history=[...])
```

---

### OpenAI (`openai_llm.py`)

**SDK:** `openai`  
**Config key:** `openai_model` (default: `gpt-5`)  
**Env var:** `OPENAI_API_KEY`

Standard OpenAI chat completions. `chat_audio()` is handled by first transcribing via the injected STT interface, then calling `chat()`. Also used by the Memory skill's `DiaryGenerator`.

---

### Groq (`groq_llm.py`)

**SDK:** `groq` (OpenAI-compatible)  
**Config key:** `groq_model` (default: `openai/gpt-oss-20b`)  
**Env var:** `GROQ_API_KEY`

High-speed inference. The Groq provider is also used by the STT module (Whisper), so a single key can power both speech recognition and language generation.

---

### GLM-4.7 (`glm_llm.py`)

**SDK:** OpenAI-compatible client pointed at Z.AI  
**Config key:** `glm_model` (default: `glm-4.7`)  
**Env var:** `GLM_API_KEY`

Connects to the Z.AI (Zhipu AI) API using the same interface as OpenAI. Useful as a cost-effective alternative.

---

## Hot Reload

Every provider implements `reload_config(config)`. When called:
- If the API key changed, the client is re-initialized.
- If the model name changed, it is updated in place.

No restart needed after a config update.

---

## Adding a New LLM Provider

1. Create `src/modules/llm/my_llm.py` and extend `LLMInterface`.
2. Implement `chat()`, `chat_audio()`, `generate_json()`, `reload_config()`.
3. In `main.py`, add a branch to the provider selection block:

```python
elif config.llm_provider == "my_provider":
    from src.modules.llm.my_llm import MyLLM
    llm = MyLLM(api_key=config.my_key, model_name=config.my_model)
```

4. Add `"my_provider"` to the `--llm-provider` choices in `parse_args()`.
