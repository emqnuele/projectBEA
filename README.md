<p align="center">
  <img src="assets/hero.png" alt="ProjectBEA Hero" />
</p>

<h1 align="center">ProjectBEA</h1>

<p align="center"><b>She talks, plays, and remembers you.</b></p>

<p align="center">
  An always-on AI persona across Discord, Telegram, Twitch and a vanilla<br />
  Minecraft server. The same mind in all of them, not a bot per platform.
</p>

<p align="center">
  <a href="https://projectbea.emqnuele.dev"><b>Website</b></a> ·
  <a href="https://projectbea.emqnuele.dev/docs"><b>Documentation</b></a> ·
  <a href="#try-it-in-five-minutes"><b>Quick start</b></a> ·
  <a href="docs/contributing.md"><b>Contributing</b></a>
</p>

<p align="center">
  <a href="https://github.com/emqnuele/projectBEA/actions/workflows/ci.yml"><img src="https://github.com/emqnuele/projectBEA/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="#run-it-in-docker"><img src="https://img.shields.io/badge/docker-compose%20up-2496ED?logo=docker&logoColor=white" alt="Docker" /></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue" alt="Python" /></a>
  <a href="https://github.com/emqnuele/projectBEA/releases"><img src="https://img.shields.io/github/v/release/emqnuele/projectBEA" alt="Release" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/emqnuele/projectBEA" alt="License" /></a>
</p>

https://github.com/user-attachments/assets/00991f61-5eed-48cc-aefb-f2f6460120d7

<p align="center"><em>The control room: everything she is perceiving, thinking and doing, on one screen.</em></p>

---

## Not a chatbot

A chatbot waits for a message and answers it. Bea does not wait.

**She perceives.** Twitch chat, a voice in a Discord call, a death in Minecraft,
a donation, a note you typed. All of it arrives on one bus.
**She chooses.** An attention gate decides what is worth a thought, so a busy
room costs almost nothing.
**She remembers.** Not a context window. A diary, a card for everyone who turns
out to matter, and conclusions she reaches about herself overnight.
**She acts.** One mind, one set of tools, one place everything leaves from.
**She lives.** She streams her thoughts line by line, speaks them while she writes them, and her avatar breathes, blinks and reacts to the room in real time.

---

## Try it in five minutes

> [!IMPORTANT]
> One command. It installs `uv` if you don't have it, pulls the dependencies,
> builds the dashboard, asks you five questions and downloads the two models
> that run on your own machine.
> 
> **macOS / Linux**
> ```bash
> curl -LsSf https://raw.githubusercontent.com/emqnuele/projectBEA/main/install.sh | bash
> ```
> 
> **Windows (PowerShell)**
> ```powershell
> irm https://raw.githubusercontent.com/emqnuele/projectBEA/main/install.ps1 | iex
> ```

The default profile is **Solo chat**: the dashboard and her voice, one API key,
nothing else. No OBS, no Discord bot, no Minecraft server, no virtual audio
cable. Those are three separate profiles you can pick later, or turn on one at
a time from the Abilities screen.

Already cloned the repo? `uv run bea --setup` does the same thing — `make setup`
if you have Make. Every `make` target here is one `uv run` command underneath, so
nothing needs Make: Windows in particular does not ship it.

> [!NOTE]
> She needs an API key from OpenRouter, OpenAI or Groq.

---

## Updating without losing her

```bash
uv run bea --update
```

Not `git pull`. The files that hold who she is — her soul, her operating manual
— ship with the engine *and* are yours to rewrite. A plain pull either refuses
to run or writes conflict markers straight into the text her personality is read
from, and nobody finds out until she starts talking like someone else.

`--update` backs up your prompts, your config and your memory first, then
merges the new version *into* your edits the way git merges a branch: you keep
the character you wrote, and the engine still gets the improvements to its own
instructions. If a change lands on the exact lines you rewrote, yours stays
untouched and the new one is left beside it to compare.

The dashboard does the same with a button, tells you when there is something
new, and shows you the two versions side by side when a file needs your call.

Updating in place is the only thing here that needs `git` installed. Without it
she runs exactly the same, and `uv run bea --doctor` tells you what you are
missing.

**[What it does, and what it refuses to do →](docs/updating.md)**

---

## She remembers you

<img src="assets/remembers.png" align="right" width="290" alt="Bea" />

Tell her who you are on Monday. Come back on Sunday and she knows.

Three layers, all of them in one SQLite file you can open, inspect, back up or
delete, in `data/bea.db`:

- **The diary.** What happened, in her words, written as she goes. Recall runs
  over it with local embeddings, so remembering something costs no API call.
- **Person cards.** A tally for everyone she meets, and a card for the ones who
  turn out to matter. Talk to her enough and you get promoted from a number to a
  person.
- **Self-lore.** Overnight she sleeps, consolidates the day, and works out
  things about herself. Those conclusions come back as facts she holds about who
  she is.

This is the difference between an AI chatbot and an AI character, and it is the
part you cannot fake with a longer prompt.

**[How memory works →](docs/skills/memory.md)** · **[Social →](docs/skills/social.md)** · **[Dream →](docs/skills/dream.md)**

<br clear="right" />

---

## She has a body

<img src="assets/minecraft.png" align="left" width="290" alt="Bea in Minecraft" />

Not "Minecraft integration". A body, on a vanilla server, that other people can
walk up to.

She does not pilot it block by block. She hands it an intention, *get a stone
pickaxe*, and carries on with the conversation she was already having while it
goes and does that. The body runs its own think/act/observe loop on the cheap
model pool, up to 24 steps, with a survival guide and a notebook it rewrites as
it goes.

Only a milestone climbs back up to her mid-goal: a block mined, a tool crafted,
an interrupt, a death. Moving and looking are means, not results.

Players who talk to her in game chat get an `Author` like anyone else, so the
roster, the person cards and the attention gate all work in-game with no
Minecraft-specific code.

It runs on **[BeaCraft](https://github.com/emqnuele/projectBEA/releases)**, a
client-side Fabric mod that simulates input and sends ordinary packets. The
server sees a normal player. Nothing is needed server-side.

**[How the skill is built →](docs/skills/minecraft.md)**

<br clear="left" />

---

## How she looks on stream

Three ways to put her on screen. Pick one in **Settings → Stream**, with a live
preview of what the stream will see.

![The stream preview showing Bea's 3D model](assets/3dmodel.png)

| | What it is | What you need |
|---|---|---|
| **Images** | One picture per mood, swapped in OBS | Your PNGs |
| **3D model** | A VRM in an OBS browser source | A `.vrm` file |
| **VTube Studio** | Your own Live2D model, driven over its API | VTube Studio running |

Her speech bubble is a separate choice — an OBS text source, the same browser
source, or nothing — so you can mix them however you like.

For the 3D route, `make model` downloads a free model to start from. If you go
looking for your own, run it through the inspector first:

```bash
uv run python tools/inspect_vrm.py your-model.vrm
```

It tells you whether the model can do what she needs — a mouth that moves, a face
per mood — and reads out the licence the file carries, so you know what you are
allowed to stream with it. Her gestures are `.vrma` clips: drop them in
`data/clips` and assign one per mood.

Whichever you pick, the mood she chooses for a line drives all of it. A semantic
picker maps whatever expression she names to the nearest one your model actually
has. Her avatar blinks, breathes, and looks around on its own, and her mouth
follows the audio as it plays.

**[How it works, and how to add a backend →](docs/modules/avatar.md)**

---

## A busy chat costs almost nothing

Answering every message is what makes an always-on persona expensive to run and
exhausting to watch. Bea reacts to what concerns her and merely notices the rest.

```
   30 messages a minute   ────────▶   4 model calls
```

That is a measured number, not an illustration:
`test_thirty_messages_a_minute_stay_under_four_model_calls` asserts it on every
commit.

| Outcome | Cost | When |
|---|---|---|
| **React** | one model call | Addressed by name, spoken to directly, or something her own body reported. Goes through unconditionally, past cooldown and quiet hours. |
| **Note** | none | Worth knowing, not worth stopping for. Becomes peripheral awareness she can bring up later, without having interrupted what she was doing. |
| **Drop** | none | The volume of a busy chat. It still moves the room's activity level, so a loud stream feels loud to her, but no single message becomes a thought. |

**[The attention gate →](docs/architecture.md)**

---

## She sleeps

<img src="assets/dream.png" align="right" width="290" alt="Bea sleeping" />

At the end of the day she goes quiet, and a nightly pass consolidates what
happened: the diary is compacted, the people who mattered get promoted, and she
works out a handful of things about herself that come back tomorrow as facts she
holds.

It is the cheapest interesting thing in the system and the one people ask about
most.

**[Dream and self-lore →](docs/skills/dream.md)**

<br clear="right" />

---

## Where she lives

Every one of these is a **Skill**: a plugin that can perceive, expose tools,
contribute prompt rules and own its own infrastructure. All of them can be
switched on or off at runtime from the dashboard, and she can never arm one
herself.

| Skill | What it is |
|---|---|
| **[Discord](docs/skills/discord.md)** | Voice calls and text channels; owns a small Node.js bot for the audio pipeline |
| **[Telegram](docs/skills/telegram.md)** | Private chats and groups, polled in-process |
| **[Twitch](docs/skills/twitch.md)** | Chat read anonymously, no token needed; volume becomes texture, not thoughts |
| **[Minecraft](docs/skills/minecraft.md)** | A body on a vanilla server: she plays toward objectives, reads game chat, remembers players |
| **[Donations](docs/skills/donations.md)** | A webhook that always earns a reaction |
| **[Stream Plan](docs/skills/plan.md)** | Today's objectives, set by the owner; she works through them and ticks them off |
| **[Memory](docs/skills/memory.md)** | Diary entries and recall, over one SQLite file |
| **[Social](docs/skills/social.md)** | Who people are: a tally for everyone, a card for the ones who matter |
| **[Dream](docs/skills/dream.md)** | Sleep, self-lore and nightly consolidation |
| **[Monologue](docs/skills/monologue.md)** | Filling the silence when nothing is happening |

**[The Skill API →](docs/skills/overview.md)**

---

## The control room

`uv run bea --web` starts a FastAPI backend on port 8000 and serves a React +
Tailwind frontend. It opens on a boot screen that checks the brain is actually
answering before it lets you in, then on a bento overview of everything at once.

![The overview screen: her state, the attention gate, today's plan and the live feed](docs/images/dashboard-overview.jpg)

- **Overview.** Is she awake, what she last said, today's progress, the attention gate, spend, abilities and the live feed, on one screen
- **Talk.** The private line to her: streams voice in and out, and shows it plainly when she hears you and chooses not to answer
- **Today.** The orders she reads every turn, plus objectives you can reorder, edit and close; she closes them herself as she goes
- **Activity.** The attention gate drawn live, over a filterable, freezable event stream, plus a full Turn Log of every decision she makes
- **Memory.** Who she knows, everyone she has met, a search over what she remembers, and the things she has worked out about herself
- **Abilities.** Every capability on or off at runtime, plus the Minecraft cockpit
- **Maintenance.** Whether there is a new version and what is in it, with a button that installs it; and the same diagnostic `--doctor` runs, streamed as it goes
- **Settings.** Eight sections with connection tests, and one save for all of them. API keys and bot tokens typed here go to `.env`, never to `config.json`

`⌘K` opens the command palette from anywhere.

> The API has no authentication, so the server binds to `127.0.0.1` unless
> `--host` says otherwise. Do not put it on a public address as it stands.

Her avatar is swapped by mood over the OBS WebSocket, with an animated text
bubble for what she is saying.

**[API Reference →](docs/web/api.md)** · **[Frontend →](docs/web/frontend.md)** · **[OBS →](docs/modules/obs.md)**

---

## Architecture

Every sense pushes onto one bus. An attention gate decides what is worth a
thought. One mind reasons over it and acts through tools.

```
  discord · telegram · twitch · minecraft · donations · the dashboard
                          │  perceptions
                          ▼
                  ┌───────────────┐
                  │ PerceptionBus │
                  └───────┬───────┘
                          ▼
                  ┌───────────────┐   react / note / drop
                  │   Attention   │───────────────┐
                  └───────┬───────┘               │
            react ────────┤                       │ noted
                          ▼                       ▼
        ┌─────────────────────────┐        [WHILE YOU WERE BUSY]
        │  the live loop (stage)  │        peripheral awareness
        │  voice · game · owner   │
        └────────────┬────────────┘
                     │  written channels
                     ▼
        ┌──────────────────────────┐
        │ scoped conversation turns│  one per channel, in parallel
        └──────────────────────────┘
                     │
                     ▼  tools
   speak · mc_chat · discord_reply · play_minecraft · objective_done · …
                     │
                     ▼
        Expression → TTS + OBS      ·      bea.db (memory)
```

Three invariants hold it together: one bus, one mind, one sink. They are
written down in **[Contributing](docs/contributing.md#the-three-invariants)**,
because breaking one is the kind of change worth agreeing on first.

**[Full architecture →](docs/architecture.md)** · **[Repository layout →](docs/architecture.md#repository-layout)**

---

## Swappable everything

Three kinds of component, each defined by an abstract interface in
`src/interfaces/base_interfaces.py`. Any provider can be swapped without
touching the core.

| Component | Interface | Implementations |
|---|---|---|
| **LLM** | `LLMClient` (tool-aware) | OpenRouter, OpenAI, Groq |
| **TTS** | `TTSInterface` | EdgeTTS (free), Kokoro (local ONNX), Orpheus (API) |
| **STT** | `STTInterface` | Local Whisper (faster-whisper), Groq, OpenRouter |
| **Avatar** | `AvatarInterface` | Images (OBS), 3D model (VRM), VTube Studio |
| **Caption** | `CaptionInterface` | OBS text source, browser source, off |
| **OBS** | `OBSInterface` | OBS WebSocket |

Models are configured per **role**, not one at a time: `mind` for the
consciousness, `background` for the diary, the dreamer and the game body. Each
role is a pool that round-robins to spread rate limits and falls back when a
provider is down. Hot reload is built in: change models, voices or settings at
runtime, without a restart.

**[LLM →](docs/modules/llm.md)** · **[TTS →](docs/modules/tts.md)** · **[STT →](docs/modules/stt.md)** · **[Avatar →](docs/modules/avatar.md)** · **[OBS →](docs/modules/obs.md)**

---

## Run it in Docker

One image carries the engine, the dashboard and the Discord bot.

```bash
make docker      # builds the image, then asks you the same five questions
make docker-up   # http://127.0.0.1:8000
```

Or without the Makefile:

```bash
cp config.example.json config.json && touch .env && docker compose run --rm setup && docker compose up
```

**What runs in a container:** the dashboard, her memory, Discord (voice
included, since it travels over the network), Telegram, Twitch and Minecraft.

**What does not:** her speaking out of your computer's speakers. That needs a
real audio device. On Linux, uncomment the `devices:` block in
`docker-compose.yml`. On macOS and Windows, Docker Desktop cannot pass an audio
device through at all, so if you are streaming with OBS, run her natively.

The compose file publishes the dashboard to `127.0.0.1:8000`, never to
`0.0.0.0`. OBS lives on the host, so point `obs_host` at `host.docker.internal`.

---

## Manual setup

`uv run bea --setup` covers all of this. Here it is by hand.

**Prerequisites:** [uv](https://docs.astral.sh/uv/) (it installs Python for
you), Node.js 18+ for the dashboard and the Discord bot, OBS Studio with the
WebSocket server enabled if you are streaming (*Tools -> WebSocket Server
Settings*), and a virtual audio cable such as
[VB-Audio Cable](https://vb-audio.com/Cable/) if you want her voice on a
separate track.

```bash
uv sync                    # or: make install
uv run bea --install-node  # or: make node   (the dashboard and the discord bot)
uv run bea --setup         # or: make setup  (writes config.json and .env for you)
```

Both of those need Node 20+. The discord bot is a node program of its own, so
turning the skill on without it leaves her looking enabled and never online.

Or by hand, copy `.env.example` to `.env`:

```env
OPENROUTER_API_KEY=sk-or-...
OPENAI_API_KEY=sk-...
GROQ_API_KEY=gsk_...
DISCORD_TOKEN=...
```

Then review `config.json` for your OBS source names, audio device, TTS voice and
which skills are enabled.

```bash
uv run bea                       # or: make run   (CLI mode)
uv run bea --web                 # or: make web   (dashboard on :8000)
uv run bea --llm-provider openrouter --tts-provider kokoro --web
```

**Tests and diagnostics:**

```bash
uv run bea --doctor  # or: make doctor
make test          # uv run pytest -q
make lint          # uv run ruff check src tests
```

1904 tests, and they run without network access or API keys: every model
client, surface and transport is faked. CI runs exactly `make test` and `make lint`.

> [!TIP]
> **Something broken?** If she stops answering, you lose audio, or the avatar
> breaks, run `uv run bea --doctor` (or `make doctor`) — or open **Maintenance** in the dashboard
> and press the button. Thirteen checks in the order the pieces depend on each
> other, stopping at the first thing that would stop her, each failure carrying
> the exact command that fixes it.

**[Setup guide →](docs/setup.md)** · **[Configuration →](docs/configuration.md)**

---

## Build your own

The plugin API is a base class and a registry.

| What | How |
|---|---|
| **A new LLM provider** | Extend `OpenAICompatibleClient`, add it to `_PROVIDERS` and `build_client()` |
| **A new TTS engine** | Implement `TTSInterface`, add the branch and the CLI choice in `src/cli.py` |
| **A new skill** | Extend `Skill`, register it in `AIVtuberBrain._build_consciousness()` |
| **A new text platform** | Extend `PlatformSkill`, and the roster, person cards, attention gate and scoped conversations come for free |

**[The Skill API →](docs/skills/overview.md)** · **[Contributing →](docs/contributing.md)**

---

## Documentation

Everything is written next to the code and rendered at
**[projectbea.emqnuele.dev/docs](https://projectbea.emqnuele.dev/docs)** from the
same source.

| | |
|---|---|
| [Architecture](docs/architecture.md) | System design, data flow, the event system |
| [Setup & Install](docs/setup.md) | Installation, OBS setup, audio routing |
| [Configuration](docs/configuration.md) | Every config field, CLI arg and `.env` var |
| [Updating](docs/updating.md) | How an update keeps the prompts you edited |
| [Skills Overview](docs/skills/overview.md) | The `Skill` API, the registry, every tool |
| [Modules](docs/modules/llm.md) | [LLM](docs/modules/llm.md) · [TTS](docs/modules/tts.md) · [STT](docs/modules/stt.md) · [Avatar](docs/modules/avatar.md) · [OBS](docs/modules/obs.md) |
| [Skills](docs/skills/overview.md) | [Memory](docs/skills/memory.md) · [Social](docs/skills/social.md) · [Dream](docs/skills/dream.md) · [Plan](docs/skills/plan.md) · [Discord](docs/skills/discord.md) · [Telegram](docs/skills/telegram.md) · [Twitch](docs/skills/twitch.md) · [Minecraft](docs/skills/minecraft.md) · [Donations](docs/skills/donations.md) · [Monologue](docs/skills/monologue.md) |
| [Web](docs/web/api.md) | [API reference](docs/web/api.md) · [Frontend](docs/web/frontend.md) |
| [Contributing](docs/contributing.md) | Where to start, the invariants, tests, pull requests |
| [Security](SECURITY.md) | What is in scope, and how to report it privately |

---

## About

Built by **[Emanuele Faraci](https://emanuelefaraci.com)** in Italy.

It started as a TTS script pointed at OBS. The interesting problem turned out
not to be making her talk. It was deciding when she should, what she should
still know a week later, and how one mind can be in five places without becoming
five bots. That is most of what is in here.

Pull requests are welcome. [Start here](docs/contributing.md).

## License

MIT. Use it, fork it, ship something with it. See [LICENSE](LICENSE).
