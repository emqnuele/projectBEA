"""Every setting Bea has, declared once.

The dashboard renders this schema instead of hard-coding a form per skill, so
a new knob is one `Setting` here and nothing else. Validation lives here too:
the API layer only decides the status code.

A section either lives inside `config.skills[key]` (`scope="skills"`) or is a
top-level dict on the config (`scope="root"`).
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from src.core.config import MASK

TYPES = ("bool", "int", "float", "string", "secret", "select", "list")


class ValidationError(ValueError):
    """A rejected settings payload, with the offending keys named."""


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    type: str
    help: str
    default: Any = None
    options: Sequence[str] = ()
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    # a value that only takes effect after a restart, so the ui can say so
    restart: bool = False

    @property
    def secret(self) -> bool:
        return self.type == "secret"

    def describe(self) -> Dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "type": self.type,
            "help": self.help, "default": self.default,
            "options": list(self.options), "min": self.minimum,
            "max": self.maximum, "restart": self.restart,
        }


@dataclass(frozen=True)
class Section:
    key: str
    label: str
    blurb: str
    scope: str                      # "skills" | "root"
    settings: List[Setting] = field(default_factory=list)
    # a platform section has a live on/off switch the skill registry owns
    toggleable: bool = False

    def get(self, key: str) -> Optional[Setting]:
        return next((s for s in self.settings if s.key == key), None)


# --- coercion ---------------------------------------------------------------

_TRUE = {"1", "true", "yes", "on", "si", "sì"}
_FALSE = {"0", "false", "no", "off", ""}


def _as_bool(raw: Any) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError("expected true or false")


def _as_number(raw: Any, cast) -> Any:
    if isinstance(raw, bool):
        raise ValueError("expected a number")
    try:
        return cast(raw)
    except (TypeError, ValueError) as e:
        raise ValueError("expected a number") from e


def _as_list(raw: Any) -> List[str]:
    if isinstance(raw, (list, tuple)):
        return [str(v).strip() for v in raw if str(v).strip()]
    return [part.strip() for part in str(raw).split(",") if part.strip()]


def coerce(setting: Setting, raw: Any) -> Any:
    """One value into the type the setting declares. Raises ValueError."""
    if setting.type == "bool":
        return _as_bool(raw)
    if setting.type == "int":
        return _bounded(setting, _as_number(raw, int))
    if setting.type == "float":
        return _bounded(setting, _as_number(raw, float))
    if setting.type == "list":
        return _as_list(raw)
    if setting.type == "select":
        value = str(raw)
        if setting.options and value not in setting.options:
            raise ValueError(f"expected one of {', '.join(setting.options)}")
        return value
    return "" if raw is None else str(raw)


def _bounded(setting: Setting, value):
    if setting.minimum is not None and value < setting.minimum:
        raise ValueError(f"must be at least {setting.minimum}")
    if setting.maximum is not None and value > setting.maximum:
        raise ValueError(f"must be at most {setting.maximum}")
    return value


# --- the schema -------------------------------------------------------------

_REASONING = ("off", "low", "medium", "high", "auto")

TELEGRAM = Section(
    key="telegram", label="Telegram", scope="skills", toggleable=True,
    blurb="Groups and DMs. She reads everything and answers where she is wanted.",
    settings=[
        Setting("enabled", "On", "bool", "Whether she is connected to Telegram at all.", False),
        Setting("token", "Bot token", "secret",
                "From @BotFather. Prefer the TELEGRAM_TOKEN environment variable.",
                restart=True),
        Setting("owner_id", "Your Telegram id", "string",
                "Your numeric id. Messages from it are treated as coming from her owner."),
        Setting("allowed_chats", "Allowed chats", "list",
                "Chat ids she may speak in, comma separated. Empty means every chat.", []),
        Setting("read_media", "Read photos, stickers and voice notes", "bool",
                "Off, she only sees plain text and is blind to everything else.", True),
        Setting("reactions", "May react with an emoji", "bool",
                "Lets her answer a message with a reaction instead of writing.", True),
        Setting("transcribe_voice", "Transcribe voice notes", "bool",
                "Runs voice notes through speech-to-text so she can answer them.", True),
        Setting("followup_enabled", "Keep a conversation going", "bool",
                "When someone answers her, she answers back without needing her name.", True),
        Setting("followup_max_turns", "Follow-up turns", "int",
                "How many turns in a row she keeps up before waiting to be called again.",
                3, minimum=1, maximum=10),
        Setting("followup_window_seconds", "Follow-up window", "int",
                "How long after she spoke a reply still counts as talking to her.",
                180, minimum=10, maximum=3600),
        Setting("group_salience", "Group pull", "float",
                "How strongly an ordinary group message pulls at her attention.",
                0.6, minimum=0.0, maximum=1.0),
    ],
)

DISCORD = Section(
    key="discord", label="Discord", scope="skills", toggleable=True,
    blurb="Voice and text. The one place she has a real voice with other people.",
    settings=[
        Setting("enabled", "On", "bool", "Whether the Discord bot runs at all.", False),
        Setting("token", "Bot token", "secret",
                "From the Discord developer portal. Prefer the DISCORD_TOKEN variable.",
                restart=True),
        Setting("admin_id", "Your Discord id", "string",
                "Your numeric id. Admin commands answer to it and nobody else."),
        Setting("access_mode", "Who she listens to", "select",
                "Strict: only the whitelist. Boost: everyone, whitelist first. "
                "Open: everyone equally.",
                "boost", options=("strict", "boost", "open")),
        Setting("api_port", "Bot API port", "int",
                "Loopback port the engine talks to the bot on. Change it on a clash.",
                3030, minimum=1024, maximum=65535, restart=True),
        Setting("brain_api_url", "Engine URL", "string",
                "Where the bot calls back into the engine.",
                "http://127.0.0.1:8000", restart=True),
        Setting("interrupt_threshold_ms", "Interrupt after", "int",
                "How long someone must keep talking before she stops to listen.",
                2000, minimum=200, maximum=10000),
        Setting("invite_max_age_seconds", "Invite lifetime", "int",
                "How long an invite she sends stays valid. Never unlimited.",
                3600, minimum=60, maximum=604800),
        Setting("invite_max_uses", "Invite uses", "int",
                "How many people one invite of hers lets in.",
                1, minimum=1, maximum=100),
        Setting("auto_leave_seconds", "Leave an empty call after", "int",
                "Seconds alone in a voice channel before she leaves. 0 to stay.",
                120, minimum=0, maximum=3600),
    ],
)

TWITCH = Section(
    key="twitch", label="Twitch", scope="skills", toggleable=True,
    blurb="The stream chat. Loud, fast, and mostly texture rather than conversation.",
    settings=[
        Setting("enabled", "On", "bool", "Whether she is reading your chat.", False),
        Setting("channel", "Channel", "string", "The channel to read, without the #.", ""),
        Setting("nick", "Bot nick", "string",
                "The account she writes as. Empty reads anonymously and cannot write.", ""),
        Setting("oauth_token", "OAuth token", "secret",
                "Only needed to write. Reading chat needs no credentials at all.",
                restart=True),
        Setting("say_rate_limit", "Messages per 30s", "int",
                "Twitch times out an account that goes over 20. Stay under it.",
                19, minimum=1, maximum=100),
        Setting("announce_raids", "Notice raids", "bool",
                "A raid reaches her the way a donation does: she always reacts.", True),
        Setting("announce_subs", "Notice subs", "bool",
                "Subs, resubs and gifted subs become something she can thank you for.", True),
        Setting("chatter_salience", "Chat pull", "float",
                "How hard an ordinary chat line pulls. Low keeps a busy chat cheap.",
                0.4, minimum=0.0, maximum=1.0),
    ],
)

MINECRAFT = Section(
    key="minecraft", label="Minecraft", scope="skills", toggleable=True,
    blurb="A body on a vanilla server.",
    settings=[
        Setting("enabled", "On", "bool", "Whether she is in the game.", False),
        Setting("server_url", "Agent URL", "string",
                "The websocket her in-game body connects to.", "ws://127.0.0.1:8080"),
        Setting("idle_nudge_seconds", "Nudge her after", "int",
                "Seconds of nothing happening before she does something on her own. 0 never.",
                90, minimum=0, maximum=3600),
    ],
)

DONATIONS = Section(
    key="donations", label="Donations", scope="skills", toggleable=True,
    blurb="Money always earns a reaction.",
    settings=[
        Setting("enabled", "On", "bool", "Whether the donation webhook is live.", False),
    ],
)

MEMORY = Section(
    key="memory", label="Memory", scope="skills",
    blurb="What she keeps, and how easily she finds it again.",
    settings=[
        Setting("enabled", "On", "bool", "Turning this off makes her forget everything.", True),
        Setting("min_similarity", "Recall threshold", "float",
                "How close a memory must be to count. Higher recalls less, but truer.",
                0.35, minimum=0.0, maximum=1.0),
        Setting("embedding_model", "Embedding model", "string",
                "Must be multilingual if her people do not write in English.",
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2", restart=True),
    ],
)

DREAM = Section(
    key="dream", label="Dreaming", scope="skills", toggleable=True,
    blurb="At night she goes over the day and decides what it meant.",
    settings=[
        Setting("enabled", "On", "bool", "Whether she consolidates at night.", True),
        Setting("hour", "Hour", "int", "Local hour she does it.", 4, minimum=0, maximum=23),
    ],
)

ATTENTION = Section(
    key="attention", label="Attention", scope="root",
    blurb="What wakes her, and what she merely notices out of the corner of her eye.",
    settings=[
        Setting("enabled", "On", "bool",
                "Off, she reacts to literally everything. Expensive and exhausting.", True),
        Setting("cooldown_seconds", "Cooldown", "int",
                "How long she stays quiet after speaking, unless spoken to.",
                20, minimum=0, maximum=600),
        Setting("interject_threshold", "Interjection threshold", "float",
                "How much a message must concern her before she speaks up unasked.",
                0.45, minimum=0.0, maximum=1.0),
        Setting("trigger_words", "What she answers to", "list",
                "Saying one of these always reaches her, cooldown or not. Leave it "
                "empty and it follows her name.",
                []),
        Setting("hot_names", "Names she cares about", "list",
                "People and things that pull her into a conversation.", []),
        Setting("digest_max_lines", "Peripheral lines", "int",
                "How much of what she missed she is shown afterwards.",
                8, minimum=0, maximum=40),
        Setting("followup_enabled", "Always answer a reply", "bool",
                "When someone replies to her, she replies back without needing her "
                "name. Off, every message goes through the same judgement call.", True),
        Setting("followup_window_seconds", "A reply still counts for", "int",
                "How long after she spoke an answer is still an answer.",
                180, minimum=10, maximum=3600),
        Setting("followup_max_turns", "Turns in a row", "int",
                "How long she keeps it up before waiting to be called again.",
                3, minimum=1, maximum=10),
    ],
)

RHYTHM = Section(
    key="rhythm", label="Initiative", scope="root",
    blurb="When she starts something instead of waiting to be spoken to.",
    settings=[
        Setting("enabled", "On", "bool", "Whether she has a rhythm of her own at all.", True),
        Setting("tick_seconds", "Check every", "int",
                "How often she looks around for something worth starting.",
                900, minimum=30, maximum=7200),
        Setting("spontaneous_enabled", "May open a conversation", "bool",
                "Off, she only ever answers.", True),
        Setting("spontaneous_probability", "How often", "float",
                "Even when everything lines up, usually she still doesn't.",
                0.15, minimum=0.0, maximum=1.0),
        Setting("spontaneous_min_silence", "Only after silence of", "int",
                "Seconds she must have been quiet there first.",
                3600, minimum=60, maximum=86400),
        Setting("spontaneous_min_activity", "Only if at least", "int",
                "Messages recently, so she is not talking to a dead room.",
                3, minimum=0, maximum=100),
        Setting("cross_platform", "May follow you elsewhere", "bool",
                "Lets her carry something from one place to another — say, DM you on "
                "Telegram about what happened on Discord.", True),
    ],
)

MODELS = Section(
    key="models", label="Models", scope="root",
    blurb="Which models she thinks with, and how fast they answer.",
    settings=[
        Setting("mind", "Mind pool", "list",
                "provider:model, comma separated. Every one must support tool calling.",
                [], restart=True),
        Setting("background", "Background pool", "list",
                "Diary, summaries, person cards. Slow and cheap is fine here.",
                [], restart=True),
        Setting("reasoning", "Thinking", "select",
                "Off is what makes her quick enough for a voice call. Auto leaves each "
                "model's default alone.",
                "off", options=_REASONING, restart=True),
    ],
)

CONSCIOUSNESS = Section(
    key="consciousness", label="Mind", scope="root",
    blurb="The shape of one turn of thought.",
    settings=[
        Setting("idle_after", "Idle after", "float",
                "Seconds of silence before she notices there is silence.",
                240.0, minimum=10, maximum=3600),
        Setting("window", "Batching window", "float",
                "How long she waits to see if more arrives before thinking.",
                0.3, minimum=0.0, maximum=5.0),
        Setting("burst_steps", "Steps per turn", "int",
                "How many tool steps one live turn may take.",
                6, minimum=1, maximum=20),
        Setting("conversation_steps", "Steps per reply", "int",
                "A written reply is not an expedition.",
                3, minimum=1, maximum=10),
        Setting("history_limit", "Context length", "int",
                "How many past messages she carries in the live loop.",
                30, minimum=4, maximum=200),
    ],
)

SECTIONS: List[Section] = [
    TELEGRAM, DISCORD, TWITCH, MINECRAFT, DONATIONS,
    ATTENTION, RHYTHM, MODELS, CONSCIOUSNESS, MEMORY, DREAM,
]

_BY_KEY = {s.key: s for s in SECTIONS}


def section(key: str) -> Section:
    """The section named `key`. Raises KeyError for anything else."""
    return _BY_KEY[key]


# --- reading and writing ----------------------------------------------------


def _block(config, sec: Section) -> Dict[str, Any]:
    if sec.scope == "skills":
        return config.skills.setdefault(sec.key, {})
    current = getattr(config, sec.key, None)
    if not isinstance(current, dict):
        current = {}
        setattr(config, sec.key, current)
    return current


def describe(config) -> Dict[str, Any]:
    """The whole schema plus current values, safe to hand to a browser."""
    out = []
    for sec in SECTIONS:
        block = _block(config, sec)
        values = {}
        for setting in sec.settings:
            raw = block.get(setting.key, setting.default)
            if setting.secret:
                values[setting.key] = MASK if raw else ""
            else:
                values[setting.key] = raw
        out.append({
            "key": sec.key, "label": sec.label, "blurb": sec.blurb,
            "scope": sec.scope, "toggleable": sec.toggleable,
            "settings": [s.describe() for s in sec.settings],
            "values": values,
        })
    return {"sections": out}


def apply_section(config, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validates the whole payload, then writes it. Raises ValidationError.

    All-or-nothing on purpose: a form that half-saves leaves the user unable to
    tell what took effect.
    """
    sec = section(key)
    block = _block(config, sec)

    errors: Dict[str, str] = {}
    staged: Dict[str, Any] = {}

    for field_key, raw in payload.items():
        setting = sec.get(field_key)
        if setting is None:
            errors[field_key] = "unknown setting"
            continue
        # the ui reads secrets back masked; writing that would replace the real
        # one with asterisks
        if setting.secret and raw == MASK:
            continue
        try:
            staged[field_key] = coerce(setting, raw)
        except ValueError as e:
            errors[field_key] = str(e)

    if errors:
        detail = "; ".join(f"{k}: {v}" for k, v in sorted(errors.items()))
        raise ValidationError(detail)

    block.update(staged)
    return staged


def restart_needed(key: str, changed: Dict[str, Any]) -> bool:
    sec = section(key)
    return any((sec.get(k) or Setting(k, k, "string", "")).restart for k in changed)
