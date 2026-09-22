"""The first-run wizard: from a fresh clone to a running Bea in a few answers.

It writes nothing the engine did not already read — `.env` for secrets and
`config.json` for the rest — so editing both by hand stays a first-class path.
The default profile deliberately arms nothing that needs OBS, a bot token or a
game server: the fastest way to lose a new user is to make them configure five
services before they hear her speak.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

from src.core import language as language_module

# which transcribers need no account, asked of the one place that builds them
from src.modules.STT.factory import LOCAL as STT_LOCAL
from src.modules.STT.faster_whisper_stt import WEIGHTS_MB
from src.modules.tts import providers
from src.setup import banner, tui
from src.setup.config_plan import (
    LOCAL_URLS,
    PLATFORM_SKILLS,
    PROVIDER_KEYS,
    PROVIDER_MODELS,
    PROVIDER_URL_DEFAULTS,
    PROVIDER_URLS,
    apply_answers,
    env_updates,
)
from src.setup.env_file import update_env
from src.setup.prefetch import Job, plan
from src.utils.huggingface import download_hint

ENV_FILE = Path(".env")
CONFIG_FILE = Path("config.json")

PROFILES: List[Tuple[str, str, str]] = [
    ("solo", "Solo chat", "Dashboard and voice only. No OBS, Discord, Twitch or Minecraft."),
    ("stream", "Streaming", "Adds OBS: avatar swap and the animated text bubble."),
    ("full", "Everything", "Walks through every skill, one at a time."),
]

PROVIDERS: List[Tuple[str, str, str]] = [
    ("openrouter", "OpenRouter", "One key, virtually any model. https://openrouter.ai/keys"),
    ("openai", "OpenAI", "Called directly. https://platform.openai.com/api-keys"),
    ("groq", "Groq", "Fastest, smallest catalogue. https://console.groq.com/keys"),
    ("google", "Google AI Studio", "Gemini with a free tier. https://aistudio.google.com/apikey"),
    ("claude", "Claude", "Anthropic, called directly. https://console.anthropic.com/"),
    ("local", "Local models", "Ollama or LM Studio on this machine. No key, nothing leaves the room."),
    ("openai_compat", "Custom OpenAI endpoint", "Any server speaking the OpenAI protocol."),
    ("anthropic_compat", "Custom Anthropic endpoint", "Any server speaking the Messages protocol."),
]

AVATARS: List[Tuple[str, str, str]] = [
    ("png", "Images", "One picture per mood, swapped in OBS. Nothing else to install."),
    ("model", "A 3D model", "A .vrm you bring, rendered in an OBS browser source."),
    ("vtube_studio", "VTube Studio", "Your own Live2D model, driven over its API."),
]

CAPTIONS: List[Tuple[str, str, str]] = [
    ("stage", "Browser source", "Typed in the page. One message per line instead of one per letter."),
    ("obs", "OBS text source", "Typed into a text source over WebSocket."),
    ("off", "Nothing", "She speaks; nothing is written on screen."),
]

STT_ENGINES: List[Tuple[str, str, str]] = [
    ("faster_whisper", "Local Whisper", "Runs on this machine. No key, no bill, nothing leaves the room."),
    ("groq", "Groq Whisper", "Hosted and very fast. Needs a Groq key."),
    ("openrouter", "OpenRouter", "The same Whisper models on your OpenRouter key."),
]


def disk_size(megabytes: int) -> str:
    """A size in the unit a person would say it in."""
    if not megabytes:
        return ""
    if megabytes < 1000:
        return f"~{megabytes} MB"
    return f"~{megabytes / 1000:.1f} GB"


# what the local transcriber costs to run, smallest first. Anything huggingface
# serves works in config.json; these are the four worth offering blind
WHISPER_SIZES: List[Tuple[str, str, str]] = [
    ("tiny", "tiny", f"{disk_size(WEIGHTS_MB['tiny'])}. Instant, and it will mishear you."),
    ("base", "base", f"{disk_size(WEIGHTS_MB['base'])}. Usable on an old laptop."),
    ("small", "small", f"{disk_size(WEIGHTS_MB['small'])}. The balance most people want."),
    ("large-v3-turbo", "large-v3-turbo",
     f"{disk_size(WEIGHTS_MB['large-v3-turbo'])}. Best, and it wants a GPU."),
]


def _language_options() -> List[Tuple[str, str, str]]:
    """Every language, with the engines that can actually speak it."""
    out = []
    for code, name in language_module.options():
        engines = ", ".join(p.label for p in providers.for_language(code))
        out.append((code, name, engines))
    return out


KEY_TEST_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "google": "https://generativelanguage.googleapis.com/v1beta/openai/models",
}


# --- small terminal helpers -------------------------------------------------


def _rule(console: Console, step: str, title: str) -> None:
    console.print()
    console.rule(f"[dim]{step}[/dim]  [bold]{title}[/bold]", align="left", style="dim")
    console.print()


def _choose(console: Console, question: str, options: List[Tuple[str, str, str]],
            default: str) -> str:
    """One option, chosen with the arrow keys. Returns its key.

    Every menu in the wizard goes through here, and `tui.select` falls back to
    the numbered prompt this used to be wherever there is no keyboard to read
    — a pipe, CI, the docker setup container.
    """
    return tui.select(console, question, options, default)


def _confirm(console: Console, question: str, default: bool = True) -> bool:
    """Yes or no. Same deal: arrows on a terminal, `y/n` everywhere else."""
    return tui.confirm(console, question, default)


def _ask_key(console: Console, label: str, env_var: str) -> str:
    """Asks for a secret, offering whatever is already in the environment."""
    existing = os.getenv(env_var, "")
    if existing:
        console.print(f"  [dim]{env_var} is already set ({existing[:6]}…). "
                      f"Press enter to keep it.[/dim]")
        entered = Prompt.ask(f"  {label}", password=True, default="", show_default=False)
        return entered or existing
    return Prompt.ask(f"  {label}", password=True, default="", show_default=False)


def _test_key(console: Console, provider: str, key: str, base_url: str = "") -> None:
    """Best effort: a failed check is a warning, never a reason to stop."""
    if provider in PROVIDER_URLS and not key:
        if not _confirm(console, "  No key given. Check the endpoint answers instead?"):
            return
    elif not key or not _confirm(console, "  Test the key now?"):
        return
    try:
        import requests

        if provider == "claude":
            url = "https://api.anthropic.com/v1/models"
        elif provider in PROVIDER_URLS:
            url = f"{base_url.rstrip('/')}/models"
        else:
            url = KEY_TEST_URLS[provider]
        with console.status("  [dim]calling the provider…[/dim]"):
            response = requests.get(url, headers=_key_headers(provider, key),
                                    timeout=15)
        if response.ok:
            console.print("  [green]✓[/green] The endpoint answers.")
        elif response.status_code in (401, 403):
            console.print("  [red]✗[/red] The endpoint rejected the key. "
                          "Setup continues — fix it in .env when you have the right one.")
        elif response.status_code == 404 and provider in PROVIDER_URLS:
            console.print("  [yellow]?[/yellow] Nothing serves the models list there. "
                          "Check the URL — it should end in /v1, without /chat/completions.")
        else:
            console.print(f"  [yellow]?[/yellow] Endpoint answered {response.status_code}. "
                          "Probably fine, but worth checking later.")
    except Exception as error:
        console.print(f"  [yellow]?[/yellow] Could not reach the endpoint ({error}). "
                      "Setup continues — check the URL and whether it is running.")


def _output_devices() -> List[Tuple[int, str]]:
    """Output devices, or an empty list wherever portaudio cannot open."""
    try:
        import sounddevice as sd

        return [
            (index, device["name"])
            for index, device in enumerate(sd.query_devices())
            if device.get("max_output_channels", 0) > 0
        ]
    except Exception:
        return []


# --- the steps --------------------------------------------------------------


def _preflight(console: Console) -> None:
    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_column(style="dim")
    table.add_column()

    version = sys.version_info
    python_ok = (3, 10) <= (version.major, version.minor) < (3, 13)
    table.add_row("Python", f"[{'green' if python_ok else 'red'}]"
                            f"{version.major}.{version.minor}.{version.micro}"
                            f"{'' if python_ok else '  (needs >=3.10, <3.13)'}[/]")

    for name, needed_for in (("uv", "dependencies"), ("node", "the dashboard and the Discord bot")):
        found = shutil.which(name)
        table.add_row(name, f"[green]{found}[/green]" if found
                      else f"[yellow]not found[/yellow] [dim]— needed for {needed_for}[/dim]")

    for path in (ENV_FILE, CONFIG_FILE):
        table.add_row(str(path), "[cyan]exists, will be updated[/cyan]" if path.exists()
                      else "[dim]will be created[/dim]")

    console.print(table)


def _ask_llm(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "1/5", "The mind")
    console.print("  Which service should she think with?\n")

    provider = _choose(console, "Provider", PROVIDERS, "openrouter")
    _, env_var = PROVIDER_KEYS[provider]
    _, default_model = PROVIDER_MODELS[provider]
    answers["llm_provider"] = provider

    url_field = PROVIDER_URLS.get(provider)
    if url_field:
        console.print()
        answers["llm_base_url"] = _ask_endpoint(
            console, provider, PROVIDER_URL_DEFAULTS.get(provider, ""))
        if provider == "local":
            console.print()
            key = _ask_key(console, "API key (almost never needed locally)", env_var)
            _test_key(console, provider, key, answers["llm_base_url"])
            answers["llm_key"] = key
            console.print()
            answers["llm_model"] = Prompt.ask("  Model", default=default_model)
            return
        console.print()
        answers["llm_key"] = _ask_key(console, "API key (empty if the endpoint wants none)",
                                      env_var)
        _test_key(console, provider, answers["llm_key"], answers["llm_base_url"])

    else:
        console.print()
        key = _ask_key(console, "API key", env_var)
        _test_key(console, provider, key)
        answers["llm_key"] = key

    console.print()
    while True:
        model = Prompt.ask("  Model", default=default_model or None)
        if (model or "").strip() or default_model:
            answers["llm_model"] = model or default_model
            return
        console.print("  [yellow]The model cannot be empty: only you know what "
                      "this endpoint serves.[/yellow]")


def _ask_endpoint(console: Console, provider: str, default: str) -> str:
    """Where a brought-your-own endpoint lives. Local runners get a menu."""
    if provider == "local":
        options = ([(url, name, "") for name, url in LOCAL_URLS.items()]
                   + [("custom", "Another URL", "A remote Ollama or any compatible server.")])
        picked = _choose(console, "Which runner", options, LOCAL_URLS["ollama"])
        if picked != "custom":
            return picked
        console.print()
    while True:
        url = Prompt.ask("  Endpoint base URL", default=default or None)
        cleaned = (url or "").strip()
        if cleaned:
            return cleaned
        console.print("  [yellow]The endpoint URL cannot be empty.[/yellow]")


def _key_headers(provider: str, key: str) -> Dict[str, str]:
    if provider == "claude":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {key}"}


def _ask_voice(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "2/5", "Her voice")

    # the language comes first and is a real answer, not a way of grouping a
    # voice menu — which is all it used to be, so it was thrown away and every
    # install ended up transcribing and answering in English
    console.print("  [dim]She answers whoever writes to her in their own language. "
                  "This is the one she\n  reaches for when she speaks first.[/dim]\n")
    language = _choose(console, "Language", _language_options(), language_module.AUTO)
    answers["language"] = language

    console.print()
    engines = [(p.id, p.label, p.blurb) for p in providers.for_language(language)]
    if len(engines) < len(providers.PROVIDERS):
        hidden = [p.label for p in providers.PROVIDERS.values()
                  if p.id not in {e[0] for e in engines}]
        console.print(f"  [dim]{', '.join(hidden)} cannot speak "
                      f"{language_module.endonym(language)}, so "
                      f"{'they are' if len(hidden) > 1 else 'it is'} not "
                      f"offered here.[/dim]\n")
    engine = _choose(console, "Engine", engines, engines[0][0])
    answers["tts_provider"] = engine

    if engine == "edge":
        console.print()
        provider = providers.PROVIDERS[engine]
        voices = [(v.id, v.label, language_module.endonym(v.language))
                  for v in providers.voices_for(provider, language)]
        answers["tts_voice"] = _choose(console, "Voice", voices, voices[0][0])

    elif engine == "orpheus":
        console.print()
        answers["orpheus_key"] = _ask_key(console, "Orpheus API key", "ORPHEUS_API_KEY")
        answers["orpheus_endpoint"] = Prompt.ask("  Endpoint URL",
                                                 default=os.getenv("ORPHEUS_ENDPOINT", ""))
        answers["orpheus_voice"] = Prompt.ask("  Voice", default="zoe")

    elif engine == "kokoro":
        console.print()
        provider = providers.PROVIDERS[engine]
        voices = [(v.id, v.label, "") for v in providers.voices_for(provider, language)]
        answers["kokoro_voice"] = _choose(console, "Voice", voices, voices[0][0])
        console.print("\n  [dim]The weights and the voice pack are downloaded on "
                      "first use, into the project root.[/dim]")

    console.print()
    devices = _output_devices()
    if not devices:
        console.print("  [dim]No audio devices visible from here — leaving the output on the "
                      "system default. Change it later in Settings.[/dim]")
        return

    console.print("  Where should she speak?\n")
    options = [(str(index), name, "") for index, name in devices[:12]]
    answers["audio_device_id"] = int(_choose(console, "Output device", options, options[0][0]))


def _ask_ears(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "3/5", "Her ears")
    console.print("  Voice input runs Whisper, either on this machine or on someone else's.\n")

    if not _confirm(console, "  Enable voice input?"):
        return

    console.print()
    engine = _choose(console, "Transcriber", STT_ENGINES, "faster_whisper")
    answers["stt_provider"] = engine

    if engine in STT_LOCAL:
        console.print("\n  [dim]The weights are downloaded once into data/models/whisper. "
                      "No key, no account.[/dim]\n")
        answers["stt_model"] = _choose(console, "Model size", WHISPER_SIZES, "small")
        return

    # the mind's key already covers it when both sides are the same provider
    if engine == answers["llm_provider"]:
        console.print(f"  [green]✓[/green] Reusing your {engine} key.")
        return

    console.print()
    answers["stt_key"] = _ask_key(console, "API key", PROVIDER_KEYS[engine][1])


def _download(console: Console, job: Job) -> bool:
    """One download, with a bar, and a warning instead of a stack trace.

    Failing here costs nothing but the wait it was meant to take out of her
    first sentence: the engine fetches whatever is missing on first use.
    """
    total = job.megabytes * 1_000_000 or None
    with Progress(SpinnerColumn(), TextColumn("  [dim]{task.description}[/dim]"),
                  BarColumn(complete_style="cyan", finished_style="green"),
                  DownloadColumn(), TimeRemainingColumn(compact=True),
                  console=console, transient=True) as progress:
        task = progress.add_task(job.label, total=total)
        error = job.fetch(lambda done: progress.update(
            task, completed=min(done, total) if total else done))

    if not error:
        console.print(f"  [green]✓[/green] {job.label} — ready in {job.root}.")
        return True

    console.print(f"  [yellow]?[/yellow] {job.label} — the download did not finish ({error}).")
    hint = download_hint(error)
    if hint:
        console.print(f"  [dim]{hint}[/dim]")
    return False


def _ask_hf_token(console: Console) -> None:
    """Offers to use a Hugging Face token, and is clear that it is not needed.

    The weights are public and no account is involved. A token does exactly
    one thing here: it lifts the per-IP rate limit, which is what makes a
    download crawl on a shared or office connection. Saying "optional" without
    saying what it buys is how a person ends up making an account they did not
    need — or skipping the one line that would have made this take a minute.
    """
    if os.getenv("HF_TOKEN"):
        console.print("  [green]✓[/green] Using the HF_TOKEN already in your environment.")
        console.print()
        return

    console.print("  [dim]Optional: a Hugging Face token. Nothing here needs an account — "
                  "the weights\n  are public and download fine without one. A token only "
                  "raises the rate limit,\n  which makes this faster on a shared or office "
                  "connection. Enter to skip.[/dim]")
    console.print("  [dim]https://huggingface.co/settings/tokens[/dim]\n")

    token = Prompt.ask("  Hugging Face token [dim](optional)[/dim]", password=True,
                       default="", show_default=False).strip()
    console.print()
    if not token:
        return

    # in this process too, not only in .env: the downloads below are about to
    # read it, and nothing reloads the file between here and there
    os.environ["HF_TOKEN"] = token
    update_env(ENV_FILE, {"HF_TOKEN": token})
    console.print("  [green]✓[/green] Saved to .env, and used for the downloads below.\n")


def _ask_downloads(console: Console, answers: Dict[str, Any]) -> None:
    """Fetches the two models that would otherwise arrive mid-conversation.

    Her memory needs the embedder whether or not anything else was armed, so
    this step is not tied to any of the answers above.
    """
    from src.core.config import BrainConfig

    jobs = plan(BrainConfig(), answers)

    if not jobs:
        console.print("  [green]✓[/green] Everything she needs is already on this machine.")
        return

    what = "one model" if len(jobs) == 1 else f"{len(jobs)} models"
    console.print(f"  She needs {what} from Hugging Face, "
                  f"{disk_size(sum(job.megabytes for job in jobs))} in all. No account and "
                  "no key —\n  and fetching them now means her first sentence is not spent "
                  "waiting for one.\n")

    if not _confirm(console, "  Download them now?"):
        console.print("  [dim]They will be fetched the first time each one is needed.[/dim]")
        return

    console.print()
    _ask_hf_token(console)
    done = [_download(console, job) for job in jobs]
    if not all(done):
        console.print("  [dim]Setup is finished either way — she fetches whatever is still "
                      "missing the first time she needs it.[/dim]")


def needs_obs(avatar: str, caption: str) -> bool:
    """Whether anything she shows still goes through the OBS WebSocket."""
    return avatar == "png" or caption == "obs"


def needs_browser_source(avatar: str, caption: str) -> bool:
    """Whether anything she shows is drawn by the stage page."""
    return avatar == "model" or caption == "stage"


def _ask_stage(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "4/5", "How she appears")
    console.print("  Two separate choices: what the audience sees of her, and how her "
                  "words are shown.\n")

    avatar = _choose(console, "Avatar", AVATARS, "png")
    console.print()
    caption = _choose(console, "Speech bubble", CAPTIONS, "stage")
    console.print()

    stage: Dict[str, Any] = {"avatar_backend": avatar, "caption_backend": caption}

    if avatar == "model":
        console.print("  No model ships with projectBEA. Run "
                      "`uv run python tools/fetch_model.py` afterwards for\n  the free "
                      "sample, or point this at your own .vrm.\n")
        stage["model_path"] = Prompt.ask("  Model file", default="data/models/VRM1_Constraint_Twist_Sample.vrm")
        console.print()
    elif avatar == "vtube_studio":
        console.print("  Turn the plugin API on first: VTube Studio → Settings → "
                      "Start API. She will ask to be allowed the first time.\n")
        stage["vts_port"] = IntPrompt.ask("  API port", default=8001)
        console.print()

    answers["stage"] = stage

    # two independent questions, because both can be true at once: images in an
    # OBS source with her words typed in the browser needs OBS *and* the page
    if needs_obs(avatar, caption):
        console.print("  That needs OBS. Enable the WebSocket server first: "
                      "OBS → Tools → WebSocket Server Settings.\n")
        if _confirm(console, "  Connect to OBS?"):
            console.print()
            obs: Dict[str, Any] = {
                "host": Prompt.ask("  Host", default="localhost"),
                "port": IntPrompt.ask("  Port", default=4455),
                "password": Prompt.ask("  Password", password=True, default="", show_default=False),
            }
            if avatar == "png":
                obs["avatar_source"] = Prompt.ask("  Avatar source name", default="BeaPNG")
            if caption == "obs":
                obs["text_source"] = Prompt.ask("  Text bubble source name", default="AIText")
            answers["obs"] = obs
            console.print()

    if needs_browser_source(avatar, caption):
        console.print("  Add a Browser Source in OBS pointing at http://127.0.0.1:8000/stage,")
        console.print("  and untick 'Shutdown source when not visible' so she keeps her pose.\n")


# the platforms she can live on, in the order config_plan arms them. The
# details each one needs are asked only for the ones that were ticked.
SURFACES: List[Tuple[str, str, str]] = [
    ("discord", "Discord", "Voice calls and text channels. Needs a bot token."),
    ("telegram", "Telegram", "Private chats and groups. Needs a bot token."),
    ("twitch", "Twitch", "Reads chat anonymously. No token needed."),
    ("minecraft", "Minecraft", "A body on a vanilla server, through the mod."),
    ("donations", "Donations", "A webhook that always earns a reaction."),
]


def _ask_skills(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "5/5", "Where she lives")
    console.print("  Every one of these is optional, and every one can be toggled later "
                  "from the dashboard.\n")

    picked = tui.multiselect(console, "Pick her surfaces", SURFACES)
    skills: Dict[str, Dict[str, Any]] = {}

    if picked:
        console.print()

    for name in picked:
        skills[name] = _ask_surface(console, name)

    answers["skills"] = skills


def _ask_surface(console: Console, name: str) -> Dict[str, Any]:
    """What one ticked surface still needs to know."""
    label = dict((value, text) for value, text, _ in SURFACES)[name]
    console.print(f"  [bold]{label}[/]")

    if name == "discord":
        return {
            "token": _ask_key(console, "    Bot token", "DISCORD_TOKEN"),
            "admin_id": Prompt.ask("    Your Discord user id", default=""),
        }
    if name == "telegram":
        return {
            "token": _ask_key(console, "    Bot token", "TELEGRAM_TOKEN"),
            "owner_id": Prompt.ask("    Your Telegram user id", default=""),
        }
    if name == "twitch":
        channel = Prompt.ask("    Channel to read", default="")
        return {"channel": channel, "nick": channel}
    if name == "minecraft":
        return {"server_url": Prompt.ask("    Mod WebSocket URL", default="ws://127.0.0.1:8080")}
    return {"token": Prompt.ask("    Shared secret", password=True, default="",
                                show_default=False)}


def _write(console: Console, answers: Dict[str, Any]) -> None:
    import logging

    from src.core.config import BrainConfig

    secrets = env_updates(answers)
    if secrets:
        update_env(ENV_FILE, secrets)

    # BrainConfig loads config.json in __post_init__, so anything the wizard does
    # not ask about survives a re-run untouched
    config = apply_answers(BrainConfig(), answers)

    # the app logger would print a timestamped line through the middle of the
    # summary; the two lines below say the same thing in this screen's voice
    config_logger = logging.getLogger("bea.config")
    previous_level = config_logger.level
    config_logger.setLevel(logging.WARNING)
    try:
        config.save_to_file()
    finally:
        config_logger.setLevel(previous_level)

    console.print()
    console.print(f"  [green]✓[/green] {ENV_FILE} — {len(secrets)} secret(s)")
    console.print(f"  [green]✓[/green] {CONFIG_FILE} — everything else")


def _summary(console: Console, answers: Dict[str, Any]) -> None:
    table = Table(show_header=False, box=None, padding=(0, 3, 0, 0))
    table.add_column(style="dim")
    table.add_column(style="bold")

    table.add_row("Mind", f"{answers['llm_provider']} · {answers['llm_model']}")
    table.add_row("Voice", answers.get("tts_voice") or answers.get("tts_provider", "edge"))
    ears = answers.get("stt_provider") or "off"
    if answers.get("stt_model"):
        ears = f"{ears} · {answers['stt_model']}"
    table.add_row("Ears", ears)
    stage = answers.get("stage", {})
    table.add_row("Avatar", dict((a[0], a[1]) for a in AVATARS).get(stage.get("avatar_backend", "png"), "Images"))
    table.add_row("Speech bubble", dict((c[0], c[1]) for c in CAPTIONS).get(stage.get("caption_backend", "obs"), "OBS text source"))
    table.add_row("OBS", "connected" if answers.get("obs") else "off")

    armed = [name for name in PLATFORM_SKILLS if name in answers.get("skills", {})]
    table.add_row("Skills", ", ".join(armed) if armed else "memory, social and dream only")

    console.print()
    console.print(table)
    console.print()
    console.print(Panel(
        "[bold]uv run bea --web[/bold]       the dashboard on http://127.0.0.1:8000\n"
        "[bold]uv run bea[/bold]             the same engine, in the terminal\n"
        "[bold]uv run bea --doctor[/bold]    checks this machine and says what to fix\n\n"
        "[dim]Re-run this wizard any time with [/dim][bold]uv run bea --setup[/bold][dim] — "
        "everything you chose\nis editable in Settings. With make installed, "
        "`make web`, `make run` and\n`make doctor` are the same three commands.[/dim]\n\n"
        f"[dim]Everything she can do, written down: [/dim]{banner.DOCS}",
        title="[bold]Next[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))


def run_setup(console: Optional[Console] = None) -> int:
    """The whole wizard. Returns a process exit code."""
    console = console or Console()

    banner.show(console, "Let's get her talking.")
    console.print("  [dim]Five questions, and nothing you pick here is permanent — every "
                  "answer is a\n  field in Settings afterwards. Arrow keys to move, enter "
                  "to choose.[/dim]\n")

    _preflight(console)

    _rule(console, "0/5", "How much do you want running?")
    profile = _choose(console, "Profile", PROFILES, "solo")

    answers: Dict[str, Any] = {"skills": {}}
    try:
        _ask_llm(console, answers)
        _ask_voice(console, answers)
        _ask_ears(console, answers)
        if profile in ("stream", "full"):
            _ask_stage(console, answers)
        if profile == "full":
            _ask_skills(console, answers)
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n  [yellow]Stopped. Nothing was written.[/yellow]\n")
        return 1

    _write(console, answers)

    # after the write on purpose: a download interrupted here still leaves a
    # configured install behind
    _rule(console, "last", "What she needs on disk")
    try:
        _ask_downloads(console, answers)
    except (KeyboardInterrupt, EOFError):
        console.print("\n  [yellow]Stopped the download.[/yellow] "
                      "[dim]She will fetch what is missing when she needs it.[/dim]")

    _summary(console, answers)
    console.print()
    return 0
