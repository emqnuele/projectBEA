"""Every voice engine as data: what it can say, and in which language.

The same shape as `llm/providers.py`, and for the same reason. Each engine used
to carry its own idea of language: EdgeTTS inferred one from the voice id,
Kokoro had a whole separate `kokoro_lang` field nobody kept in step, and
Orpheus had no concept of one at all. Switching engine silently threw the
language away, and no single place could answer "can this setup say this".

So the engines stopped deciding. A wrapper is handed a voice and synthesises
it; which voice that is, whether it can speak the language, and what to do when
it cannot, is decided here — once, for all of them. Adding an engine is one
entry in `PROVIDERS` plus a builder in `factory.py`.

What deliberately does *not* happen here: nothing silently replaces a voice
somebody chose. `voice_for` reports what the config actually means, and
`plan_for_language` returns what *would* change, for the settings layer to
apply where the owner can see it.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Optional, Tuple

from src.core import language as language_module
from src.core.language import AUTO


@dataclass(frozen=True)
class Voice:
    """One voice an engine offers, and the language it speaks."""

    id: str        # what the engine is handed: `it-IT-IsabellaNeural`, `if_sara`, `zoe`
    label: str     # what a person picking one reads
    language: str  # a code from `core.language`, or AUTO when it speaks anything


@dataclass(frozen=True)
class VoiceProvider:
    """One row per engine id.

    `voice_field` is the config field holding the chosen voice, which is the
    only per-engine knob this module needs to know about. `open_catalogue`
    means the listed voices are a curated subset and the engine will accept
    ids that are not in the table — EdgeTTS has thousands, and refusing one
    somebody pasted in would be a regression, not a safety net.
    """

    id: str
    label: str
    blurb: str
    voice_field: str
    voices: Tuple[Voice, ...]
    local: bool
    needs_key: bool = False
    key_field: str = ""
    url_field: str = ""
    open_catalogue: bool = False
    # engines that phonemise per language rather than per voice have to be told
    # which one, in their own spelling. Empty means the voice already says it.
    language_field: str = ""
    engine_languages: Mapping[str, str] = field(default_factory=dict)


def _edge(code: str, *pairs: Tuple[str, str]) -> Tuple[Voice, ...]:
    return tuple(Voice(voice_id, label, code) for voice_id, label in pairs)


# A curated shortlist per language, not the full catalogue: EdgeTTS alone has
# thousands, and a menu nobody can read is worse than four good names. Every id
# here was checked against `edge_tts.list_voices()`.
EDGE_VOICES: Tuple[Voice, ...] = (
    *_edge("en", ("en-US-AvaNeural", "Ava (US)"), ("en-US-AndrewNeural", "Andrew (US)"),
           ("en-GB-SoniaNeural", "Sonia (UK)"), ("en-GB-RyanNeural", "Ryan (UK)")),
    *_edge("it", ("it-IT-IsabellaNeural", "Isabella"), ("it-IT-ElsaNeural", "Elsa"),
           ("it-IT-DiegoNeural", "Diego")),
    *_edge("ja", ("ja-JP-NanamiNeural", "Nanami"), ("ja-JP-KeitaNeural", "Keita")),
    *_edge("es", ("es-ES-ElviraNeural", "Elvira"), ("es-ES-AlvaroNeural", "Álvaro")),
    *_edge("fr", ("fr-FR-DeniseNeural", "Denise"), ("fr-FR-HenriNeural", "Henri")),
    *_edge("de", ("de-DE-KatjaNeural", "Katja"), ("de-DE-ConradNeural", "Conrad")),
    *_edge("pt", ("pt-BR-FranciscaNeural", "Francisca"), ("pt-BR-AntonioNeural", "Antônio")),
    *_edge("zh", ("zh-CN-XiaoxiaoNeural", "Xiaoxiao"), ("zh-CN-YunxiNeural", "Yunxi")),
    *_edge("ko", ("ko-KR-SunHiNeural", "SunHi"), ("ko-KR-InJoonNeural", "InJoon")),
)

# The eleven voices in the v0.19 pack, which is the one this project pins:
# the first letter is the accent (a American, b British) and the second the
# gender. Enumerated from the voice file rather than remembered.
#
# They are all English, and that is a property of the weights, not a shortlist.
# Kokoro v1.0 adds Italian, Japanese and six more languages — but every
# kokoro-onnx release that can read the v1.0 pack requires numpy>=2, and this
# project pins numpy<2. Until that moves, Kokoro is an English engine and says
# so, so that nobody picks it for Japanese and goes silent on stream.
KOKORO_VOICES: Tuple[Voice, ...] = (
    Voice("af_bella", "Bella (US)", "en"),
    Voice("af_nicole", "Nicole (US)", "en"),
    Voice("af_sarah", "Sarah (US)", "en"),
    Voice("af_sky", "Sky (US)", "en"),
    Voice("am_adam", "Adam (US)", "en"),
    Voice("am_michael", "Michael (US)", "en"),
    Voice("bf_emma", "Emma (UK)", "en"),
    Voice("bf_isabella", "Isabella (UK)", "en"),
    Voice("bm_george", "George (UK)", "en"),
    Voice("bm_lewis", "Lewis (UK)", "en"),
)

# what Kokoro calls each language when it phonemises: espeak-ng's names, not
# ours. Wider than the voice list on purpose — the phonemiser handles these
# whatever the weights offer, and the table stops being a lie the day the
# voice pack catches up.
KOKORO_LANGUAGES: Mapping[str, str] = {
    "en": "en-us", "ja": "ja", "fr": "fr-fr", "zh": "cmn", "ko": "ko",
}

# Orpheus ships English voices only. Listed so the wizard and the settings can
# say so out loud instead of letting somebody pick Italian and go mute.
ORPHEUS_VOICES: Tuple[Voice, ...] = (
    Voice("zoe", "Zoe", "en"),
    Voice("tara", "Tara", "en"),
    Voice("leo", "Leo", "en"),
    Voice("leah", "Leah", "en"),
)


PROVIDERS: Dict[str, VoiceProvider] = {
    "edge": VoiceProvider(
        id="edge", label="EdgeTTS",
        blurb="Free, no key, every language. Needs internet.",
        voice_field="tts_voice", voices=EDGE_VOICES, local=False,
        open_catalogue=True),
    "kokoro": VoiceProvider(
        id="kokoro", label="Kokoro",
        blurb="Runs on this machine. No key, no account, nothing leaves the room.",
        voice_field="kokoro_voice", voices=KOKORO_VOICES, local=True,
        language_field="kokoro_lang", engine_languages=KOKORO_LANGUAGES),
    "orpheus": VoiceProvider(
        id="orpheus", label="Orpheus",
        blurb="The most expressive. English only, and needs a Baseten endpoint.",
        voice_field="orpheus_voice", voices=ORPHEUS_VOICES, local=False,
        needs_key=True, key_field="orpheus_key", url_field="orpheus_endpoint"),
}

DEFAULT_PROVIDER = "edge"


def get(provider_id: Optional[str]) -> Optional[VoiceProvider]:
    return PROVIDERS.get((provider_id or "").strip().lower())


def for_config(config: Any) -> VoiceProvider:
    """The engine this config selects, falling back rather than failing.

    A typo in `tts_provider` used to be caught in the factory and turned into
    EdgeTTS there. It is the same answer here, so that everything asking "what
    can this setup say" agrees with what will actually be built.
    """
    return get(getattr(config, "tts_provider", "")) or PROVIDERS[DEFAULT_PROVIDER]


# --- what an engine can say -------------------------------------------------


def languages(provider: VoiceProvider) -> Tuple[str, ...]:
    """Every language this engine has a voice for, in declaration order."""
    seen: Dict[str, None] = {}
    for voice in provider.voices:
        if voice.language != AUTO:
            seen.setdefault(voice.language, None)
    return tuple(seen)


def speaks(provider: VoiceProvider, code: Optional[str]) -> bool:
    """Can this engine say anything in that language?

    `AUTO` is always true: nothing has been asked for yet.
    """
    resolved = language_module.resolve(code)
    return resolved == AUTO or resolved in languages(provider)


def for_language(code: Optional[str]) -> Tuple[VoiceProvider, ...]:
    """The engines that can speak it. What the setup wizard offers."""
    return tuple(p for p in PROVIDERS.values() if speaks(p, code))


def voices_for(provider: VoiceProvider, code: Optional[str]) -> Tuple[Voice, ...]:
    """The voices to offer for a language. Everything, when nothing is pinned."""
    resolved = language_module.resolve(code)
    if resolved == AUTO:
        return provider.voices
    return tuple(v for v in provider.voices if v.language == resolved)


def language_of(provider: VoiceProvider, voice_id: str) -> str:
    """Which language a voice speaks, or `AUTO` when the engine will not say.

    A voice that is not in the table is only unknown on an open catalogue —
    EdgeTTS ids carry their own locale, so `it-IT-GiuseppeMultilingualNeural`
    answers for itself without being listed.
    """
    wanted = (voice_id or "").strip()
    for voice in provider.voices:
        if voice.id == wanted:
            return voice.language
    if provider.open_catalogue:
        return language_module.resolve(wanted)
    return AUTO


def default_voice(provider: VoiceProvider, code: Optional[str]) -> Optional[Voice]:
    """The voice to reach for in a language, or None when it has none."""
    available = voices_for(provider, code)
    return available[0] if available else None


def engine_language(provider: VoiceProvider, code: Optional[str]) -> str:
    """The language in the engine's own spelling, for engines that want one."""
    resolved = language_module.resolve(code)
    if resolved == AUTO:
        return ""
    return provider.engine_languages.get(resolved, resolved)


# --- what a config actually means -------------------------------------------


def voice_for(config: Any) -> Voice:
    """The voice this config will really be spoken in.

    Deliberately not "the voice the language implies": a chosen voice is a
    choice, and an owner who set an Italian voice while `language` still said
    English must not have it swapped underneath them on upgrade. When nothing
    usable is configured this falls back to the language's default voice, and
    failing that to the engine's first one, so there is always a voice.
    """
    provider = for_config(config)
    configured = str(getattr(config, provider.voice_field, "") or "").strip()
    if configured:
        return Voice(configured, configured, language_of(provider, configured))

    fallback = default_voice(provider, getattr(config, "language", "")) \
        or (provider.voices[0] if provider.voices else None)
    return fallback or Voice("", "", AUTO)


def plan_for_language(config: Any, code: Optional[str]) -> Dict[str, Any]:
    """The config fields that should change to move this setup to a language.

    Returned rather than applied: the settings layer writes it where the owner
    can see it, and the wizard writes it as part of an answer they gave. Empty
    when the engine cannot speak the language at all — `speaks` is the question
    to ask first, and `warnings` is what to say about it.
    """
    provider = for_config(config)
    resolved = language_module.resolve(code)
    changes: Dict[str, Any] = {}

    # nothing to plan for a language this engine has no voice in: pointing its
    # phonemiser at one it cannot say would be worse than leaving it alone
    if not speaks(provider, resolved):
        return changes

    voice = default_voice(provider, resolved)
    if voice is not None and getattr(config, provider.voice_field, "") != voice.id:
        # only when the configured voice cannot speak it: replacing a voice that
        # already can would undo a preference for no reason
        current = str(getattr(config, provider.voice_field, "") or "")
        if language_of(provider, current) != resolved:
            changes[provider.voice_field] = voice.id

    if provider.language_field:
        spelling = engine_language(provider, resolved)
        if spelling and getattr(config, provider.language_field, "") != spelling:
            changes[provider.language_field] = spelling

    return changes


def warnings(config: Any) -> Tuple[str, ...]:
    """Everything wrong with this combination, in plain words.

    Read by the settings API on save and by `--doctor`. It never blocks: the
    owner is told, and stays in charge of their own config.
    """
    provider = for_config(config)
    wanted = language_module.resolve(getattr(config, "language", ""))
    out = []

    if wanted != AUTO and not speaks(provider, wanted):
        out.append(
            f"{provider.label} has no {language_module.endonym(wanted)} voice, and "
            f"`language` is set to {wanted!r}. She will be silent whenever she "
            f"answers in it. EdgeTTS speaks every language she supports."
        )

    voice = voice_for(config)
    spoken = voice.language
    if wanted != AUTO and spoken != AUTO and spoken != wanted and speaks(provider, wanted):
        out.append(
            f"The voice {voice.id!r} speaks {language_module.endonym(spoken) or 'another language'}, "
            f"but `language` is set to {wanted!r}. Pick a voice that matches, or she "
            f"will read one language in another one's accent."
        )

    if provider.needs_key and not getattr(config, provider.key_field, None):
        out.append(f"{provider.label} needs {provider.key_field} and it is not set.")

    return tuple(out)


__all__ = [
    "AUTO", "DEFAULT_PROVIDER", "PROVIDERS", "Voice", "VoiceProvider",
    "default_voice", "engine_language", "for_config", "for_language", "get",
    "language_of", "languages", "plan_for_language", "speaks", "voice_for",
    "voices_for", "warnings",
]
