import copy
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("bea.config")

CONFIG_FILE = "config.json"

# secrets nested inside the `skills` dict: (skill key, field). Top-level secrets
# live in BrainConfig.SECRET_KEYS.
SECRET_SKILL_FIELDS: List[Tuple[str, str]] = [
    ("discord", "token"),
    ("telegram", "token"),
    ("twitch", "oauth_token"),
]

MASK = "********"

@dataclass
class BrainConfig:
    language: str = "en" # default language
    soul_path: str = "data/prompts/soul.md"  # shared persona, prepended to every context
    system_prompt_path: str = "data/prompts/chat.md"  # deprecated: fallback when operating manual is absent
    operating_prompt_path: str = "data/prompts/operating.md"  # unified operating manual (speak tool, moods, perception)
    llm_provider: str = "openrouter" # openrouter, openai, groq

    # openrouter (routes to virtually any model via one openai-compatible endpoint)
    openrouter_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    openrouter_model: str = "deepseek/deepseek-v4-flash"

    # openai
    openai_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = "gpt-5"

    # groq
    groq_key: Optional[str] = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    groq_model: str = "openai/gpt-oss-20b"

    obs_text_source: Optional[str] = "AIText"
    obs_avatar_source: str = "BeaPNG"
    obs_source_type: str = "image" # image or media
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    audio_device_id: int = 0

    tts_provider: str = "edge" # edge or kokoro or orpheus
    tts_voice: str = "en-US-AvaNeural"
    tts_pitch: str = "+5Hz"
    tts_rate: str = "+10%"
    tts_volume: str = "+33%"



    # orpheus
    orpheus_key: Optional[str] = field(default_factory=lambda: os.getenv("ORPHEUS_API_KEY"))
    orpheus_endpoint: Optional[str] = field(default_factory=lambda: os.getenv("ORPHEUS_ENDPOINT", ""))
    orpheus_voice: str = "zoe"

    # kokoro tts (onnx)
    kokoro_model: str = "kokoro-v0_19.onnx"
    kokoro_voices_file: str = "voices.bin"
    kokoro_voice: str = "af_bella"
    kokoro_speed: float = 1.0
    kokoro_lang: str = "en-us"



    # avatar
    avatar_map: Dict[str, Dict[str, str]] = field(default_factory=lambda: {
        "normal": {"idle": "", "talking": ""},
        "angry": {"idle": "", "talking": ""},
        "bored": {"idle": "", "talking": ""},
        "cry": {"idle": "", "talking": ""},
        "ew": {"idle": "", "talking": ""},
        "love": {"idle": "", "talking": ""},
        "shock": {"idle": "", "talking": ""},
    })

    png_dir: str = "data/pngs"

    # typing animation
    text_line_width: int = 40
    text_lines: Optional[int] = 4
    text_font_size: int = 75
    text_min_font_size: int = 55
    text_font_step: int = 2
    typing_delay: float = 0.03
    text_min_duration: float = 2.0

    # skills
    skills: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        "monologue": {
            "enabled": False,
            "interval_seconds": 30,
            "chunk_pause_seconds": 4.0,
            "prompt_path": "data/prompts/monologue.md"
        },
        # everything Bea remembers now lives in one sqlite file; the embedding
        # model is multilingual because her people write in italian
        "memory": {
            "enabled": True,
            "db_path": "data/bea.db",
            "embedding_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "embedding_cache_dir": "data/embeddings_cache",
            "min_similarity": 0.35
        },
        "social_memory": {
            "enabled": True
        },
        "dream": {
            "enabled": True
        },
        "minecraft": {
            "enabled": False,
            "server_url": "ws://localhost:8080",
            "auto_chat_thoughts": False,
            "auto_speak_thoughts": False,
            "system_prompt_path": "data/prompts/minecraft.md"
        },
        # the oauth token is deliberately absent: read from TWITCH_OAUTH_TOKEN.
        # reading chat needs no credentials at all (anonymous irc).
        "twitch": {
            "enabled": False,
            "channel": "",
            "nick": ""
        },
        # the shared secret is read from DONATION_SECRET
        "donations": {
            "enabled": False
        },
        # the token is deliberately absent: it is read from TELEGRAM_TOKEN
        "telegram": {
            "enabled": False,
            "owner_id": "",
            "allowed_chats": []   # empty = every chat she is added to
        },
        # the discord token is deliberately absent: it is read from DISCORD_TOKEN
        "discord": {
            "enabled": False,
            "target_channel": "",
            "api_port": 3030,
            "brain_api_url": "http://127.0.0.1:8000",
            "admin_id": "",
            "interrupt_threshold_ms": 3000
        }
    })

    # unified consciousness loop (single always-on brain)
    consciousness: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "idle_after": 240.0,       # seconds of silence before an IDLE perception (monologue = last resort)
        "window": 0.3,             # perception aggregation window
        "burst_steps": 6,          # max reasoning steps per perception batch
        "history_limit": 30,       # rolling context size
        "correlation_timeout": 90.0,  # how long an HTTP caller waits for Bea to respond
        # scoped conversation turns (written channels, beside the live loop)
        "conversation_history": 16,   # past messages of that channel in the turn
        "conversation_steps": 3,      # a reply is not an expedition
        "max_coalesced_runs": 3,      # cap on re-runs when messages keep arriving
    })

    # model pools per role, as "provider:model" specs. Round-robin inside a pool
    # spreads rate limits; the rest of the pool is the fallback when one is down.
    # Leave a role empty to fall back to llm_provider + <provider>_model.
    # NOTE: every model in "mind" must support tool calling — Bea only speaks
    # through tools, so one that cannot would simply never say anything.
    models: Dict[str, Any] = field(default_factory=lambda: {
        "mind": [],
        "background": [],
    })

    # attention gate: what wakes the mind vs what she merely notices
    attention: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "cooldown_seconds": 20,        # she just spoke: let the room breathe
        "interject_threshold": 0.45,   # score needed to speak up unprompted
        "quiet_hours": [3, 9],         # never interjects here (being addressed still does)
        "trigger_words": ["bea", "beatrice"],
        "hot_names": [],               # names that pull her into a conversation
        "self_ids": [],                # her own platform ids, to spot replies to her
        "digest_max_lines": 8,
    })

    # STT
    stt_provider: str = "openrouter"
    stt_model: str = "whisper-large-v3-turbo"

    def __post_init__(self):
        self.load_from_file()

    # secret keys
    SECRET_KEYS = ["openrouter_key", "openai_key", "groq_key", "orpheus_key", "orpheus_endpoint"]

    def load_from_file(self):
        """Loads configuration from config.json if it exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # migration: image to avatar source
                if "obs_image_source" in data and "obs_avatar_source" not in data:
                    data["obs_avatar_source"] = data.pop("obs_image_source")

                # update fields
                for key, value in data.items():
                    if hasattr(self, key):
                        # security: env vars always take priority over config.json for secret fields.
                        # If the env var is already set (non-empty), skip the config.json value entirely.
                        # If the env var is not set, allow a non-empty config.json value to fill it.
                        if key in self.SECRET_KEYS:
                            current_val = getattr(self, key, None)
                            if current_val:
                                continue  # env var is set → it always wins
                            if value is None or value == "":
                                continue  # env var not set and config.json empty → nothing to apply
                            # env var not set but config.json has a value → use it

                        if key == "skills":
                            current_skills = self.skills
                            for skill_name, skill_val in value.items():
                                if skill_name in current_skills:
                                    current_skills[skill_name].update(skill_val)
                                else:
                                    current_skills[skill_name] = skill_val
                        else:
                            setattr(self, key, value)

            except Exception as e:
                logger.error(f"Error loading config.json: {e}")

    def save_to_file(self):
        """Saves current configuration to config.json, EXCLUDING secrets."""
        data = asdict(self)

        # security: strip secrets
        for secret in self.SECRET_KEYS:
            data.pop(secret, None)

        skills = data.get("skills", {})
        for skill_key, field_name in SECRET_SKILL_FIELDS:
            if skills.get(skill_key, {}).pop(field_name, None):
                logger.warning(
                    f"Not persisting skills.{skill_key}.{field_name} to {CONFIG_FILE}. "
                    f"Set it via the environment instead."
                )

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Configuration saved to {CONFIG_FILE} (secrets excluded)")
        except Exception as e:
            logger.error(f"Error saving config.json: {e}")

    def public_dict(self) -> Dict[str, Any]:
        """The config as the UI may see it: every secret removed or masked.

        `GET /config` is unauthenticated and reachable from any page the browser
        has open, so it must never carry a usable key. Masked (rather than
        removed) nested secrets so the UI can still show 'a token is set'.
        """
        data = copy.deepcopy(asdict(self))

        for secret in self.SECRET_KEYS:
            data.pop(secret, None)

        skills = data.get("skills", {})
        for skill_key, field_name in SECRET_SKILL_FIELDS:
            block = skills.get(skill_key)
            if isinstance(block, dict) and field_name in block:
                block[field_name] = MASK if block[field_name] else ""

        return data
