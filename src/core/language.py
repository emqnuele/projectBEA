"""The one place that knows what language she is working in.

`config.language` used to reach exactly three files — the STT providers — while
the dashboard promised it also decided "how she answers". It did not: every
prompt, every voice and every trigger word was English regardless. This module
is the missing middle. Everything that needs to know a language asks here, and
nothing else parses a language code by hand.

Two things are deliberately kept apart, because they are not the same question:

- **What she hears.** `whisper_code` is a pin for the transcriber, and `AUTO`
  means "work it out yourself". Measured on real audio, detection beats a pin
  in every case and a *wrong* pin is catastrophic — Italian speech pinned to
  `ja` comes back as invented Japanese — so `AUTO` is the default.
- **What she says.** She always answers in the language she was addressed in;
  that is `MIRROR`, and it is in every prompt. `config.language` only decides
  what she reaches for when she speaks *first* and there is no one to mirror:
  the idle monologue, a spontaneous line, narrating Minecraft to an empty room.

That split is what makes one turn able to answer Telegram in Italian and Twitch
in English, which is a thing she really does — perceptions from every surface
arrive in one frame and are answered in one turn.
"""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

# no pin: let the transcriber detect, and let her mirror whoever is talking
AUTO = "auto"


@dataclass(frozen=True)
class Language:
    """A language this engine can be set to, and the names it goes by."""

    code: str           # the primary subtag, which is also the whisper code
    endonym: str        # what it calls itself, for prompts and for menus
    english_name: str   # what to call it in English-language logs and docs


# The nine the dashboard and the setup wizard already offered between them.
# English, Italian and Japanese are the ones with tests; the rest ride the same
# code paths and are no worse off than they were.
LANGUAGES: Dict[str, Language] = {
    "en": Language("en", "English", "English"),
    "it": Language("it", "Italiano", "Italian"),
    "ja": Language("ja", "日本語", "Japanese"),
    "es": Language("es", "Español", "Spanish"),
    "fr": Language("fr", "Français", "French"),
    "de": Language("de", "Deutsch", "German"),
    "pt": Language("pt", "Português", "Portuguese"),
    "zh": Language("zh", "中文", "Chinese"),
    "ko": Language("ko", "한국어", "Korean"),
}

# Everything that has ever been written into a config.json or picked from a
# menu, mapped onto the code above. `jp` is the dashboard's own spelling of
# Japanese and whisper refuses it outright; the endonyms are what the setup
# wizard's voice menu is keyed by.
ALIASES: Dict[str, str] = {
    "jp": "ja", "jpn": "ja", "japanese": "ja", "日本語": "ja",
    "cn": "zh", "chinese": "zh", "中文": "zh", "zh-cn": "zh", "zh-tw": "zh",
    "kr": "ko", "korean": "ko", "한국어": "ko",
    "english": "en", "english (us)": "en", "english (uk)": "en",
    "italian": "it", "italiano": "it",
    "spanish": "es", "español": "es", "espanol": "es",
    "french": "fr", "français": "fr", "francais": "fr",
    "german": "de", "deutsch": "de",
    "portuguese": "pt", "português": "pt", "portugues": "pt",
    "português (br)": "pt", "portuguese (br)": "pt",
}

# what an unset language falls back to when something insists on a real one
FALLBACK = "en"


def resolve(raw: Optional[str]) -> str:
    """A code this engine knows, or `AUTO`.

    Takes whatever is in the config or came back from a menu: a bare code, a
    regional tag (`it-IT`), an endonym (`Italiano`), an old spelling (`jp`).
    Anything it cannot place becomes `AUTO` rather than an error — a typo in
    config.json must cost detection, never her voice.
    """
    text = (raw or "").strip().lower().replace("_", "-")
    if not text or text == AUTO:
        return AUTO
    if text in LANGUAGES:
        return text
    if text in ALIASES:
        return ALIASES[text]
    # a regional tag: `it-IT`, `pt-BR`, and the voice ids that carry one
    primary = text.split("-", 1)[0]
    if primary in LANGUAGES:
        return primary
    return ALIASES.get(primary, AUTO)


def named(raw: Optional[str]) -> Optional[Language]:
    """The `Language` behind a code, or None when it resolves to `AUTO`."""
    code = resolve(raw)
    return LANGUAGES.get(code)


def endonym(raw: Optional[str]) -> str:
    """What the language calls itself, for a prompt or a menu."""
    language = named(raw)
    return language.endonym if language else ""


def whisper_code(raw: Optional[str]) -> Optional[str]:
    """What to pin the transcriber to, or None to let it detect.

    None rather than `"auto"`: every transcriber we drive — faster-whisper,
    groq, openrouter — reads a missing language as "detect it", and each of
    them rejects the literal string.
    """
    code = resolve(raw)
    return None if code == AUTO else code


def options() -> Tuple[Tuple[str, str], ...]:
    """`(code, endonym)` for every language, `AUTO` first. For menus."""
    return ((AUTO, "Detect automatically"),
            *((code, language.endonym) for code, language in LANGUAGES.items()))


# --- what goes in the prompt -------------------------------------------------

# Measured against the real prompt stack, n=8 per cell: without this block a
# Japanese message came back in English 5 times out of 8, because ~16k
# characters of English instructions outweigh one Japanese line. With it,
# Italian, English and Japanese were all 8/8, and a batch carrying all three
# at once was answered correctly in each conversation.
_MIRROR = (
    "## LANGUAGE\n"
    "Always answer in the language you were addressed in. Each conversation "
    "keeps its own language: a message in Italian is answered in Italian even "
    "when the line above it was English."
)

_SPEAKS_FIRST = (
    "\nWhen you speak first and there is no one to mirror — thinking out loud, "
    "starting something yourself — speak {endonym}."
)


def directive(raw: Optional[str]) -> str:
    """The `## LANGUAGE` block for the system prompt.

    It belongs in the cached half of the prompt, not in the per-turn briefing:
    it is true for the whole session, and a volatile line at the top of a
    request costs the entire prompt cache on every single turn.
    """
    language = named(raw)
    if language is None:
        return _MIRROR
    return _MIRROR + _SPEAKS_FIRST.format(endonym=language.endonym)


def write_in(raw: Optional[str]) -> str:
    """One line telling a background pass which language to write its output in.

    The diary, the dreamer and the person profiler all read a conversation and
    write facts back into memory. Those facts are injected into her context
    every turn, so a pass that always wrote English quietly pulled an Italian
    conversation back towards English — the drift was coming out of her own
    memory, not out of the model.
    """
    language = named(raw)
    if language is None:
        return ("Write your output in the language the conversation is in. "
                "If it is in several, use the one most of it is in.")
    return (f"Write your output in {language.english_name}, whatever language "
            f"the conversation itself is in.")
