"""A line spoken on this machine is timed by the speaker, and the output is chosen by name.

`test_local_player.py` pins the player itself; this is what the rest of her
sees of it: when she stops counting as speaking, what a barge-in costs, when a
sentence's words and mouth appear, and how the doctor, the dashboard and the
command line pick the output.
"""

import asyncio
import time

import numpy as np
import pytest

from src.core.config import BrainConfig
from src.core.config_write import apply_config
from src.core.expression.player import CHUNK_MS, FADE_MS
from src.core.expression.voice import Expression
from src.interfaces.base_interfaces import TTSInterface
from src.setup import doctor
from tests.fakes import FakeCaption

RATE = 24000


class Config:
    text_font_size = 40
    text_line_width = 30
    text_lines = 3
    text_min_font_size = 20
    text_font_step = 2
    typing_delay = 0.0
    text_min_duration = 0.0
    obs_text_source = ""
    obs_source_type = "image"
    audio_device = "CMF Buds 2"
    audio_device_id = None
    audio_buffer_ms = 100
    audio_idle_close_s = 30.0


class Events:
    def publish(self, *a, **k):
        pass


class Speech(TTSInterface):
    def __init__(self, seconds=0.2):
        self.seconds = seconds

    async def generate_audio(self, text, prosody=None):
        return np.full(int(RATE * self.seconds), 0.1, dtype=np.float32), RATE

    def reload_config(self, config):
        pass


class Avatar:
    def __init__(self):
        self.log = []

    def show(self, mood, state):
        self.log.append(("show", state, time.monotonic()))

    def perform(self, clip):
        pass

    def mouth(self, envelope, fps):
        self.log.append(("mouth", len(envelope), time.monotonic()))

    def reload_config(self, config):
        pass

    def close(self):
        pass


@pytest.fixture
def card(silent_audio):
    silent_audio.devices.clear()
    silent_audio.output("MacBook Speakers", latency=0.015)
    silent_audio.output("CMF Buds 2", latency=0.2)
    return silent_audio


def expression(seconds=0.2, config=None):
    avatar = Avatar()
    caption = FakeCaption()
    e = Expression(config or Config(), Speech(seconds), avatar, caption, Events())
    e.player._sd = None
    return e, avatar, caption


async def test_she_counts_as_speaking_until_the_room_hears_the_end(card):
    """Barge-in reads this: ending it on a timer let the last fifth of a second go unguarded."""
    e, avatar, _ = expression(0.3)
    started = time.monotonic()
    await e.speak("neutral", "Una frase abbastanza lunga.")
    assert time.monotonic() - started >= 0.3 + 0.2 - 0.03
    assert e.is_speaking is False
    e.close()


async def test_the_mouth_starts_when_the_sentence_reaches_the_speaker(card):
    e, avatar, _ = expression(0.2)
    started = time.monotonic()
    await e.speak("neutral", "Una frase abbastanza lunga.")
    mouth = next(at for kind, _, at in avatar.log if kind == "mouth")
    assert mouth - started >= 0.2 - 0.03, "the mouth ran ahead of the headset"
    e.close()


async def test_a_sentence_written_as_it_goes_is_captioned_when_it_is_heard(card):
    e, _, caption = expression(0.2)
    line = e.open_line("neutral")
    line.say("Prima frase abbastanza lunga. ")
    line.say("Seconda frase abbastanza lunga.")
    await line.close()
    assert caption.said == ["Prima frase abbastanza lunga.", "Seconda frase abbastanza lunga."]
    e.close()


async def test_a_barge_in_never_waits_on_the_sound_card(card):
    e, avatar, _ = expression(2.0)
    speaking = asyncio.create_task(e.speak("neutral", "Una frase lunghissima che non finisce mai."))
    await asyncio.sleep(0.3)
    started = time.monotonic()
    await e.interrupt()
    # the old sd.stop() held the loop 111-146 ms; a shared ci runner gets some room under that
    assert time.monotonic() - started < 0.1
    assert e.is_speaking is False
    await asyncio.wait_for(speaking, timeout=1)
    written = sum(card.streams[-1].written)
    await asyncio.sleep(0.3)
    # at most the chunk already on its way and the fade that ends it
    tail = RATE * (CHUNK_MS + FADE_MS) // 1000
    assert sum(card.streams[-1].written) - written <= tail, "she kept talking after being stopped"
    e.close()


async def test_choosing_another_output_moves_her_voice(card):
    e, _, _ = expression(0.05)
    await e.speak("neutral", "Una frase.")
    config = Config()
    config.audio_device = "MacBook Speakers"
    e.reload_config(config)
    await e.speak("neutral", "Un'altra frase.")
    assert [s.device for s in card.streams] == [1, 0]
    e.close()


async def test_shutting_down_lets_go_of_the_sound_card(card):
    e, _, _ = expression(0.05)
    await e.speak("neutral", "Una frase.")
    e.close()
    assert card.streams[-1].closed


# --- opening the output before she speaks ----------------------------------------


async def test_a_turn_opens_the_sound_card_while_the_model_is_still_thinking(card):
    """A quiet bluetooth output took 180-456 ms to open; the model's own latency hides it."""
    from tests.fakes import StreamingLLMClient, speaks
    from tests.test_speaking_early import build, one_turn, said_to

    mind, bus = build(StreamingLLMClient([speaks("Ciao.")]))
    bus.put(said_to(mind))
    await one_turn(mind, bus)
    assert mind.expression.warm_ups == 1


async def test_her_mind_wandering_does_not_wake_the_sound_card():
    from src.core.perception.types import Perception, PerceptionKind
    from tests.fakes import StreamingLLMClient, stays_silent
    from tests.test_speaking_early import build, one_turn

    mind, bus = build(StreamingLLMClient([stays_silent()]))
    bus.put(Perception(PerceptionKind.IDLE, "idle", "nothing happening", salience=0.5))
    await one_turn(mind, bus)
    assert mind.llm.calls, "no turn ran, so this proved nothing"
    assert mind.expression.warm_ups == 0


async def test_warming_up_opens_the_stream_before_the_first_word(card):
    e, _, _ = expression()
    e.warm_up()
    await asyncio.sleep(0.05)
    assert len(card.streams) == 1
    e.close()


async def test_warming_up_leaves_the_sound_card_alone_during_a_call(card):
    class Call:
        live = True
        current = None

    e, _, _ = expression()
    e.set_call(Call())
    e.warm_up()
    await asyncio.sleep(0.05)
    assert card.streams == []
    e.close()


# --- picking the output ----------------------------------------------------------


async def test_the_doctor_passes_an_output_chosen_by_name(card):
    finding = await doctor.check_speakers(_config(audio_device="CMF Buds 2"))
    assert finding.ok
    assert "CMF Buds 2" in finding.detail and "200 ms" in finding.detail


async def test_the_doctor_warns_about_an_output_picked_by_position(card):
    finding = await doctor.check_speakers(_config(audio_device="", audio_device_id=1))
    assert not finding.ok and not finding.blocking
    assert "position" in finding.detail and "audio_device" in finding.fix


async def test_the_doctor_warns_about_an_output_that_is_not_plugged_in(card):
    finding = await doctor.check_speakers(_config(audio_device="AirPods"))
    assert not finding.ok and not finding.blocking
    assert "MacBook Speakers" in finding.detail


async def test_the_doctor_fails_a_machine_with_no_output(card):
    card.devices.clear()
    finding = await doctor.check_speakers(_config())
    assert not finding.ok and finding.blocking


def test_the_dashboard_lists_outputs_by_name_with_the_default_marked(card):
    from src.web.routers.settings import audio_devices
    listed = audio_devices()
    assert [d["name"] for d in listed] == ["MacBook Speakers", "CMF Buds 2"]
    assert listed[0]["default"] is True and listed[1]["latency_ms"] == 200


def test_the_dashboard_can_store_a_name_and_clear_the_old_position():
    config = BrainConfig()
    config.audio_device_id = 2
    apply_config(config, {"audio_device": "CMF Buds 2", "audio_device_id": None})
    assert config.audio_device == "CMF Buds 2" and config.audio_device_id is None


async def test_the_dashboard_dials_reach_the_player_without_a_restart(card):
    config = BrainConfig()
    apply_config(config, {"audio_buffer_ms": 150, "audio_latency_s": 0.1, "audio_idle_close_s": 60})
    assert (config.audio_buffer_ms, config.audio_latency_s, config.audio_idle_close_s) == (150, 0.1, 60)

    e, _, _ = expression(0.05)
    e.reload_config(config)
    await e.speak("neutral", "Una frase.")
    assert card.streams[-1].latency_asked == 0.1
    assert e.player._buffer_ms == 150 and e.player._idle_close_s == 60
    e.close()


def test_the_command_line_takes_the_output_by_name():
    from src import cli
    config = BrainConfig()
    cli.apply_cli_overrides(config, cli.parse_args(["--device", "CMF Buds 2"]))
    assert config.audio_device == "CMF Buds 2"


def test_the_setup_wizard_stores_the_output_by_name():
    from src.setup.config_plan import apply_answers
    config = BrainConfig()
    config.audio_device_id = 3
    apply_answers(config, {"llm_provider": "openrouter", "audio_device": "CMF Buds 2"})
    assert config.audio_device == "CMF Buds 2" and config.audio_device_id is None


def _config(**kwargs) -> BrainConfig:
    settings = BrainConfig()
    for key, value in kwargs.items():
        setattr(settings, key, value)
    return settings
