import argparse
import asyncio
import dataclasses
import faulthandler
import os

from dotenv import load_dotenv

from src.core.agent.registry import ModelPoolError, ModelRegistry
from src.core.brain import AIVtuberBrain
from src.core.config import BrainConfig
from src.modules.obs.obs_websocket import OBSController
from src.utils.logger import get_logger

logger = get_logger("bea")


def bootstrap() -> None:
    """The environment, before anything reads it. Idempotent.

    Every one of these used to sit between the imports, which made the file's
    behaviour depend on its import order — and made tidying the imports a
    silent regression rather than a mistake anyone would catch.
    """
    # the local embedding model runs in a subprocess; silence the noisy fork warning
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    # segfaults and access violations get a traceback instead of a silent exit
    faulthandler.enable()
    load_dotenv()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="ProjectBEA - AI Persona Engine")

    parser.add_argument("--setup", action="store_true",
                        help="Interactive first-run setup: writes .env and config.json")
    parser.add_argument("--doctor", action="store_true",
                        help="Check this machine: keys, voice, ears, body, and what to fix")
    parser.add_argument("--update", action="store_true",
                        help="Pull the new version without overwriting your prompts or your config")
    parser.add_argument("--no-rebuild", action="store_true",
                        help="With --update: skip `uv sync` and the dashboard build")
    parser.add_argument("--install-node", action="store_true",
                        help="Install the dashboard and the discord bot (needs Node 20+)")
    parser.add_argument("--web", action="store_true", help="Start Web Interface (FastAPI + React)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address for the web interface (default: loopback only)")
    parser.add_argument("--port", type=int, default=8000, help="Port for the web interface")

    # core config
    parser.add_argument("--system-file", dest="system_prompt_path", metavar="SYSTEM_FILE", default=None,
                        help="Path to system prompt file")
    parser.add_argument("--png-dir", default=None, help="Directory for avatar PNGs")

    # llm selection
    parser.add_argument("--llm-provider", choices=["openrouter", "openai", "groq"], default=None, help="LLM Provider to use")

    # openrouter
    parser.add_argument("--openrouter-key", default=None, help="OpenRouter API Key")
    parser.add_argument("--openrouter-model", default=None, help="OpenRouter Model (e.g. openai/gpt-4o-mini)")

    # openai
    parser.add_argument("--openai-key", default=None, help="OpenAI API Key")
    parser.add_argument("--openai-model", default=None, help="OpenAI Model")

    # groq
    parser.add_argument("--groq-key", default=None, help="Groq API Key")
    parser.add_argument("--groq-model", default=None, help="Groq Model")

    # stt
    parser.add_argument("--stt-provider", choices=["groq", "openrouter"], default=None, help="STT Provider")
    parser.add_argument("--stt-model", default=None, help="STT Model")

    # obs
    parser.add_argument("--obs-host", default=None, help="OBS WebSocket host")
    parser.add_argument("--obs-port", type=int, default=None, help="OBS WebSocket port")
    parser.add_argument("--obs-password", default=None, help="OBS WebSocket password")
    parser.add_argument("--obs-avatar-source", default=None, required=False, help="OBS Source Name for Avatar")
    parser.add_argument("--obs-source-type", choices=["image", "media"], default=None, help="OBS Source Type")
    parser.add_argument("--obs-text-source", default=None, help="OBS Source Name for Text Bubble")

    # tts
    parser.add_argument("--tts-provider", choices=["edge", "coqui", "orpheus", "kokoro"], default=None, help="TTS Provider")
    parser.add_argument("--tts-voice", default=None, help="EdgeTTS Voice")
    # orpheus
    parser.add_argument("--orpheus-key", default=None, help="Orpheus API Key")
    parser.add_argument("--orpheus-endpoint", default=None, help="Orpheus Endpoint")
    parser.add_argument("--orpheus-voice", default=None, help="Orpheus Voice")

    # kokoro
    parser.add_argument("--kokoro-file", dest="kokoro_model", metavar="KOKORO_FILE", default=None,
                        help="Kokoro Model File")
    parser.add_argument("--kokoro-voices", dest="kokoro_voices_file", metavar="KOKORO_VOICES", default=None,
                        help="Kokoro Voices File")

    parser.add_argument("--device-id", dest="audio_device_id", metavar="DEVICE_ID", type=int, default=None,
                        help="Audio Output Device ID")

    # text/typing
    parser.add_argument("--typing-delay", type=float, default=None, help="Typing animation delay")

    return parser.parse_args(argv)


def apply_cli_overrides(config: BrainConfig, args) -> None:
    """Only overrides where the flag was passed: CLI arg > config.json > default.

    A flag overrides the config field its `dest` names — which is why the four
    flags whose spelling diverges from their field carry an explicit `dest`.
    The pairing used to be a hand-written table of every flag, so renaming a
    field left the table still setting the old name on an object without it.
    """
    fields = {f.name for f in dataclasses.fields(config)}

    for name, value in sorted(vars(args).items()):
        # `is not None` and not truthiness: `--device-id 0` is the first audio
        # device and `--obs-password ''` is a password being cleared
        if value is None or name not in fields:
            continue
        setattr(config, name, value)
        logger.info(f"CLI override: {name} = {value}")


async def main(args=None):
    args = args or parse_args()

    # 1. config — priority: CLI arg > config.json > dataclass default
    #
    # BrainConfig() loads config.json in __post_init__ (via load_from_file),
    # giving us: config.json values on top of dataclass defaults.
    # We then apply any explicitly-provided CLI args on top, so CLI always wins.
    config = BrainConfig()
    apply_cli_overrides(config, args)

    # 2. modules

    # stt
    from src.modules.STT.factory import build_stt
    stt = build_stt(config)

    # llm: one pool per role, so a provider outage does not silence her and the
    # dreamer never competes with the mind
    registry = ModelRegistry(config, stt=stt)
    try:
        registry.get("mind")
    except ModelPoolError as e:
        logger.error(str(e))
        return

    # tts
    from src.modules.tts.factory import build_tts
    tts = build_tts(config)

    # obs
    obs = OBSController(
        host=config.obs_host,
        port=config.obs_port,
        password=config.obs_password,
        source_name=config.obs_avatar_source
    )

    # 3. Brain
    brain = AIVtuberBrain(config, registry, tts, stt, obs)

    try:
        brain.initialize()
        await brain.start_skills()

        if args.web:
            from src.web.server import run_server
            logger.info(f"Starting Web Interface at http://{args.host}:{args.port}")
            await run_server(brain, host=args.host, port=args.port)
        else:
            await brain.run_loop()

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        # save on ANY exit (clean stop, crash, ctrl+c): save_all_pending is
        # idempotent (guards on entry_exists), so a double call is harmless
        if brain.memory_skill and brain.memory_skill.enabled:
            logger.info("Saving pending memories...")
            try:
                await brain.memory_skill.save_all_pending()
            except Exception as e:
                logger.error(f"Failed to save pending memories on shutdown: {e}")
        await brain.stop_skills()
        brain.shutdown()


def run():
    # before parse_args: --doctor and --setup build a BrainConfig, whose secrets
    # default off the environment `.env` carries
    bootstrap()
    args = parse_args()
    # the wizard runs before anything heavy is imported: it exists precisely
    # for the case where config.json and .env do not exist yet
    if args.setup:
        from src.setup import run_setup
        raise SystemExit(run_setup())
    # same reason: it exists for the case where something below is broken
    if args.doctor:
        from src.setup.doctor import run_doctor
        # a check ought to test what it was asked to test: `--tts-provider
        # kokoro` on the command line must not diagnose the default instead
        config = BrainConfig()
        apply_cli_overrides(config, args)
        raise SystemExit(run_doctor(config=config))
    # no engine needed to run npm, and this is what people without `make` reach
    # for when the dashboard or the discord bot was never installed
    if args.install_node:
        from src.setup.node import install_all
        raise SystemExit(install_all())
    # and again: an update exists to repair the tree everything below is
    # imported from, so it must not import any of it
    if args.update:
        from src.core.update.console import run_update
        raise SystemExit(run_update(rebuild=not args.no_rebuild))
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
