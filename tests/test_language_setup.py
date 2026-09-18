"""The setup and the settings agree with the engine about languages.

The wizard asked "Language" and threw the answer away — it was only a heading
over the EdgeTTS voice menu — so every install transcribed and answered in
English whatever was picked. The dashboard had its own copy of the list, which
offered `jp`, a code no transcriber has ever accepted.
"""

from src.core.config import BrainConfig
from src.core.config_write import plan_config
from src.modules.tts import providers
from src.setup.config_plan import apply_answers
from src.web.routers.settings import get_voices


def base_answers(**overrides):
    answers = {
        "llm_provider": "openrouter", "llm_model": "x", "llm_key": "k",
        "tts_provider": "edge", "skills": {},
    }
    answers.update(overrides)
    return answers


# --- the wizard keeps the answer --------------------------------------------


def test_the_language_the_wizard_asked_for_is_written_down():
    config = apply_answers(BrainConfig(), base_answers(language="it"))
    assert config.language == "it"


def test_a_language_and_its_voice_arrive_together():
    config = apply_answers(BrainConfig(), base_answers(
        language="ja", tts_voice="ja-JP-NanamiNeural"))
    assert config.language == "ja"
    assert config.tts_voice == "ja-JP-NanamiNeural"


def test_an_engine_that_needs_a_phonemiser_gets_one():
    config = apply_answers(BrainConfig(), base_answers(
        language="en", tts_provider="kokoro", kokoro_voice="af_bella"))
    assert config.kokoro_lang == "en-us"


def test_saying_nothing_about_the_language_leaves_it_alone():
    config = BrainConfig()
    config.language = "it"
    apply_answers(config, base_answers())
    assert config.language == "it"


def test_a_language_with_no_voice_chosen_still_gets_one_that_speaks_it():
    """The wizard only asks for a voice on some engines; the rest are derived."""
    config = apply_answers(BrainConfig(), base_answers(language="ja"))
    assert providers.language_of(providers.PROVIDERS["edge"], config.tts_voice) == "ja"


# --- one table, served rather than copied ------------------------------------


def test_the_dashboard_is_offered_the_same_languages_the_engine_knows():
    from src.core.language import AUTO, LANGUAGES

    served = [row["code"] for row in get_voices()["languages"]]
    assert served == [AUTO, *LANGUAGES]
    # the copy that used to live in the dashboard offered this one
    assert "jp" not in served


def test_every_served_engine_says_which_languages_it_speaks():
    for row in get_voices()["providers"]:
        declared = providers.languages(providers.PROVIDERS[row["id"]])
        assert row["languages"] == list(declared)
        assert row["voices"], row["id"]


# --- the settings warn rather than block -------------------------------------


def test_a_save_that_makes_her_mute_is_allowed_and_called_out():
    config = BrainConfig()
    config.tts_provider = "kokoro"
    plan = plan_config(config, {"language": "ja"})

    assert plan.changed["language"] == "ja"          # saved
    assert any("silent" in w for w in plan.warnings)  # and said out loud


def test_a_save_that_leaves_the_voice_behind_is_called_out():
    config = BrainConfig()
    config.tts_provider = "edge"
    config.tts_voice = "en-US-AvaNeural"
    plan = plan_config(config, {"language": "ja"})

    assert any("en-US-AvaNeural" in w for w in plan.warnings)
    assert plan.suggested == {"tts_voice": "ja-JP-NanamiNeural"}


def test_nothing_is_suggested_when_the_setup_already_agrees():
    config = BrainConfig()
    config.tts_provider = "edge"
    config.tts_voice = "ja-JP-KeitaNeural"
    plan = plan_config(config, {"language": "ja"})

    assert plan.warnings == ()
    assert plan.suggested == {}


def test_a_suggestion_is_never_applied_on_its_own():
    """Swapping a voice somebody chose is not a save they asked for."""
    config = BrainConfig()
    config.tts_voice = "en-US-AvaNeural"
    plan = plan_config(config, {"language": "it"})
    plan.apply(config)

    assert config.language == "it"
    assert config.tts_voice == "en-US-AvaNeural"


# --- the diagnostic tests the language she is set to -------------------------


def test_the_doctor_makes_her_say_something_in_her_own_language():
    """Synthesising English proved only that the engine was up."""
    from src.setup.doctor import test_line

    config = BrainConfig()
    config.language = "ja"
    assert test_line(config) == "今日はいい天気ですね"

    config.language = "it"
    assert test_line(config) == "una bella giornata"


def test_the_doctor_falls_back_to_english_when_detecting():
    from src.setup.doctor import TEST_LINE, test_line

    config = BrainConfig()
    config.language = "auto"
    assert test_line(config) == TEST_LINE
