# ProjectBEA — AI VTuber Engine

**ProjectBEA** is a modular, fully autonomous AI VTuber engine. It powers a living AI persona — **Bea** — that can hold live conversations, monologue to her audience when idle, join Discord voice calls, play Minecraft autonomously, and remember past sessions via a built-in RAG memory system. All of this is orchestrated through a clean plugin-based architecture where every component is swappable.


> Built for fun by a 19-year-old CS student learning Python. Open-source, self-hostable, and designed to be easily extended.

---

## Features

| Feature | Description |
|---|---|
| **Swappable LLMs** | Gemini, OpenAI-compatible (GPT-4o, Groq, GLM-4.7) — switch at runtime |
| **Multiple TTS engines** | EdgeTTS (free), Kokoro (local ONNX), Orpheus (API) |
| **OBS Integration** | Avatar PNG/video swap, animated text bubble via WebSocket |
| **RAG Memory** | ChromaDB-powered diary system — Bea remembers past sessions |
| **Discord Skill** | Full voice call integration — listens, transcribes, responds live |
| **Minecraft Skill** | Autonomous LLM-driven agent that plays Minecraft via WebSocket |
| **Monologue Skill** | When idle, Bea automatically starts talking to her audience |
| **Web Dashboard** | React + FastAPI dashboard for chat, config, skill control, brain activity |
| **Hot Reload** | Change models, voices, or settings at runtime without restart |
| **Plugin Skills** | Every capability is a `BaseSkill` plugin — add your own in minutes |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AIVtuberBrain                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐    │
│  │  LLM     │  │  TTS     │  │  STT     │  │  OBS          │    │
│  │ (pluggable)│ │ (pluggable)│ │ (Groq)   │  │ (WebSocket) │    │
│  └──────────┘  └──────────┘  └──────────┘  └───────────────┘    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    SkillManager                         │    │
│  │  ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐    │    │
│  │  │ Memory   │ │ Discord  │ │ Minecraft │ │Monologue│    │    │
│  │  │ (RAG)    │ │ (Voice)  │ │ (Agent)   │ │ (Idle)  │    │    │
│  │  └──────────┘ └──────────┘ └───────────┘ └─────────┘    │    │
│  └─────────────────────────────────────────────────────────┘    │
│  ┌──────────────────┐   ┌──────────────────────────────────┐    │
│  │  HistoryManager  │   │  EventManager                    │    │
│  │  (sessions/JSON) │   │  (system, input, output, skill)  │    │
│  └──────────────────┘   └──────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │       FastAPI + React         │
              │       Web Dashboard           │
              └───────────────────────────────┘
```

**[Full Architecture Documentation →](docs/architecture.md)**

---

## Project Structure

```
ProjectBEA/
├── main.py                    # Entry point (CLI args + engine bootstrap)
├── config.json                # Persistent runtime configuration
├── requirements.txt
├── data/
│   ├── conversations/         # Saved session JSON files
│   ├── memory_db/             # ChromaDB persistent storage
│   ├── pngs/                  # Avatar images per mood (idle/talking)
│   └── prompts/               # System prompts (persona, monologue, minecraft)
├── docs/                      # Full documentation (you are here)
└── src/
    ├── core/
    │   ├── brain.py           # Central orchestrator
    │   ├── config.py          # BrainConfig dataclass + config.json I/O
    │   ├── events.py          # EventManager (pub/sub, brain activity log)
    │   └── resources.py       # Avatar resource loader
    ├── interfaces/
    │   └── base_interfaces.py # Abstract contracts: LLM, TTS, STT, OBS
    ├── modules/
    │   ├── llm/               # LLM providers (Gemini, OpenAI, Groq, GLM)
    │   ├── tts/               # TTS engines (EdgeTTS, Kokoro, Orpheus)
    │   ├── STT/               # STT (Groq/Whisper)
    │   ├── obs/               # OBS WebSocket controller
    │   └── skills/            # Plugin skill system
    │       ├── base_skill.py
    │       ├── skill_manager.py
    │       ├── memory/        # RAG memory + ChromaDB
    │       ├── discord/       # Discord voice skill + Node.js bot
    │       ├── minecraft/     # Minecraft autonomous agent
    │       └── implementations/ # Monologue + misc skills
    ├── utils/
    │   ├── history_manager.py # Conversation session persistence
    │   ├── llm_utils.py       # JSON response parsing
    │   └── text_utils.py      # Text formatting utilities
    └── web/
        ├── app.py             # FastAPI REST API
        ├── server.py          # Uvicorn launcher
        └── frontend/          # React + Vite + Tailwind dashboard
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10+
- Node.js 18+ (for the Discord bot)
- OBS Studio with WebSocket plugin enabled *(Tools → WebSocket Server Settings)*
- A virtual audio cable such as [VB-Audio Cable](https://vb-audio.com/Cable/) *(optional but recommended)*

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Copy `.env.example` to `.env` (or set environment variables directly):

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=AIzaSy...
GROQ_API_KEY=gsk_...
DISCORD_TOKEN=...
```

Review `config.json` to set your OBS source names, audio device ID, TTS voice, and which skills are enabled.

**[Full Configuration Guide →](docs/configuration.md)**

### 4. Run

**CLI mode** (terminal interactive):
```bash
python main.py
```

**Web Dashboard mode** (FastAPI + React UI):
```bash
python main.py --web
```

**Override provider at launch:**
```bash
python main.py --llm-provider gemini --tts-provider kokoro --web
```

**[Setup & Deployment Guide →](docs/setup.md)**

---

## Modules

The engine is built around three types of components, each defined by an abstract interface in `src/interfaces/base_interfaces.py`. Any provider can be swapped without touching the core.

| Component | Interface | Implementations |
|---|---|---|
| **LLM** | `LLMInterface` | Gemini, OpenAI, Groq, GLM-4.7 |
| **TTS** | `TTSInterface` | EdgeTTS, Kokoro (local), Orpheus |
| **STT** | `STTInterface` | Groq (Whisper large-v3-turbo) |
| **OBS** | `OBSInterface` | OBS WebSocket (obs-websocket-py) |

**[LLM Modules →](docs/modules/llm.md)** · **[TTS Modules →](docs/modules/tts.md)** · **[STT →](docs/modules/stt.md)** · **[OBS →](docs/modules/obs.md)**

---

## Skills — Plugin System

Skills are autonomous background capabilities managed by the `SkillManager`. Each extends `BaseSkill` and can be enabled/disabled at runtime (including hot-toggle from the web UI).

| Skill | Description |
|---|---|
| **Memory** | RAG system: converts sessions into diary entries, stores in ChromaDB, injects relevant context into every prompt |
| **Discord** | Launches a Node.js Discord bot; listens in voice channels, transcribes speech, sends audio back live |
| **Minecraft** | Connects via WebSocket to a Minecraft mod; an LLM agent autonomously performs actions using tool-calling |
| **Monologue** | When the audience is silent, Bea starts unprompted storytelling — episodically, chunk by chunk |

**[Skills Overview →](docs/skills/overview.md)**

---

## Web Dashboard

The `--web` flag starts a FastAPI backend (port 8000) and serves a React + Tailwind frontend.

**Pages:**
- **Chat** — text chat with Bea, session management
- **Brain Activity** — real-time event feed (inputs, outputs, skill events, thoughts)
- **Skills** — toggle skills on/off at runtime
- **Config** — edit every setting live with hot reload

**[API Reference →](docs/web/api.md)** · **[Frontend →](docs/web/frontend.md)**

---

## Full Documentation

| Document | Contents |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flow, event system |
| [Setup & Install](docs/setup.md) | Installation, OBS setup, audio routing |
| [Configuration](docs/configuration.md) | All config fields, CLI args, `.env` vars |
| [LLM Modules](docs/modules/llm.md) | Providers, response format, adding new LLMs |
| [TTS Modules](docs/modules/tts.md) | EdgeTTS, Kokoro, Orpheus |
| [STT Module](docs/modules/stt.md) | Groq Whisper transcription |
| [OBS Module](docs/modules/obs.md) | Avatar control, text animation |
| [Skills Overview](docs/skills/overview.md) | BaseSkill API, SkillManager lifecycle |
| [Memory Skill](docs/skills/memory.md) | RAG system, ChromaDB, diary generation |
| [Discord Skill](docs/skills/discord.md) | Discord bot setup, voice pipeline |
| [Minecraft Skill](docs/skills/minecraft.md) | MC agent, tool-calling, WebSocket bridge |
| [Monologue Skill](docs/skills/monologue.md) | Idle storytelling state machine |
| [Web API](docs/web/api.md) | All REST endpoints |
| [Frontend](docs/web/frontend.md) | React component structure |

---

## Extending ProjectBEA

The modular design makes adding new capabilities straightforward:

- **New LLM provider** → implement `LLMInterface`, register in `main.py`
- **New TTS engine** → implement `TTSInterface`, add to CLI choices
- **New Skill** → extend `BaseSkill`, register in `SkillManager`

See [Skills Overview](docs/skills/overview.md) for the full plugin API.

---

## About

Built by **Emanuele Faraci**, 19-year-old Computer Science student from Italy.

This project started as a way to learn Python properly, specifically async programming, API integrations, and modular system design, while building something actually fun. It grew from a simple TTS + OBS script into a full VTuber engine with skills, memory, and a web dashboard.

just a side project built for fun and learning.

**Portfolio:** [emanuelefaraci.com](https://emanuelefaraci.com)

---

## License

This project is open-source. See `LICENSE` for details.

