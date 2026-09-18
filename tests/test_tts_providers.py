"""The voice engines are options; the language policy is one thing above them.

Each engine used to carry its own idea of a language — EdgeTTS inferred one
from the voice id, Kokoro had a separate `kokoro_lang` nobody kept in step,
Orpheus had none — so switching engine threw the language away and nothing
could answer "can this setup say this".
"""

from src.core.config import BrainConfig
from src.modules.tts import providers
from src.modules.tts.factory import BUILDERS, backend_name, kokoro_language


def config(**overrides) -> BrainConfig:
    settings = BrainConfig()
    for key, value in overrides.items():
        setattr(settings, key, value)
    return settings


# --- the table is the truth -------------------------------------------------


def test_every_engine_has_a_builder_and_every_builder_an_engine():
    """A row without a builder is a menu entry that explodes when picked."""
    assert set(providers.PROVIDERS) == set(BUILDERS)


def test_every_engine_names_a_real_config_field():
    settings = BrainConfig()
    for provider in providers.PROVIDERS.values():
        assert hasattr(settings, provider.voice_field), provider.id
        if provider.language_field:
            assert hasattr(settings, provider.language_field), provider.id
        if provider.key_field:
            assert hasattr(settings, provider.key_field), provider.id


def test_every_voice_declares_a_language_we_know():
    from src.core.language import LANGUAGES
    for provider in providers.PROVIDERS.values():
        for voice in provider.voices:
            assert voice.language in LANGUAGES, f"{provider.id}/{voice.id}"


# --- what an engine can say -------------------------------------------------


def test_edge_speaks_the_three_that_matter():
    edge = providers.PROVIDERS["edge"]
    for code in ("en", "it", "ja"):
        assert providers.speaks(edge, code)


def test_kokoro_is_honest_about_being_english_only():
    """The v0.19 pack this project pins has no other language in it."""
    kokoro = providers.PROVIDERS["kokoro"]
    assert providers.languages(kokoro) == ("en",)
    assert not providers.speaks(kokoro, "it")
    assert not providers.speaks(kokoro, "ja")


def test_orpheus_is_honest_about_being_english_only():
    assert providers.languages(providers.PROVIDERS["orpheus"]) == ("en",)


def test_an_unset_language_rules_nothing_out():
    for provider in providers.PROVIDERS.values():
        assert providers.speaks(provider, "auto")
        assert providers.speaks(provider, "")


def test_the_wizard_is_offered_only_engines_that_can_speak_it():
    assert {p.id for p in providers.for_language("it")} == {"edge"}
    assert {p.id for p in providers.for_language("ja")} == {"edge"}
    assert {p.id for p in providers.for_language("en")} == set(providers.PROVIDERS)
    assert {p.id for p in providers.for_language("auto")} == set(providers.PROVIDERS)


# --- reading a voice --------------------------------------------------------


def test_a_listed_voice_reports_its_language():
    edge = providers.PROVIDERS["edge"]
    assert providers.language_of(edge, "it-IT-IsabellaNeural") == "it"
    assert providers.language_of(edge, "ja-JP-NanamiNeural") == "ja"


def test_an_unlisted_edge_voice_still_answers_from_its_own_locale():
    """EdgeTTS has thousands; a pasted id must not become a mystery."""
    edge = providers.PROVIDERS["edge"]
    assert providers.language_of(edge, "it-IT-GiuseppeMultilingualNeural") == "it"


def test_a_closed_catalogue_does_not_invent_a_language():
    kokoro = providers.PROVIDERS["kokoro"]
    assert providers.language_of(kokoro, "made_up") == providers.AUTO


# --- what a config means ----------------------------------------------------


def test_the_configured_voice_is_the_one_that_gets_used():
    assert providers.voice_for(config(tts_voice="ja-JP-KeitaNeural")).id == \
        "ja-JP-KeitaNeural"


def test_a_chosen_voice_is_never_swapped_for_the_language():
    """An owner who set an Italian voice under `language: en` meant it."""
    settings = config(language="en", tts_voice="it-IT-IsabellaNeural")
    assert providers.voice_for(settings).id == "it-IT-IsabellaNeural"


def test_an_empty_voice_falls_back_to_one_that_speaks_the_language():
    assert providers.voice_for(config(language="ja", tts_voice="")).id == \
        "ja-JP-NanamiNeural"


def test_an_unknown_engine_is_built_as_the_default_one():
    assert backend_name(config(tts_provider="nonsense")) == providers.DEFAULT_PROVIDER
    assert providers.for_config(config(tts_provider="nonsense")).id == "edge"


# --- moving a setup to a language -------------------------------------------


def test_a_plan_names_the_voice_the_language_needs():
    settings = config(tts_provider="edge", tts_voice="en-US-AvaNeural")
    assert providers.plan_for_language(settings, "it") == \
        {"tts_voice": "it-IT-IsabellaNeural"}


def test_a_plan_leaves_a_voice_that_already_speaks_it_alone():
    settings = config(tts_provider="edge", tts_voice="it-IT-DiegoNeural")
    assert providers.plan_for_language(settings, "it") == {}


def test_a_plan_for_an_engine_that_cannot_speak_it_changes_nothing():
    settings = config(tts_provider="kokoro", kokoro_voice="af_bella")
    assert providers.plan_for_language(settings, "ja") == {}


def test_a_plan_also_moves_the_phonemiser_for_engines_that_have_one():
    """A `kokoro_lang` left behind by an earlier language has to come back."""
    settings = config(tts_provider="kokoro", kokoro_voice="af_bella",
                      kokoro_lang="ja")
    assert providers.plan_for_language(settings, "en")["kokoro_lang"] == "en-us"


# --- kokoro's phonemiser ----------------------------------------------------


def test_kokoro_phonemises_in_the_language_of_its_voice():
    """`af_bella` is English whatever a stale `kokoro_lang` says."""
    settings = config(tts_provider="kokoro", kokoro_voice="af_bella",
                      kokoro_lang="ja")
    assert kokoro_language(settings) == "en-us"


def test_kokoro_falls_back_to_the_configured_language():
    settings = config(tts_provider="kokoro", kokoro_voice="", language="en")
    assert kokoro_language(settings) == "en-us"


def test_kokoro_keeps_a_voice_it_has_rather_than_phonemising_a_language_it_cannot_say():
    """An English voice read with a Japanese phonemiser is noise, not Japanese.

    The honest answer is the voice it actually has, plus the warning that says
    out loud she will not be answering in Japanese with this engine.
    """
    settings = config(tts_provider="kokoro", kokoro_voice="", language="ja")
    assert kokoro_language(settings) == "en-us"
    assert providers.warnings(settings)


def test_espeaks_own_spelling_is_used_rather_than_ours():
    kokoro = providers.PROVIDERS["kokoro"]
    assert providers.engine_language(kokoro, "en") == "en-us"
    assert providers.engine_language(kokoro, "zh") == "cmn"


# --- what it says is wrong --------------------------------------------------


def test_an_engine_that_cannot_speak_the_language_is_called_out():
    warnings = providers.warnings(config(tts_provider="kokoro", language="ja"))
    assert any("Kokoro" in w and "silent" in w for w in warnings)


def test_a_voice_in_the_wrong_language_is_called_out():
    warnings = providers.warnings(
        config(tts_provider="edge", language="ja", tts_voice="en-US-AvaNeural"))
    assert any("en-US-AvaNeural" in w for w in warnings)


def test_a_matching_setup_says_nothing():
    assert providers.warnings(
        config(tts_provider="edge", language="ja",
               tts_voice="ja-JP-NanamiNeural")) == ()


def test_detection_never_complains_about_a_mismatch():
    """Nothing has been asked for, so nothing can be wrong yet."""
    assert providers.warnings(
        config(tts_provider="kokoro", language="auto", kokoro_voice="af_bella")) == ()


def test_a_missing_key_is_named():
    warnings = providers.warnings(
        config(tts_provider="orpheus", orpheus_key=None, orpheus_voice="zoe"))
    assert any("orpheus_key" in w for w in warnings)


# --- kokoro's files ---------------------------------------------------------


def test_the_voice_pack_is_the_format_the_library_can_read():
    """`voices.bin` made `Kokoro()` raise, which left the engine silently mute."""
    from src.modules.tts.kokoro_tts_wrapper import normalize_voices_file

    assert normalize_voices_file("voices.bin") == "voices.json"
    assert normalize_voices_file("data/models/voices.bin") == "data/models/voices.json"


def test_a_voice_pack_that_is_already_right_is_left_alone():
    from src.modules.tts.kokoro_tts_wrapper import normalize_voices_file

    assert normalize_voices_file("voices.json") == "voices.json"
    assert normalize_voices_file("/somewhere/mine.json") == "/somewhere/mine.json"
    assert normalize_voices_file("") == "voices.json"


def test_a_fresh_config_asks_for_a_voice_pack_that_works():
    assert BrainConfig().kokoro_voices_file == "voices.json"


def test_each_file_is_fetched_under_its_own_name(monkeypatch, tmp_path):
    """The url used to be a constant, so every path got `voices.bin` content."""
    from src.modules.tts import kokoro_tts_wrapper

    asked = []
    monkeypatch.setattr(kokoro_tts_wrapper.KokoroTTSWrapper, "_download_file",
                        lambda self, url, filename: asked.append((url, filename)))
    monkeypatch.setattr(kokoro_tts_wrapper.KokoroTTSWrapper, "_initialize_model",
                        lambda self: None)

    kokoro_tts_wrapper.KokoroTTSWrapper(model_path="kokoro-v0_19.onnx",
                                        voices_path="voices.json")

    assert [url.rsplit("/", 1)[-1] for url, _ in asked] == \
        ["kokoro-v0_19.onnx", "voices.json"]


def test_a_download_that_dies_half_way_leaves_nothing_behind(monkeypatch, tmp_path):
    """A truncated file passed `os.path.exists` and was never fetched again."""
    import pytest
    import requests

    from src.modules.tts import kokoro_tts_wrapper

    target = tmp_path / "voices.json"

    class Dying:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size=None):
            yield b"half a file"
            raise OSError("connection reset")

    monkeypatch.setattr(requests, "get", lambda *a, **k: Dying())
    wrapper = kokoro_tts_wrapper.KokoroTTSWrapper.__new__(
        kokoro_tts_wrapper.KokoroTTSWrapper)

    with pytest.raises(OSError):
        wrapper._download_file("https://example/voices.json", str(target))

    assert not target.exists()
    assert not (tmp_path / "voices.json.part").exists()


def test_the_old_binary_pack_under_the_new_name_is_thrown_away(tmp_path):
    """Renaming the file left every existing install mute: the bytes were wrong."""
    from src.modules.tts.kokoro_tts_wrapper import discard_unreadable_voices

    target = tmp_path / "voices.json"
    target.write_bytes(b"\x93NUMPY\x01\x00v\x00")

    discard_unreadable_voices(str(target))

    assert not target.exists()


def test_a_voice_pack_that_reads_is_kept(tmp_path):
    """It is megabytes of json and downloading it again is not free."""
    from src.modules.tts.kokoro_tts_wrapper import discard_unreadable_voices

    target = tmp_path / "voices.json"
    target.write_text('\n  {"af_bella": [[0.0]]}')

    discard_unreadable_voices(str(target))

    assert target.exists()


def test_an_empty_voice_pack_is_thrown_away_too(tmp_path):
    """A download killed before the `.part` rename existed left one of these."""
    from src.modules.tts.kokoro_tts_wrapper import discard_unreadable_voices

    target = tmp_path / "voices.json"
    target.write_bytes(b"")

    discard_unreadable_voices(str(target))

    assert not target.exists()


def test_nothing_is_checked_for_a_pack_that_is_not_json(tmp_path):
    """The model itself is binary on purpose, and so is a `voices.bin` kept by hand."""
    from src.modules.tts.kokoro_tts_wrapper import discard_unreadable_voices

    target = tmp_path / "kokoro-v0_19.onnx"
    target.write_bytes(b"\x08\x07onnx")

    discard_unreadable_voices(str(target))

    assert target.exists()


def test_a_corrupt_pack_is_fetched_again_on_startup(monkeypatch, tmp_path):
    """The whole point: the engine has to recover without anyone deleting a file."""
    from src.modules.tts import kokoro_tts_wrapper

    target = tmp_path / "voices.json"
    target.write_bytes(b"\x93NUMPY\x01\x00")

    asked = []
    monkeypatch.setattr(kokoro_tts_wrapper.KokoroTTSWrapper, "_download_file",
                        lambda self, url, filename: asked.append(filename))
    monkeypatch.setattr(kokoro_tts_wrapper.KokoroTTSWrapper, "_initialize_model",
                        lambda self: None)

    kokoro_tts_wrapper.KokoroTTSWrapper(model_path=str(tmp_path / "kokoro-v0_19.onnx"),
                                        voices_path=str(target))

    assert not target.exists()
    assert str(target) in asked
