import json
import os
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from src.utils.logger import get_logger

logger = get_logger("bea.config")

CONFIG_FILE = "config.json"

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
        "memory": {
            "enabled": True,
            "chroma_path": "data/memory_db",
            "openai_model": "gpt-4o-mini",
            "embedding_model": "local"
        },
        "social_memory": {
            "enabled": True,
            "roster_path": "data/memory/roster.json",
            "people_path": "data/memory/people.json"
        },
        "dream": {
            "enabled": True,
            "self_path": "data/memory/self.md",
            "profile_path": "data/memory/self_profile.json",
            "recent_path": "data/memory/recent.json"
        },
        "minecraft": {
            "enabled": False,
            "server_url": "ws://localhost:8080",
            "auto_chat_thoughts": False,
            "auto_speak_thoughts": False,
            "system_prompt_path": "data/prompts/minecraft.md"
        },
        "discord": {
            "enabled": False,
            "token": "",
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
            if secret in data:
                del data[secret]
        
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
            logger.info(f"Configuration saved to {CONFIG_FILE} (secrets excluded)")
        except Exception as e:
            logger.error(f"Error saving config.json: {e}")
