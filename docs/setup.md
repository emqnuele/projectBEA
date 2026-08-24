# Setup & Installation

← [Back to README](../README.md)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | latest | Python toolchain & dependency manager — installs Python for you |
| Node.js | 18+ | Required only for the web dashboard and the Discord bot |
| OBS Studio | 28+ | obs-websocket 5.x built-in |
| Virtual Audio Cable | any | e.g. [VB-Audio CABLE](https://vb-audio.com/Cable/) — optional but recommended |

> You do **not** need to install Python yourself. `uv` reads `requires-python` from
> `pyproject.toml` and downloads a matching interpreter automatically.
> Install `uv` with: `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS/Linux)
> or `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows).

---

## 1. Clone & Install

```bash
git clone https://github.com/emqnuele/projectBEA.git
cd projectBEA
```

Install all Python dependencies into a managed virtual environment (`.venv`):

```bash
uv sync                    # core dependencies
uv sync --extra minecraft  # also the optional minecraft-agent deps
uv sync --extra migrate    # only once, to lift an old chroma store into bea.db
```

That's it — `uv` creates `.venv`, pins every dependency from `uv.lock`, and is fully
reproducible. There is no need to activate the venv manually; prefix commands with
`uv run` (e.g. `uv run bea`).

If you have `make` available, the same is wrapped in convenient targets:

```bash
make install        # uv sync
make install-all    # uv sync --extra minecraft
make help           # list every target
```

> **Linux note:** Some packages (`numpy`, `tokenizers`) may need to compile from source if a pre-built wheel is unavailable for your Python version. Install a C/C++ compiler first if you hit build errors:
> ```bash
> sudo dnf install gcc gcc-c++   # Fedora/RHEL
> sudo apt install build-essential  # Debian/Ubuntu
> ```

---

## 2. Environment Variables

Create a `.env` file in the project root:

```env
# LLM providers — add the ones you plan to use
OPENROUTER_API_KEY=sk-or-...   # recommended: routes to any model
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...

# TTS — only if using Orpheus
ORPHEUS_API_KEY=...
ORPHEUS_ENDPOINT=https://model-xxxxxxxx.api.baseten.co/environments/production/predict

# Discord — only if using the Discord skill
DISCORD_TOKEN=...

# Telegram — only if using the Telegram skill
TELEGRAM_TOKEN=...

# Twitch — only needed to WRITE in chat; reading works anonymously
TWITCH_OAUTH_TOKEN=oauth:...

# Donations — shared secret checked on the webhook. Set this before exposing the server
DONATION_SECRET=...

# Logging — optional, defaults to INFO
LOG_LEVEL=DEBUG   # set to DEBUG to see verbose output (OBS, TTS, audio playback details)
```

> **Security note:** Environment variables **always take priority** over `config.json` for secret fields (`*_key`, `orpheus_endpoint`). If an env var is set and non-empty, the `config.json` value is silently skipped — even if it is also non-empty. A non-empty `config.json` value is only used as a fallback when the env var is not set.

---

## 3. OBS Studio Setup

1. Open OBS Studio.
2. Go to **Tools → WebSocket Server Settings**.
3. Enable the WebSocket server (default port: `4455`).
4. Set a password and note it down — you'll need it in `config.json`.

### Recommended OBS Sources

| Source Name | Type | Purpose |
|---|---|---|
| `BeaPNG` | Image Source | Avatar PNG (talking/idle) — or `BeaVid` if using `obs_source_type: "media"` |
| `AIText` | Text (GDI+) | Animated speech bubble |

Set `obs_avatar_source`, `obs_text_source` in `config.json` to match your source names.

---

## 4. Avatar Images / Videos

Populate `data/pngs/` with avatar assets organized by mood. Each mood folder contains two files: an idle and a talking state.

```
data/pngs/
├── normal/
│   ├── idle.mp4       (or .png, .gif)
│   └── talking.mp4
├── angry/
│   ├── idle.mp4
│   └── talking.mp4
├── bored/  cry/  ew/  love/  shock/   (same structure)
```

The `obs_source_type` config key controls whether OBS uses an **image** source (`image`) or a **media** source (`media`).

Then map the files in `config.json` under the `avatar_map` key:

```json
"avatar_map": {
  "normal": { "idle": "data/pngs/normal/idle.mp4", "talking": "data/pngs/normal/talking.mp4" },
  "angry":  { "idle": "data/pngs/angry/idle.mp4",  "talking": "data/pngs/angry/talking.mp4"  }
}
```

---

## 5. Audio Device Setup

ProjectBEA outputs audio to a specific device ID. To list available devices:

```bash
uv run python -c "import sounddevice; print(sounddevice.query_devices())"
```

Find the ID of your virtual cable (e.g. *CABLE Input* on Windows) and set `audio_device_id` in `config.json`.

---

## 6. Discord Bot Setup (optional)

Install Node.js dependencies for the bot:

```bash
cd src/core/skills/voice/bot
npm install
```

Set your Discord token in `.env` or in `config.json` under `skills.discord.token`.

Then toggle the skill on from the dashboard's Skills page, or set
`skills.discord.enabled: true` before starting.

[Discord Skill Details →](skills/discord.md)

---

## 6b. Telegram & Twitch (optional)

Neither needs a subprocess — both run in-process.

**Telegram:** create a bot with [@BotFather](https://t.me/botfather), put the
token in `.env` as `TELEGRAM_TOKEN`, set `skills.telegram.owner_id` to your own
user id, and leave `allowed_chats` empty to let her read every chat she is added
to. [Details →](skills/telegram.md)

**Twitch:** set `skills.twitch.channel` and toggle it on — reading needs no
credentials at all. Only add `TWITCH_OAUTH_TOKEN` and `skills.twitch.nick` if
you want her to type in chat. [Details →](skills/twitch.md)

---

## 7. Kokoro TTS Setup (optional)

Kokoro runs **entirely locally** — no API key required.

The engine automatically downloads the model files on first launch if they are missing:
- `kokoro-v0_19.onnx` (~95 MB)
- `voices.bin` (~30 MB)

No manual steps needed. Just set `tts_provider` to `kokoro` in `config.json` and start the engine. The download happens once and is cached in the project root.

To use a different path, update `kokoro_model` and `kokoro_voices_file` in `config.json`.

---

## 8. Orpheus TTS Setup (optional)

Orpheus is a high-quality expressive voice API hosted on [Baseten](https://baseten.co). It requires a manual deployment step before use:

1. Create an account at [baseten.co](https://baseten.co).
2. From the Baseten model library, find and deploy the **Orpheus TTS** model to your workspace.
3. Wait for the deployment to become active (a few minutes).
4. Copy the **Endpoint URL** shown in your deployment dashboard (format: `https://model-xxxxxxxx.api.baseten.co/environments/production/predict`).
5. Copy your **API key** from the Baseten account settings.
6. Add both to your `.env`:

```env
ORPHEUS_API_KEY=your-baseten-api-key
ORPHEUS_ENDPOINT=https://model-xxxxxxxx.api.baseten.co/environments/production/predict
```

> **Security note:** `ORPHEUS_ENDPOINT` is treated as a secret — it is read from the environment variable and is **never saved to `config.json`**, even if set via the web dashboard.

Then in `config.json` set `tts_provider` to `orpheus` and `orpheus_voice` to one of: `zoe`, `tara`, `leo`, `leah`.

> **Note:** Baseten bills per inference. Orpheus is the most expensive TTS option — use EdgeTTS or Kokoro for testing.

---

## 8. Build the Frontend (required for Web Dashboard)

Before using `--web`, you must install the Node.js dependencies and build the frontend once. The Python server serves the compiled output from `src/web/frontend/dist/` — if that folder doesn't exist, the dashboard will not load.

```bash
cd src/web/frontend
npm install
npm run build
cd ../../..   # back to project root
```

You only need to repeat this step when the frontend source code changes.

---

## Running the Engine

### CLI mode (interactive terminal)

```bash
uv run bea          # or: make run
```

Type messages at the `You >` prompt. Type `exit` to quit.

### Web Dashboard mode

```bash
uv run bea --web    # or: make web  (also builds the frontend)
```

Opens the FastAPI server at `http://localhost:8000`. The React frontend (built
in step 8) is served from the same port at `/`.

> The API has **no authentication**, so the server binds to `127.0.0.1` by
> default. Exposing it on the network is an explicit opt-in:
> `uv run bea --web --host 0.0.0.0`. Do that only behind something that
> authenticates, and set `DONATION_SECRET` first.

### CLI argument overrides

Any config value can be overridden at launch without editing `config.json`:

```bash
uv run bea \
  --llm-provider openrouter \
  --openrouter-model openai/gpt-4o-mini \
  --tts-provider kokoro \
  --device-id 22 \
  --web
```

[Full CLI & Config Reference →](configuration.md)

---

## Running the Frontend in Development Mode

This is only needed when **actively developing the frontend**. Instead of using the built `dist/`, Vite serves the source files with hot-reload at a separate port.

1. Start the backend first (in one terminal):

```bash
uv run bea --web
```

2. Then start the Vite dev server (in a second terminal):

```bash
cd src/web/frontend
npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173`. There is no proxy in
`vite.config.js`: the frontend calls the backend directly through `API_BASE`
(`src/web/frontend/src/api.js`), which is `http://localhost:8000` in dev and the
page's own origin in a build. To point the dev server somewhere else, set
`VITE_API_BASE` rather than editing the source.

`http://localhost:5173` is already in the backend's CORS allowlist. For any
other origin, set `BEA_ALLOWED_ORIGINS` (comma-separated) before starting the
brain.

> **Note:** For normal use you do **not** need the dev server — just build once with `npm run build` (step 8) and use `uv run bea --web`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `OBS not connected` warning on start | OBS is not running or WebSocket creds are wrong — the engine continues without it |
| `No audio device` error | Run the sounddevice query above and update `audio_device_id` |
| Discord bot fails with `node_modules not found` | Run `npm install` in `src/core/skills/voice/bot/` |
| `Embedder unavailable` on start | The embedding model could not be downloaded. Everything else keeps working — only long-term recall is lost until it can |
| `No usable model for role 'mind'` | The `models.mind` pool is empty or none of its keys are set. Check `models` in `config.json` and the matching `*_API_KEY` |
| A model in `mind` "does not support tool calling" | Remove it from the pool. Bea speaks only through tools, so a model without them never says anything |
| She never starts anything in Minecraft | Give her objectives on the dashboard's Stream Plan page — with an empty plan she only ever reacts |
| OBS avatar source not updating after config migration | If your `config.json` still contains the old key `obs_image_source`, it is silently renamed to `obs_avatar_source` by `load_from_file()`. Delete the old key from your `config.json` and re-save to avoid ambiguity. |
