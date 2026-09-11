import argparse
import asyncio
import faulthandler
import os

# the local embedding model runs in a subprocess; silence the noisy fork warning
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

from dotenv import load_dotenv

# enable fault handler to catch segfaults/access violations
faulthandler.enable()

# load env
load_dotenv()

from src.core.agent.registry import ModelPoolError, ModelRegistry
from src.core.brain import AIVtuberBrain
from src.core.config import BrainConfig
from src.modules.obs.obs_websocket import OBSController
from src.utils.logger import get_logger

logger = get_logger("bea")


def parse_args():
    parser = argparse.ArgumentParser(description="ProjectBEA - AI Persona Engine")

    parser.add_argument("--setup", action="store_true",
                        help="Interactive first-run setup: writes .env and config.json")
    parser.add_argument("--doctor", action="store_true",
                        help="Check this machine: keys, voice, ears, body, and what to fix")
    parser.add_argument("--update", action="store_true",
                        help="Pull the new version without overwriting your prompts or your config")
    parser.add_argument("--no-rebuild", action="store_true",
                        help="With --update: skip `uv sync` and the dashboard build")
    parser.add_argument("--web", action="store_true", help="Start Web Interface (FastAPI + React)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="Bind address for the web interface (default: loopback only)")
    parser.add_argument("--port", type=int, default=8000, help="Port for the web interface")

    # core config
    parser.add_argument("--system-file", default=None, help="Path to system prompt file")
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
    parser.add_argument("--kokoro-file", default=None, help="Kokoro Model File")
    parser.add_argument("--kokoro-voices", default=None, help="Kokoro Voices File")

    parser.add_argument("--device-id", type=int, default=None, help="Audio Output Device ID")

    # text/typing
    parser.add_argument("--typing-delay", type=float, default=None, help="Typing animation delay")

    return parser.parse_args()


def apply_cli_overrides(config: BrainConfig, args) -> None:
    """Only overrides where the flag was passed: CLI arg > config.json > default."""
    cli_overrides = {
        "system_prompt_path": args.system_file,
        "png_dir":            args.png_dir,
        "llm_provider":       args.llm_provider,
        "openrouter_key":     args.openrouter_key,
        "openrouter_model":   args.openrouter_model,
        "openai_key":         args.openai_key,
        "openai_model":       args.openai_model,
        "groq_key":           args.groq_key,
        "groq_model":         args.groq_model,
        "stt_provider":       args.stt_provider,
        "stt_model":          args.stt_model,
        "obs_host":           args.obs_host,
        "obs_port":           args.obs_port,
        "obs_password":       args.obs_password,
        "obs_avatar_source":  args.obs_avatar_source,
        "obs_source_type":    args.obs_source_type,
        "obs_text_source":    args.obs_text_source,
        "tts_provider":       args.tts_provider,
        "tts_voice":          args.tts_voice,
        "orpheus_key":        args.orpheus_key,
        "orpheus_endpoint":   args.orpheus_endpoint,
        "orpheus_voice":      args.orpheus_voice,
        "kokoro_model":       args.kokoro_file,
        "kokoro_voices_file": args.kokoro_voices,
        "audio_device_id":    args.device_id,
        "typing_delay":       args.typing_delay,
    }
    for field_name, value in cli_overrides.items():
        if value is not None:
            setattr(config, field_name, value)
            logger.info(f"CLI override: {field_name} = {value}")


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
    # and again: an update exists to repair the tree everything below is
    # imported from, so it must not import any of it
    if args.update:
        from src.core.update.console import run_update
        raise SystemExit(run_update(rebuild=not args.no_rebuild))
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
