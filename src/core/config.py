import copy
import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.mind.moods import default_avatar_map, rename_legacy
from src.core.persona import DEFAULT_NAME, DEFAULT_PRONOUNS
from src.utils.files import atomic_write_text
from src.utils.logger import get_logger

logger = get_logger("bea.config")

CONFIG_FILE = "config.json"

MASK = "********"

# every secret in the config, and the environment variable the engine reads it
# from. `save_to_file` strips all of them on the way to config.json, so this is
# the map that says where one typed into the dashboard is actually written.
# Keyed the way `GET /secrets` reports them: a bare field, or `skill.field`.
SECRET_ENV_VARS: Dict[str, str] = {
    "openrouter_key": "OPENROUTER_API_KEY",
    "openai_key": "OPENAI_API_KEY",
    "groq_key": "GROQ_API_KEY",
    "google_key": "GOOGLE_API_KEY",
    "claude_key": "ANTHROPIC_API_KEY",
    "openai_compat_key": "OPENAI_COMPAT_API_KEY",
    "anthropic_compat_key": "ANTHROPIC_COMPAT_API_KEY",
    "local_key": "LOCAL_API_KEY",
    "orpheus_key": "ORPHEUS_API_KEY",
    "orpheus_endpoint": "ORPHEUS_ENDPOINT",
    "discord.token": "DISCORD_TOKEN",
    "telegram.token": "TELEGRAM_TOKEN",
    "twitch.oauth_token": "TWITCH_OAUTH_TOKEN",
    "web.brave_api_key": "BRAVE_API_KEY",
    "web.tavily_api_key": "TAVILY_API_KEY",
}

# derived, so a new secret is declared once: the ones nested inside the
# `skills` dict as (skill key, field). Top-level ones are BrainConfig.SECRET_KEYS
SECRET_SKILL_FIELDS: List[Tuple[str, str]] = [
    (skill, field_name) for skill, _, field_name in
    (key.partition(".") for key in SECRET_ENV_VARS if "." in key)
]


def deep_merge(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    """`incoming` over `base`, recursing into dicts. Lists replace wholesale.

    Every dict-valued setting is a block of named knobs, so a config.json
    written before a knob existed must not delete it. A list, on the other
    hand, is one value: merging trigger_words would make them impossible to
    shorten.
    """
    merged = dict(base)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = deep_merge(current, value)
        else:
            merged[key] = value
    return merged

# What the shape of config.json is understood to mean, so that a default which
# changed can be told from a value somebody chose. Bumped only when a *meaning*
# changes; a new field needs nothing, because an absent field already has one.
#
#   1  `language` became a policy rather than a pin, and its default became
#      `auto`. Before it, every install carried `"language": "en"` whether or
#      not anybody had ever wanted english.
CONFIG_VERSION = 1


@dataclass
class BrainConfig:
    # which meaning of this file to read it with. See CONFIG_VERSION.
    config_version: int = CONFIG_VERSION

    # what she hears and, when she speaks first, what she reaches for. `auto`
    # lets the transcriber detect and leaves her mirroring whoever is talking:
    # measured on real audio, detection matched or beat a pin every time, and a
    # wrong pin turns Italian speech into invented Japanese. See core/language.py
    language: str = "auto"
    soul_path: str = "data/prompts/soul.md"  # shared persona, prepended to every context
    system_prompt_path: str = "data/prompts/chat.md"  # deprecated: fallback when operating manual is absent
    operating_prompt_path: str = "data/prompts/operating.md"  # unified operating manual (speak tool, moods, perception)
    llm_provider: str = "openrouter" # openrouter, openai, groq, google, claude, openai_compat, anthropic_compat, local

    # openrouter (routes to virtually any model via one openai-compatible endpoint)
    openrouter_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENROUTER_API_KEY"))
    openrouter_model: str = "deepseek/deepseek-v4-flash"

    # openai
    openai_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    openai_model: str = "gpt-5"

    # groq
    groq_key: Optional[str] = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    groq_model: str = "openai/gpt-oss-20b"

    # google ai studio (gemini through its openai-compatible endpoint)
    google_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    google_model: str = "gemini-3.8-flash"

    # claude (anthropic messages api)
    claude_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    claude_model: str = "claude-sonnet-5"

    # any self-hosted openai-compatible server. chat completions is the
    # universal default; flip openai_compat_api when the endpoint speaks
    # the responses protocol instead
    openai_compat_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_COMPAT_API_KEY"))
    openai_compat_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_COMPAT_BASE_URL", ""))
    openai_compat_model: str = ""
    openai_compat_api: str = "chat" # chat or responses

    # any anthropic-compatible endpoint
    anthropic_compat_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_COMPAT_API_KEY"))
    anthropic_compat_base_url: str = field(default_factory=lambda: os.getenv("ANTHROPIC_COMPAT_BASE_URL", ""))
    anthropic_compat_model: str = ""

    # the models on this machine (ollama, lm studio): no key, no account,
    # nothing leaves the room. point the url at lm studio to switch runners
    local_key: Optional[str] = field(default_factory=lambda: os.getenv("LOCAL_API_KEY"))
    local_base_url: str = field(default_factory=lambda: os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1"))
    local_model: str = "qwen3:8b"

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
    kokoro_voices_file: str = "voices.json"
    kokoro_voice: str = "af_bella"
    kokoro_speed: float = 1.0
    kokoro_lang: str = "en-us"

    # avatar: one slot per mood, derived so a new mood is never avatar-less.
    # Used by the `png` backend; the others have their own maps under `stage`.
    avatar_map: Dict[str, Dict[str, str]] = field(default_factory=default_avatar_map)

    png_dir: str = "data/pngs"

    # how she is put on screen. Two independent choices, because "PNG avatar with
    # the nicer browser caption" and "3D body with the bubble still in OBS" are
    # both setups people actually want.
    stage: Dict[str, Any] = field(default_factory=lambda: {
        "avatar_backend": "png",       # png | model | vtube_studio
        "caption_backend": "obs",      # obs | stage | off
        "lipsync_fps": 30,             # how often the mouth is told what to do

        # the `model` backend
        "model_path": "",              # the .vrm you bring; never shipped with the repo
        "clips_dir": "data/clips",     # .vrma behaviours, which are portable and are
        "shot": "bust",                # bust | half | full, framed off the head bone
        "mood_clips": {},              # mood -> clip name, all optional
        "background": "",              # a colour behind her, or empty for transparent
        "max_fps": 0,                  # cap the browser source; 0 follows the display

        # the `vtube_studio` backend: nothing is bundled, it talks to yours
        "vts_host": "127.0.0.1",
        "vts_port": 8001,
        "vts_expressions": {},         # mood -> expression file in the user's model
        "vts_clips": {},               # clip name -> hotkey id in the user's model
        "vts_mouth_param": "MouthOpen",
        "vts_mouth_form_param": "",    # a mouth that also changes shape, if yours has one
    })

    # typing animation
    text_line_width: int = 40
    text_lines: Optional[int] = 4
    text_font_size: int = 75
    text_min_font_size: int = 55
    text_font_step: int = 2
    typing_delay: float = 0.03
    text_min_duration: float = 2.0

    # staying current. `check` is the only thing here that reaches the network,
    # and it only ever talks to the remote this copy was cloned from; `apply`
    # is a button that runs `git pull` and a build, so it is separately
    # revocable for anyone who would rather update from a terminal.
    updates: Dict[str, Any] = field(default_factory=lambda: {
        "check": True,
        "allow_web_apply": True,
    })

    # who she is called. The prose lives in soul.md; this is the structured part
    # every other path needs — the gate's trigger words, the prompt placeholders,
    # the name her own messages are filed under, the dashboard chrome.
    persona: Dict[str, Any] = field(default_factory=lambda: {
        "name": DEFAULT_NAME,
        "pronouns": DEFAULT_PRONOUNS,
    })

    # skills
    skills: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        # the idle timer itself is consciousness.idle_after, not a key here
        "monologue": {
            "enabled": False,
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
            "enabled": True,
            "hour": 4          # she consolidates at night, without being asked
        },
        "minecraft": {
            "enabled": False,
            "server_url": "ws://127.0.0.1:8080",
            "idle_nudge_seconds": 90,   # 0 = she only ever reacts, never starts
            "commentary_seconds": 20,   # 0 = she plays in silence between milestones
            "system_prompt_path": "data/prompts/minecraft.md",
            "body_prompt_path": "data/prompts/minecraft_body.md"
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
        # off by default: pages are written by strangers. The search keys are
        # absent on purpose, read from BRAVE_API_KEY and TAVILY_API_KEY
        "web": {
            "enabled": False,
            "search_provider": "auto",   # keyed providers first, keyless always last
            "searxng_url": "",
            "safesearch": "moderate",
            "max_results": 5,
            "max_chars": 6000,
            "long_pages": "passages",   # "model" has the background model read them
            "wait_seconds": 3.0         # past this a lookup finishes in the background
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
            "api_port": 3030,
            "brain_api_url": "http://127.0.0.1:8000",
            "admin_id": "",
            "duck_threshold_ms": 400,
            "interrupt_threshold_ms": 4000,
            # the reflex: when she may open her mouth without being asked
            "fill_silences": True,
            "silence_seconds": 6.0,          # quiet for this long and the door opens
            "silence_jitter_seconds": 2.0,   # a fixed threshold sounds like a timer
            "silence_min_gap_seconds": 25.0,
            "unprompted_per_minute": 1       # the number that sets her character
        }
    })

    # unified consciousness loop (single always-on brain)
    consciousness: Dict[str, Any] = field(default_factory=lambda: {
        "idle_after": 240.0,       # seconds of silence before an IDLE perception (monologue = last resort)
        # the batch closes when the senses go quiet for this long, not this
        # long after the first thing arrived
        "window": 0.3,             # quiet gap for a live sense (voice, game)
        "text_window": 1.2,        # quiet gap for written text: a person is still typing
        "max_window": 8.0,         # ceiling on one batch, so a busy chat cannot hold the turn
        "burst_steps": 6,          # max reasoning steps per perception batch
        "correlation_timeout": 90.0,  # how long an HTTP caller waits for Bea to respond
        # ongoing present: what counts as "happening right now" across a handoff
        "hot_seconds": 1800,          # max age of an ongoing present message
        # the one sliding window. The ceiling is the only number anyone needs:
        # the trigger, the resting size and the ongoing present follow it, so
        # raising it raises how much she actually keeps rather than just how
        # much the emergency valve tolerates. 0 means "follow the ceiling";
        # pin one to take it out of the owner's hands and into your own.
        "context_max_tokens": 150_000,
        "handoff_trigger_tokens": 0,
        "handoff_target_tokens": 0,
        "hot_tokens": 0,
        "context_handoff": True,      # off: the window only grows until the ceiling trims it
        "window_persist_after_turn": True,  # off: the window only reaches disk on shutdown
        "dynamic_context_timeout": 5.0,     # seconds a turn waits for recall before answering without it
        # one jsonl a day of every turn she takes: the prompt in force, what she
        # was shown, what she did and what it cost. Nothing leaves the machine.
        "turn_log": True,
        "turn_log_dir": "data/turns",
        "turn_log_days": 14,          # 0 keeps them forever
    })

    # "provider:model" pools per role: round-robin spreads rate limits, the rest
    # of the pool is the fallback. Empty falls back to llm_provider.
    # every model in "mind" must support tool calling, or she never speaks
    # "reasoning" is a latency setting, not a quality one: she answers in a
    # voice call, and a thinking trace before the first token loses the moment
    models: Dict[str, Any] = field(default_factory=lambda: {
        "mind": [],
        "background": [],
        "reasoning": "off",   # off | low | medium | high | auto
    })

    # a day, not an event loop: when she starts something on her own, and when
    # she consolidates what happened
    rhythm: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "tick_seconds": 900,             # how often the spontaneous check runs
        "spontaneous_enabled": True,
        "spontaneous_probability": 0.15, # even when eligible, usually she doesn't
        "spontaneous_min_silence": 3600, # she spoke recently: more is noise, not presence
        "spontaneous_min_activity": 3,   # a dead room means talking to nobody
    })

    # attention gate: what wakes the mind vs what she merely notices
    attention: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "cooldown_seconds": 20,        # she just spoke: let the room breathe
        "voice_cooldown_seconds": 5,   # in a call 20s is not restraint, it is absence
        "quiet_hours": [3, 9],         # never interjects here (being addressed still does)
        "trigger_words": [],           # empty = worked out from persona.name
        "hot_names": [],               # names that pull her into a conversation
        "self_ids": [],                # her own platform ids, to spot replies to her
        "followup_enabled": True,
        "followup_window_seconds": 180,
        "followup_max_turns": 3,
        "followup_max_interposed": 3,
        "followup_active_bonus": 5,
        "followup_lookback": 30,
    })

    # how she feels, and how long it lasts. The mood colours her voice and her
    # prompt; how she *acts* on it is the soul's business, not this block's.
    affect: Dict[str, Any] = field(default_factory=lambda: {
        "enabled": True,
        "half_life_minutes": 25,       # long enough to survive a few exchanges
        "person_half_life_hours": 60,  # a rancour outlives a mood
        "memory_ttl_hours": 6,         # how long she remembers what caused it
    })

    # her clock. Empty follows the machine, which is fine on a laptop and wrong
    # in a UTC container where the quiet hours would silently shift
    timezone: str = ""

    # STT
    stt_provider: str = "openrouter"
    stt_model: str = "whisper-large-v3-turbo"

    # local whisper. Only read when stt_provider is "faster_whisper"; the model
    # id comes from stt_model like everywhere else, hosted spellings included
    faster_whisper_device: str = "auto"       # auto | cpu | cuda
    faster_whisper_compute_type: str = "auto" # auto picks int8 on cpu, float16 on cuda
    faster_whisper_download_root: str = "data/models/whisper"
    faster_whisper_vad: bool = True           # drops silence, which whisper otherwise invents words for

    def __post_init__(self):
        self.load_from_file()

    # the top-level secrets, derived from the one map
    SECRET_KEYS = [key for key in SECRET_ENV_VARS if "." not in key]

    def load_from_file(self):
        """Loads configuration from config.json if it exists."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # migration: a config written before `language` was a policy
                # carries the old default, and the old default is a pin. An
                # install updated from there kept transcribing italian speech
                # as english — whisper does not fail on a wrong pin, it
                # translates — and nothing anywhere said so.
                if data.get("config_version") is None and data.get("language") == "en":
                    data["language"] = "auto"
                    logger.warning(
                        "config.json predates the language setting and pins her ears "
                        "to english, which is what it defaulted to rather than "
                        "something anybody chose. Detecting instead. To keep "
                        "english, set it in Settings -> Language, which writes the "
                        "choice down as one."
                    )

                # migration: the window used to be three independent numbers,
                # and every install carries the three defaults written out. Now
                # they follow the ceiling, so leaving them pinned would make
                # the ceiling a placebo — moved to 0 unless somebody chose
                # something of their own, which stays chosen.
                consciousness = data.get("consciousness")
                if isinstance(consciousness, dict):
                    for key, legacy in (("handoff_trigger_tokens", 120_000),
                                        ("handoff_target_tokens", 50_000),
                                        ("hot_tokens", 30_000)):
                        if consciousness.get(key) == legacy:
                            consciousness[key] = 0

                # migration: `consciousness.enabled` is gone — the mind is the
                # only path and is always on. A stored `false` used to leave her
                # mute with every dashboard chat waiting out the 90s correlation
                # timeout, which read as her choosing silence. Drop it so an old
                # file cannot keep that state.
                if isinstance(consciousness, dict):
                    if consciousness.pop("enabled", None) is not None:
                        logger.warning(
                            "config.json carries consciousness.enabled, which no longer "
                            "means anything — the mind is always on. Dropping it."
                        )

                # migration: `group_salience` was declared at 0.6 but never read,
                # so every group message actually pulled at 0.8. A stored 0.6 is
                # the old default somebody saved, not a choice — drop it so the
                # wired default (0.8) keeps the historical behaviour. Anything
                # else was chosen on purpose and stays.
                skills = data.get("skills")
                if isinstance(skills, dict):
                    telegram = skills.get("telegram")
                    if isinstance(telegram, dict) and telegram.get("group_salience") == 0.6:
                        telegram.pop("group_salience", None)
                        logger.warning(
                            "config.json carries telegram.group_salience 0.6, which was "
                            "the displayed default of a setting that was never read — "
                            "group messages always pulled at 0.8. Dropping it so the "
                            "behaviour stays what it was. Set Group pull explicitly "
                            "to keep 0.6."
                        )

                # migration: image to avatar source
                if "obs_image_source" in data and "obs_avatar_source" not in data:
                    data["obs_avatar_source"] = data.pop("obs_image_source")

                # migration: the moods were renamed to the plain names of the
                # feelings, and every one of these dicts is keyed by mood
                if "avatar_map" in data:
                    data["avatar_map"] = rename_legacy(data["avatar_map"])
                stage = data.get("stage")
                if isinstance(stage, dict):
                    for key in ("mood_clips", "vts_expressions", "vts_clips"):
                        if key in stage:
                            stage[key] = rename_legacy(stage[key])

                # update fields
                for key, value in data.items():
                    if key == "config_version":
                        # what this build understands, not what was written by
                        # whatever wrote the file last
                        continue
                    if hasattr(self, key):
                        # env always wins for secrets; config.json only fills a
                        # var that is not set
                        if key in self.SECRET_KEYS:
                            current_val = getattr(self, key, None)
                            if current_val:
                                continue  # env var is set → it always wins
                            if value is None or value == "":
                                continue  # env var not set and config.json empty → nothing to apply
                            # env var not set but config.json has a value → use it

                        current = getattr(self, key, None)
                        if isinstance(current, dict) and isinstance(value, dict):
                            setattr(self, key, deep_merge(current, value))
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
            # atomic: a torn config.json is read back as defaults on the next start
            atomic_write_text(Path(CONFIG_FILE), json.dumps(data, indent=4))
            logger.info(f"Configuration saved to {CONFIG_FILE} (secrets excluded)")
        except Exception as e:
            logger.error(f"Error saving config.json: {e}")

    def public_dict(self) -> Dict[str, Any]:
        """The config as the UI may see it: every secret removed or masked.

        `GET /config` is unauthenticated and reachable from any page the browser
        has open, so it must never carry a usable key. Masked (rather than
        removed) nested secrets so the UI can still show 'a token is set'.
        """
        data = asdict(self)

        for secret in self.SECRET_KEYS:
            data.pop(secret, None)

        data["skills"] = self.public_skills()
        return data

    def public_skills(self) -> Dict[str, Dict[str, Any]]:
        """Every skill block as the UI may see it, with its secrets masked.

        A key typed into the dashboard lives in the block in memory until the
        next start, so any endpoint handing a block out must go through here.
        """
        skills = copy.deepcopy(self.skills)
        for skill_key, field_name in SECRET_SKILL_FIELDS:
            block = skills.get(skill_key)
            if isinstance(block, dict) and field_name in block:
                block[field_name] = MASK if block[field_name] else ""
        return skills
