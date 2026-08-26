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
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from src.setup.config_plan import (
    PLATFORM_SKILLS,
    PROVIDER_KEYS,
    PROVIDER_MODELS,
    STT_PROVIDERS,
    apply_answers,
    env_updates,
)
from src.setup.env_file import merge_env

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
]

TTS_ENGINES: List[Tuple[str, str, str]] = [
    ("edge", "EdgeTTS", "Free, no key, good quality. Needs internet."),
    ("kokoro", "Kokoro", "Runs locally from an ONNX file you download yourself."),
    ("orpheus", "Orpheus", "Best quality, needs a Baseten endpoint and key."),
]

# a short curated list beats the full EdgeTTS catalogue, which is thousands long
VOICES: Dict[str, List[Tuple[str, str]]] = {
    "English (US)": [("en-US-AvaNeural", "Ava"), ("en-US-AndrewNeural", "Andrew")],
    "English (UK)": [("en-GB-SoniaNeural", "Sonia"), ("en-GB-RyanNeural", "Ryan")],
    "Italiano": [("it-IT-IsabellaNeural", "Isabella"), ("it-IT-DiegoNeural", "Diego")],
    "Español": [("es-ES-ElviraNeural", "Elvira"), ("es-ES-AlvaroNeural", "Álvaro")],
    "Français": [("fr-FR-DeniseNeural", "Denise"), ("fr-FR-HenriNeural", "Henri")],
    "Deutsch": [("de-DE-KatjaNeural", "Katja"), ("de-DE-ConradNeural", "Conrad")],
    "日本語": [("ja-JP-NanamiNeural", "Nanami"), ("ja-JP-KeitaNeural", "Keita")],
    "中文": [("zh-CN-XiaoxiaoNeural", "Xiaoxiao"), ("zh-CN-YunxiNeural", "Yunxi")],
    "Português (BR)": [("pt-BR-FranciscaNeural", "Francisca"), ("pt-BR-AntonioNeural", "Antônio")],
}

KEY_TEST_URLS = {
    "openrouter": "https://openrouter.ai/api/v1/key",
    "openai": "https://api.openai.com/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
}


# --- small terminal helpers -------------------------------------------------


def _rule(console: Console, step: str, title: str) -> None:
    console.print()
    console.rule(f"[dim]{step}[/dim]  [bold]{title}[/bold]", align="left", style="dim")
    console.print()


def _choose(console: Console, question: str, options: List[Tuple[str, str, str]],
            default: str) -> str:
    """A numbered menu. Returns the key of the chosen option."""
    for index, (key, label, hint) in enumerate(options, 1):
        mark = "[cyan]•[/cyan]" if key == default else " "
        console.print(f"  [bold cyan]{index}[/] {mark} [bold]{label}[/]")
        if hint:
            console.print(f"        [dim]{hint}[/]")
    console.print()

    default_index = next(str(i) for i, opt in enumerate(options, 1) if opt[0] == default)
    answer = Prompt.ask(
        f"  {question}",
        choices=[str(i) for i in range(1, len(options) + 1)],
        default=default_index,
        show_choices=False,
    )
    return options[int(answer) - 1][0]


def _ask_key(console: Console, label: str, env_var: str) -> str:
    """Asks for a secret, offering whatever is already in the environment."""
    existing = os.getenv(env_var, "")
    if existing:
        console.print(f"  [dim]{env_var} is already set ({existing[:6]}…). "
                      f"Press enter to keep it.[/dim]")
        entered = Prompt.ask(f"  {label}", password=True, default="", show_default=False)
        return entered or existing
    return Prompt.ask(f"  {label}", password=True, default="", show_default=False)


def _test_key(console: Console, provider: str, key: str) -> None:
    """Best effort: a failed check is a warning, never a reason to stop."""
    if not key or not Confirm.ask("  Test the key now?", default=True):
        return
    try:
        import requests

        with console.status("  [dim]calling the provider…[/dim]"):
            response = requests.get(
                KEY_TEST_URLS[provider],
                headers={"Authorization": f"Bearer {key}"},
                timeout=15,
            )
        if response.ok:
            console.print("  [green]✓[/green] The key works.")
        elif response.status_code in (401, 403):
            console.print("  [red]✗[/red] The provider rejected the key. "
                          "Setup continues — fix it in .env when you have the right one.")
        else:
            console.print(f"  [yellow]?[/yellow] Provider answered {response.status_code}. "
                          "Probably fine, but worth checking later.")
    except Exception as error:
        console.print(f"  [yellow]?[/yellow] Could not reach the provider ({error}). "
                      "Skipping the check.")


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
    model_field, default_model = PROVIDER_MODELS[provider]

    console.print()
    key = _ask_key(console, "API key", env_var)
    _test_key(console, provider, key)

    console.print()
    model = Prompt.ask("  Model", default=default_model)

    answers["llm_provider"] = provider
    answers["llm_key"] = key
    answers["llm_model"] = model


def _ask_voice(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "2/5", "Her voice")

    engine = _choose(console, "Engine", TTS_ENGINES, "edge")
    answers["tts_provider"] = engine

    if engine == "edge":
        console.print()
        languages = [(name, name, ", ".join(label for _, label in voices))
                     for name, voices in VOICES.items()]
        language = _choose(console, "Language", languages, "English (US)")
        console.print()
        voices = [(voice_id, label, "") for voice_id, label in VOICES[language]]
        answers["tts_voice"] = _choose(console, "Voice", voices, voices[0][0])

    elif engine == "orpheus":
        console.print()
        answers["orpheus_key"] = _ask_key(console, "Orpheus API key", "ORPHEUS_API_KEY")
        answers["orpheus_endpoint"] = Prompt.ask("  Endpoint URL",
                                                 default=os.getenv("ORPHEUS_ENDPOINT", ""))
        answers["orpheus_voice"] = Prompt.ask("  Voice", default="zoe")

    else:
        console.print("\n  [dim]Kokoro reads two files from the project root: "
                      "kokoro-v0_19.onnx and voices.bin.\n"
                      "  Download them once from the kokoro-onnx releases page.[/dim]")

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
    console.print("  Voice input needs Whisper, which only Groq and OpenRouter serve here.\n")

    if not Confirm.ask("  Enable voice input?", default=True):
        return

    provider = answers["llm_provider"]
    if provider in STT_PROVIDERS:
        answers["stt_provider"] = provider
        console.print(f"  [green]✓[/green] Reusing your {provider} key.")
        return

    console.print()
    choices = [option for option in PROVIDERS if option[0] in STT_PROVIDERS]
    stt_provider = _choose(console, "Transcription provider", choices, "groq")
    console.print()
    answers["stt_provider"] = stt_provider
    answers["stt_key"] = _ask_key(console, "API key", PROVIDER_KEYS[stt_provider][1])


def _ask_obs(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "4/5", "OBS")
    console.print("  Enable the WebSocket server first: OBS → Tools → WebSocket Server Settings.\n")

    if not Confirm.ask("  Connect to OBS?", default=True):
        return

    console.print()
    answers["obs"] = {
        "host": Prompt.ask("  Host", default="localhost"),
        "port": IntPrompt.ask("  Port", default=4455),
        "password": Prompt.ask("  Password", password=True, default="", show_default=False),
        "avatar_source": Prompt.ask("  Avatar source name", default="BeaPNG"),
        "text_source": Prompt.ask("  Text bubble source name", default="AIText"),
    }


def _ask_skills(console: Console, answers: Dict[str, Any]) -> None:
    _rule(console, "5/5", "Where she lives")
    console.print("  Every one of these is optional, and every one can be toggled later "
                  "from the dashboard.\n")

    skills: Dict[str, Dict[str, Any]] = {}

    if Confirm.ask("  Discord — voice calls and text channels?", default=False):
        skills["discord"] = {
            "token": _ask_key(console, "    Bot token", "DISCORD_TOKEN"),
            "admin_id": Prompt.ask("    Your Discord user id", default=""),
        }

    if Confirm.ask("  Telegram — private chats and groups?", default=False):
        skills["telegram"] = {
            "token": _ask_key(console, "    Bot token", "TELEGRAM_TOKEN"),
            "owner_id": Prompt.ask("    Your Telegram user id", default=""),
        }

    if Confirm.ask("  Twitch — read chat (anonymous, no token needed)?", default=False):
        channel = Prompt.ask("    Channel to read", default="")
        skills["twitch"] = {"channel": channel, "nick": channel}

    if Confirm.ask("  Minecraft — a body on a vanilla server?", default=False):
        skills["minecraft"] = {
            "server_url": Prompt.ask("    Mod WebSocket URL", default="ws://127.0.0.1:8080"),
        }

    if Confirm.ask("  Donations — a webhook that always earns a reaction?", default=False):
        skills["donations"] = {
            "token": Prompt.ask("    Shared secret", password=True, default="", show_default=False),
        }

    answers["skills"] = skills


def _write(console: Console, answers: Dict[str, Any]) -> None:
    import logging

    from src.core.config import BrainConfig

    secrets = env_updates(answers)
    if secrets:
        existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
        ENV_FILE.write_text(merge_env(existing, secrets), encoding="utf-8")

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
    table.add_row("Ears", answers.get("stt_provider") or "off")
    table.add_row("OBS", "connected" if answers.get("obs") else "off")

    armed = [name for name in PLATFORM_SKILLS if name in answers.get("skills", {})]
    table.add_row("Skills", ", ".join(armed) if armed else "memory, social and dream only")

    console.print()
    console.print(table)
    console.print()
    console.print(Panel(
        "[bold]make web[/bold]     the dashboard on http://127.0.0.1:8000\n"
        "[bold]make run[/bold]     the same engine, in the terminal\n\n"
        "[dim]Re-run this wizard any time with [/dim][bold]uv run bea --setup[/bold][dim]. "
        "Everything you chose is editable in Settings.[/dim]",
        title="[bold]Next[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))


def run_setup(console: Optional[Console] = None) -> int:
    """The whole wizard. Returns a process exit code."""
    console = console or Console()

    console.print()
    console.print(Panel(
        "[bold]Let's get Bea talking.[/bold]\n\n"
        "[dim]Five questions, and nothing you pick here is permanent — "
        "every answer is a field in Settings afterwards.[/dim]",
        title="[bold]ProjectBEA setup[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()

    _preflight(console)

    _rule(console, "0/5", "How much do you want running?")
    profile = _choose(console, "Profile", PROFILES, "solo")

    answers: Dict[str, Any] = {"skills": {}}
    try:
        _ask_llm(console, answers)
        _ask_voice(console, answers)
        _ask_ears(console, answers)
        if profile in ("stream", "full"):
            _ask_obs(console, answers)
        if profile == "full":
            _ask_skills(console, answers)
    except (KeyboardInterrupt, EOFError):
        console.print("\n\n  [yellow]Stopped. Nothing was written.[/yellow]\n")
        return 1

    _write(console, answers)
    _summary(console, answers)
    console.print()
    return 0
