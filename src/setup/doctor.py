"""`bea --doctor`: find out what is broken, and what to type to fix it.

The wizard runs once. Everything it set up can stop working afterwards — a key
expires, an audio device is unplugged, OBS is not open, a model is renamed by
its provider, someone edits the operating manual and removes the one line that
tells her how to speak. Until now the only thing between that and giving up was
a log file.

So: a fixed sequence of checks, each one small enough to name a single cause,
run in the order the pieces depend on each other and **stopped at the first
blocking failure**. There is no point testing the voice when there is no config
file, and a page of red is a page nobody reads. Every failure carries the exact
thing to do about it.

Checks are ordinary async functions returning a `Finding`, and they take the
config rather than a running brain: what breaks in the field is the machine and
its services, not the wiring — CI already assembles the brain on every push.
That is also what makes every one of them testable without a sound card, a key
or a network.
"""

import asyncio
import os
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from src.core import config as config_module
from src.core.agent.registry import BACKGROUND, MIND, looks_like_missing_tool_support
from src.core.config import BrainConfig
from src.core.expression.tags import DIRECTIONS
from src.core.mind.operating import missing_tools
from src.core.stage import installed_clips

ENV_FILE = Path(".env")

# the built dashboard, which is also the page her 3D body is drawn on
DASHBOARD = Path("src/web/frontend/dist/index.html")

# a line short enough to synthesise quickly and distinctive enough that hearing
# it back is evidence rather than a coincidence
TEST_LINE = "one two three"

# where the dashboard listens unless it is told otherwise
DEFAULT_PORT = 8000


@dataclass(frozen=True)
class Finding:
    """What one check found, and what to do if it is bad news.

    `blocking` is the difference between "nothing below this can work" and
    "this one thing will not". A missing config file stops the run; a missing
    Twitch channel does not.
    """

    ok: bool
    detail: str = ""
    fix: str = ""
    blocking: bool = True

    @property
    def stops(self) -> bool:
        return not self.ok and self.blocking


def passed(detail: str = "") -> Finding:
    return Finding(True, detail)


def failed(detail: str, fix: str = "", blocking: bool = True) -> Finding:
    return Finding(False, detail, fix, blocking)


def warned(detail: str, fix: str = "") -> Finding:
    return Finding(False, detail, fix, blocking=False)


# --- the checks --------------------------------------------------------------


async def check_python(config: BrainConfig) -> Finding:
    version = sys.version_info
    if not (3, 10) <= (version.major, version.minor) < (3, 13):
        return failed(
            f"Python {version.major}.{version.minor} — she needs >=3.10 and <3.13",
            "uv python install 3.12 && uv sync",
        )
    if not shutil.which("uv"):
        return warned("uv is not on PATH",
                      "Install it from https://docs.astral.sh/uv/ — everything "
                      "else in this project assumes it.")
    return passed(f"Python {version.major}.{version.minor}.{version.micro}")


async def check_config(config: BrainConfig) -> Finding:
    # read off the module rather than imported once: it is the same file the
    # engine reads, and the engine can be pointed at another one
    settings = Path(config_module.CONFIG_FILE)
    if not settings.is_file():
        return failed(f"{settings} is not there", "uv run bea --setup")
    if not ENV_FILE.is_file():
        return warned(f"{ENV_FILE} is not there — every key is coming from the "
                      "environment instead",
                      "uv run bea --setup")
    return passed(f"{settings} and {ENV_FILE}")


async def check_keys(config: BrainConfig) -> Finding:
    """Every provider the pools actually name has a key on this machine."""
    wanted = set()
    for role in (MIND, BACKGROUND):
        for entry in config.models.get(role) or []:
            if ":" in str(entry):
                wanted.add(str(entry).split(":", 1)[0])
    if not wanted:
        wanted.add(config.llm_provider)

    missing = [name for name in sorted(wanted) if not _key_for(config, name)]
    if missing:
        return failed(f"no key for {', '.join(missing)}",
                      f"Put {', '.join(_env_var(name) for name in missing)} in {ENV_FILE}, "
                      f"or run `uv run bea --setup`.")
    return passed(", ".join(sorted(wanted)))


async def check_mind(config: BrainConfig) -> Finding:
    """She answers, and she can call a tool — which is how she speaks at all."""
    from src.core.agent.registry import ModelPoolError, ModelRegistry

    try:
        client = ModelRegistry(config).get(MIND)
    except ModelPoolError as e:
        return failed(str(e), "Check `models.mind` in config.json.")

    tool = [{"type": "function", "function": {
        "name": "answer", "description": "Answer the question.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}}]
    try:
        reply = await client.complete(
            [{"role": "user", "content": "Call answer with the text 'ok'."}], tools=tool)
    except Exception as e:
        if looks_like_missing_tool_support(e):
            return failed(
                f"{_model_of(client)} cannot call tools, so she can never speak",
                "Every model in `models.mind` needs tool calling. Swap it for one "
                "that has it — the docs list what works.")
        return failed(f"the mind did not answer ({e})",
                      "Check the key, the model id and whether the provider is up.")

    if not reply.tool_calls:
        return warned(
            f"{_model_of(client)} answered, but ignored the tool it was handed",
            "She speaks by calling `speak`. A model that will not call tools "
            "reliably will stand there in silence.")
    return passed(f"{_model_of(client)} answered and called a tool")


async def check_manual(config: BrainConfig) -> Finding:
    """The manual in force still explains the two things it has to."""
    from src.utils.prompts import load_text

    rules = load_text(config.operating_prompt_path) or load_text(config.system_prompt_path)
    if not rules:
        return warned(f"{config.operating_prompt_path} is empty or missing",
                      "She falls back to the built-in manual, which works — but "
                      "anything you wrote in that file is not being used.")

    missing = missing_tools(rules, ["speak", "stay_silent"])
    if missing:
        return failed(
            f"the operating manual never mentions {', '.join(missing)}",
            f"Add them back to {config.operating_prompt_path}, or delete the file "
            f"to fall back to the built-in manual.")

    if not any(f"<{kind}:" in rules for kind in DIRECTIONS):
        return warned(
            "the manual does not explain the direction she can write inline",
            f"Without it she never writes <{DIRECTIONS[0]}:…> or "
            f"<{DIRECTIONS[1]}:…>, so her face only changes once per line.")
    return passed("the manual names her tools and her direction")


async def check_speakers(config: BrainConfig) -> Finding:
    try:
        import sounddevice as sd
    except Exception as e:
        return failed(f"no audio library on this machine ({e})",
                      "uv sync — and on Linux, install libportaudio2.")

    try:
        outputs = [d for d in sd.query_devices() if d.get("max_output_channels", 0) > 0]
    except Exception as e:
        return failed(f"no audio device could be listed ({e})",
                      "On Linux check that PulseAudio or PipeWire is running.")

    if not outputs:
        return failed("this machine has no audio output at all",
                      "Plug something in, or run her with the stage backends only.")

    wanted = config.audio_device_id
    try:
        info = sd.query_devices(wanted)
        if info.get("max_output_channels", 0) > 0:
            return passed(f"device {wanted}: {info.get('name', wanted)}")
    except Exception:
        pass
    return warned(
        f"audio_device_id {wanted} is not an output; she will fall back to another",
        "Set `audio_device_id` in config.json to one of: "
        + ", ".join(f"{i} ({d['name']})" for i, d in enumerate(sd.query_devices())
                    if d.get("max_output_channels", 0) > 0))


async def check_voice(config: BrainConfig) -> Finding:
    """She makes a sound. Nothing is played — this is about the engine."""
    from src.modules.tts.factory import build_tts

    try:
        tts = build_tts(config)
    except Exception as e:
        return failed(f"the {config.tts_provider} voice could not be built ({e})",
                      "Check `tts_provider` and its settings in config.json.")

    try:
        audio, rate = await tts.generate_audio(TEST_LINE)
    except Exception as e:
        return failed(f"{config.tts_provider} produced nothing ({e})",
                      _voice_fix(config))

    seconds = (getattr(audio, "size", 0) or 0) / max(1, rate)
    if seconds <= 0:
        return failed(f"{config.tts_provider} answered with silence", _voice_fix(config))
    return passed(f"{config.tts_provider} said {TEST_LINE!r} in {seconds:.1f}s")


async def check_ears(config: BrainConfig) -> Finding:
    """The round trip: she says a line, and the transcriber hears it back."""
    if not config.stt_provider:
        return warned("no transcriber is configured",
                      "She cannot hear voice input. Set `stt_provider` if you "
                      "want to talk to her rather than type.")

    from src.modules.STT.factory import build_stt
    from src.modules.tts.factory import build_tts

    try:
        stt = build_stt(config)
        audio, rate = await build_tts(config).generate_audio(TEST_LINE)
        heard = await asyncio.to_thread(_transcribe, stt, audio, rate)
    except Exception as e:
        return failed(f"{config.stt_provider} could not transcribe ({e})",
                      "Check the STT key and model in config.json.")

    if not heard:
        return failed(f"{config.stt_provider} heard nothing at all",
                      "Check the STT key and model in config.json.")
    words = {w.strip(".,!?").lower() for w in heard.split()}
    if not words & set(TEST_LINE.split()):
        return warned(f"it heard {heard!r} instead of {TEST_LINE!r}",
                      "Not necessarily wrong — but a different STT model may "
                      "serve you better.")
    return passed(f"{config.stt_provider} heard {heard.strip()!r}")


async def check_memory(config: BrainConfig) -> Finding:
    """The database opens, and the embedding model is actually on disk."""
    from src.core.memory.store import MemoryStore

    cfg = config.skills.get("memory", {})
    try:
        store = MemoryStore(cfg.get("db_path", "data/bea.db"))
    except Exception as e:
        return failed(f"her memory will not open ({e})",
                      "Check that `skills.memory.db_path` is writable.")
    store.close()

    try:
        from src.core.memory.embedder import FastEmbedEmbedder
        embedder = FastEmbedEmbedder(cfg.get("embedding_model"),
                                     cfg.get("embedding_cache_dir"))
        await asyncio.to_thread(embedder.embed, ["a line to embed"])
    except Exception as e:
        return warned(f"the embedding model is not usable ({e})",
                      "She keeps her people and her hot facts; she loses recall "
                      "and lands every invented mood on `neutral`.")
    return passed("the database opens and the embedder answers")


async def check_stage(config: BrainConfig) -> Finding:
    """Whatever backend she is set to, the things it needs are there."""
    stage = config.stage or {}
    backend = stage.get("avatar_backend", "png")

    if backend == "png":
        missing = [f"{mood}/{state}"
                   for mood, slots in (config.avatar_map or {}).items()
                   for state, path in (slots or {}).items()
                   if path and not Path(path).is_file()]
        if missing:
            return failed(f"{len(missing)} avatar image(s) are not on disk: "
                          f"{', '.join(missing[:4])}",
                          "Fix the paths in `avatar_map`, or point `png_dir` at "
                          "the folder they are actually in.")
        return passed("every configured avatar image is on disk")

    if backend == "model":
        raw = stage.get("model_path") or ""
        if not raw:
            return failed("the 3D body has no model",
                          "make model — or set `stage.model_path` to your own .vrm.")
        if not Path(raw).is_file():
            return failed(f"{raw} is not on disk",
                          "make model — or correct `stage.model_path`.")
        clips = installed_clips(config)
        return passed(f"{Path(raw).name}, {len(clips)} behaviour(s) installed")

    if backend == "vtube_studio":
        host = stage.get("vts_host") or "127.0.0.1"
        port = int(stage.get("vts_port") or 8001)
        if not _reachable(host, port):
            return failed(f"nothing is listening on {host}:{port}",
                          "Open VTube Studio and turn on its plugin API "
                          "(Settings → the plug icon).")
        return passed(f"VTube Studio answers on {host}:{port}")

    return warned(f"unknown avatar backend {backend!r}",
                  "Set `stage.avatar_backend` to png, model or vtube_studio.")


async def check_obs(config: BrainConfig) -> Finding:
    """Only asked when a backend she is actually using needs it."""
    from src.setup.wizard import needs_obs

    stage = config.stage or {}
    if not needs_obs(stage.get("avatar_backend", "png"),
                     stage.get("caption_backend", "obs")):
        return passed("not needed by the backends she is set to")

    if not _reachable(config.obs_host, config.obs_port):
        return failed(f"nothing is listening on {config.obs_host}:{config.obs_port}",
                      "Open OBS, then Tools → WebSocket Server Settings → Enable.")
    return passed(f"OBS answers on {config.obs_host}:{config.obs_port}")


async def check_dashboard(config: BrainConfig) -> Finding:
    """The page is built, and something is not already sitting on her port."""
    stage = config.stage or {}
    needs_page = (stage.get("avatar_backend") == "model"
                  or stage.get("caption_backend") == "stage")

    if not DASHBOARD.is_file():
        if needs_page:
            return failed("the dashboard has never been built, and her stage needs it",
                          "make frontend")
        return warned("the dashboard has never been built",
                      "make frontend — the engine runs without it, the web "
                      "interface does not.")

    if _reachable("127.0.0.1", DEFAULT_PORT):
        return warned(f"something is already listening on {DEFAULT_PORT}",
                      "Either that is her, already running, or something else "
                      "has the port. `uv run bea --web --port <other>` moves her.")
    return passed(f"built, and port {DEFAULT_PORT} is free")


CHECKS: List[Tuple[str, Callable]] = [
    ("Python and uv", check_python),
    ("Config and secrets", check_config),
    ("API keys", check_keys),
    ("The mind", check_mind),
    ("The operating manual", check_manual),
    ("Audio output", check_speakers),
    ("Her voice", check_voice),
    ("Her ears", check_ears),
    ("Her memory", check_memory),
    ("Her body", check_stage),
    ("OBS", check_obs),
    ("The dashboard", check_dashboard),
]


# --- running them ------------------------------------------------------------


async def diagnose(config: BrainConfig, report=None) -> List[Tuple[str, Finding]]:
    """Runs the checks in order, stopping at the first blocking failure.

    `report` is called with each `(title, finding)` as it lands, so a terminal
    shows progress instead of nothing for the twenty seconds this takes. It is
    optional so the whole thing can be run and asserted on without one.
    """
    found: List[Tuple[str, Finding]] = []
    for title, check in CHECKS:
        try:
            finding = await check(config)
        except Exception as e:
            # a check that falls over is itself a finding, and never the end of
            # the run: the one after it may be the one that explains why
            finding = warned(f"this check could not run ({e})")
        found.append((title, finding))
        if report:
            report(title, finding)
        if finding.stops:
            break
    return found


def run_doctor(console=None) -> int:
    """The command. Returns a shell exit code: 0 when nothing is blocking."""
    import warnings

    from rich.console import Console

    from src.utils.logger import quieten

    # the findings are the output; the engine's own commentary is not
    quieten()
    warnings.filterwarnings("ignore")

    console = console or Console()
    config = BrainConfig()

    console.print()
    console.rule("[bold]Checking your setup[/bold]", align="left", style="dim")
    console.print()

    found = asyncio.run(diagnose(config, report=lambda t, f: _print(console, t, f)))
    return _verdict(console, found)


def _print(console, title: str, finding: Finding) -> None:
    mark = "[green]✓[/green]" if finding.ok else (
        "[red]✗[/red]" if finding.blocking else "[yellow]![/yellow]")
    console.print(f"  {mark} [bold]{title}[/bold]"
                  + (f"  [dim]{finding.detail}[/dim]" if finding.detail else ""))
    if not finding.ok and finding.fix:
        for line in finding.fix.splitlines():
            console.print(f"      [cyan]{line}[/cyan]")


def _verdict(console, found: List[Tuple[str, Finding]]) -> int:
    console.print()
    blocking = [title for title, finding in found if finding.stops]
    warnings = [title for title, finding in found
                if not finding.ok and not finding.blocking]

    if blocking:
        skipped = len(CHECKS) - len(found)
        console.print(f"  [red]{blocking[0]} is in the way.[/red] Fix it and run "
                      f"this again"
                      + (f" — {skipped} check(s) below it never ran." if skipped else "."))
        return 1
    if warnings:
        console.print(f"  [yellow]She will run.[/yellow] {len(warnings)} thing(s) "
                      f"will not work as well as they could: "
                      f"{', '.join(warnings).lower()}.")
        return 0
    console.print("  [green]Everything checks out.[/green]")
    return 0


# --- small helpers -----------------------------------------------------------


def _env_var(provider: str) -> str:
    return {"openrouter": "OPENROUTER_API_KEY", "openai": "OPENAI_API_KEY",
            "groq": "GROQ_API_KEY"}.get(provider, f"{provider.upper()}_API_KEY")


def _key_for(config: BrainConfig, provider: str) -> Optional[str]:
    return getattr(config, f"{provider}_key", None) or os.getenv(_env_var(provider))


def _model_of(client) -> str:
    name = getattr(client, "model_name", "")
    if name:
        return name
    pool = getattr(client, "clients", None)
    return getattr(pool[0], "model_name", "the mind") if pool else "the mind"


def _voice_fix(config: BrainConfig) -> str:
    if config.tts_provider == "kokoro":
        return "make kokoro — the ONNX model and voices file are downloaded, not shipped."
    if config.tts_provider == "orpheus":
        return "Check ORPHEUS_API_KEY and `orpheus_endpoint`; the endpoint may be cold."
    return "EdgeTTS needs internet and no key. If you are online, the service may be down."


def _reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def _transcribe(stt, audio, rate) -> str:
    """Writes the synthesised line to a temp wav and hands it to the transcriber."""
    import tempfile

    import soundfile as sf

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        path = handle.name
    try:
        sf.write(path, audio, rate)
        return stt.transcribe(path) or ""
    finally:
        Path(path).unlink(missing_ok=True)


__all__ = ["CHECKS", "Finding", "diagnose", "run_doctor", "failed", "passed", "warned"]
