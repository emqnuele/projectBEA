# Setup & Installation

← [Back to README](../README.md)

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.10+ | Tested on 3.11 |
| Node.js | 18+ | Required only for the Discord bot |
| OBS Studio | 28+ | obs-websocket 5.x built-in |
| Virtual Audio Cable | any | e.g. [VB-Audio CABLE](https://vb-audio.com/Cable/) — optional but recommended |

---

## 1. Clone & Install

```bash
git clone https://github.com/emqnuele/projectBEA.git
cd projectbea
```

Create a virtual environment (recommended):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate
```

Install Python dependencies:

```bash
pip install -r requirements.txt
```

> **Linux note:** Some packages (`numpy`, `tokenizers`) may need to compile from source if a pre-built wheel is unavailable for your Python version. Install a C/C++ compiler first if you hit build errors:
> ```bash
> sudo dnf install gcc gcc-c++   # Fedora/RHEL
> sudo apt install build-essential  # Debian/Ubuntu
> ```

> **uv users:** `uv pip install -r requirements.txt` also works and is faster. The `tokenizers>=0.20.0` pin in `requirements.txt` avoids a known broken build in the 0.19.x series.

---

## 2. Environment Variables

Create a `.env` file in the project root:

```env
# LLM providers — add the ones you plan to use
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
GLM_API_KEY=...

# TTS — only if using Orpheus
ORPHEUS_API_KEY=...
ORPHEUS_ENDPOINT=https://model-xxxxxxxx.api.baseten.co/environments/production/predict

# Discord — only if using the Discord skill
DISCORD_TOKEN=...

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
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Find the ID of your virtual cable (e.g. *CABLE Input* on Windows) and set `audio_device_id` in `config.json`.

---

## 6. Discord Bot Setup (optional)

Install Node.js dependencies for the bot:

```bash
cd src/modules/skills/discord/bot
npm install
```

Set your Discord token in `.env` or in `config.json` under `skills.discord.token`.

In `config.json`, also set:
- `skills.discord.enabled: true`
- `skills.discord.target_channel`: the voice channel name where Bea should listen/speak

[Discord Skill Details →](skills/discord.md)

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
python main.py
```

Type messages at the `You >` prompt. Type `exit` to quit.

### Web Dashboard mode

```bash
python main.py --web
```

Opens the FastAPI server at `http://localhost:8000`. The React frontend (built in step 8) is served from the same port at `/`.

### CLI argument overrides

Any config value can be overridden at launch without editing `config.json`:

```bash
python main.py \
  --llm-provider gemini \
  --gemini-model gemini-2.0-flash \
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
python main.py --web
```

2. Then start the Vite dev server (in a second terminal):

```bash
cd src/web/frontend
npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173`. The frontend makes **direct** API calls to `http://localhost:8000` — **no proxy is configured** in `vite.config.js`. If you change the backend port, update the API base URL in the frontend source accordingly.

> **Note:** For normal use you do **not** need the dev server — just build once with `npm run build` (step 8) and use `python main.py --web`.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `OBS not connected` warning on start | OBS is not running or WebSocket creds are wrong — the engine continues without it |
| `No audio device` error | Run the sounddevice query above and update `audio_device_id` |
| Discord bot fails with `node_modules not found` | Run `npm install` in `src/modules/skills/discord/bot/` |
| Memory skill disabled on start | `OPENAI_API_KEY` not set — ChromaDB embedding requires it |
| `GEMINI_API_KEY is missing` | Set the key in `.env` or pass `--gemini-key` at launch |
| Skills silently start disabled despite `"enabled": true` in `config.json` | Expected — all non-memory skills are force-disabled at every cold start. Enable them at runtime via the web dashboard or `POST /skills/{name}/toggle`. |
| OBS avatar source not updating after config migration | If your `config.json` still contains the old key `obs_image_source`, it is silently renamed to `obs_avatar_source` by `load_from_file()`. Delete the old key from your `config.json` and re-save to avoid ambiguity. |
