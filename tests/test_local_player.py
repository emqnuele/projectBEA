"""Her voice on this machine keeps time with the speaker, never with a timer.

The fake device plays in real time: a small ring drained by the clock, plus the
latency its entry declares, the way a bluetooth headset adds a fifth of a
second after the ring. Every test here is about something the room would hear:
a hole between sentences, the end of one cut off, a face changing early, a stop
that takes too long, or the engine freezing while the device opens.
"""

import asyncio
import time

import numpy as np
import pytest

from src.core.expression.player import FIRST_FORMAT, LocalPlayer, candidates, resolve, selector_of

RATE = 24000


def tone(seconds: float) -> np.ndarray:
    return np.full(int(RATE * seconds), 0.1, dtype=np.float32)


def devices(*entries):
    """Output devices as `output_devices()` lists them."""
    return [{"id": i, "name": name, "channels": 2, "latency_ms": 0, "default": default}
            for i, (name, default) in enumerate(entries)]


@pytest.fixture
def card(silent_audio):
    """The fake sound card, with a slow output and a quick one."""
    silent_audio.devices.clear()
    silent_audio.output("MacBook Speakers", latency=0.015)
    silent_audio.output("CMF Buds 2", latency=0.2)
    silent_audio.default.device = (0, 0)
    return silent_audio


def player(card, selector=None, **kwargs) -> LocalPlayer:
    return LocalPlayer(backend=card, selector=selector, **kwargs)


# --- choosing the output ---------------------------------------------------------


def test_a_device_is_found_by_its_name_whatever_position_it_moved_to():
    listed = devices(("MSI G242", False), ("CMF Buds 2", True), ("MacBook Speakers", False))
    assert resolve("CMF Buds 2", listed)["id"] == 1
    assert resolve("cmf buds 2", listed)["id"] == 1


def test_a_name_cut_short_by_the_oldest_windows_api_still_matches():
    listed = devices(("Speakers (Realtek(R) Audio)", True), ("CABLE Input (VB-Audio Virtual C", False))
    assert resolve("CABLE Input (VB-Audio Virtual Cable)", listed)["id"] == 1


def test_a_short_name_is_not_mistaken_for_the_start_of_another():
    listed = devices(("Speakers", True), ("Headphones", False))
    assert resolve("Speakers (USB Audio)", listed) is None


def test_nothing_chosen_follows_the_system_default():
    listed = devices(("MSI G242", False), ("CMF Buds 2", True))
    assert resolve(None, listed)["name"] == "CMF Buds 2"


def test_a_device_that_is_not_plugged_in_falls_back_to_the_default_first():
    listed = devices(("MSI G242", False), ("CMF Buds 2", True))
    assert resolve("AirPods", listed) is None
    assert [d["name"] for d in candidates("AirPods", listed)] == ["CMF Buds 2", "MSI G242"]


def test_the_config_names_a_device_and_an_old_position_only_counts_without_one():
    class Config:
        audio_device = ""
        audio_device_id = None

    config = Config()
    assert selector_of(config) is None
    config.audio_device_id = 2
    assert selector_of(config) == 2
    config.audio_device = "CMF Buds 2"
    assert selector_of(config) == "CMF Buds 2"


async def test_she_speaks_on_the_device_she_is_given_by_name(card):
    p = player(card, "CMF Buds 2")
    await p.play(tone(0.05), RATE)
    await p.drained()
    assert card.streams[-1].device == 1
    p.close()


async def test_a_device_that_refuses_to_open_hands_over_to_the_next(card):
    """A bluetooth headset switched to headset mode refuses; she still speaks."""
    card.refuse.add("CMF Buds 2")
    p = player(card, "CMF Buds 2")
    await p.play(tone(0.05), RATE)
    await p.drained()
    assert p.device_name == "MacBook Speakers"
    p.close()


async def test_portaudio_relists_the_devices_every_time_the_stream_opens(card):
    """A headset plugged in after she started is only visible to a restarted portaudio."""
    p = player(card)
    await p.play(tone(0.05), RATE)
    await p.drained()
    assert card.restarts == 1
    p.close()


async def test_choosing_another_device_moves_her_at_the_next_piece_not_mid_word(card):
    p = player(card, "MacBook Speakers")
    await p.play(tone(0.05), RATE)
    await p.drained()
    p.configure(selector="CMF Buds 2")
    await p.play(tone(0.05), RATE)
    await p.drained()
    assert [s.device for s in card.streams] == [0, 1]
    assert card.streams[0].closed
    p.close()


async def test_no_device_at_all_still_takes_as_long_as_the_line(card, caplog):
    """Everything timed on her voice holds even on a box with no sound card."""
    card.devices.clear()
    p = player(card)
    started = time.monotonic()
    await p.play(tone(0.2), RATE)
    await p.drained()
    assert time.monotonic() - started >= 0.15
    assert "no usable audio output" in caplog.text
    p.close()


# --- keeping time ----------------------------------------------------------------


async def test_the_sentences_of_a_line_play_back_to_back_without_a_hole(card):
    # a hole here would come from the design, not from a runner pausing for a few hundred ms
    card.capacity_ms = 500
    p = player(card, "CMF Buds 2", buffer_ms=400)
    for seconds in (0.15, 0.1, 0.2):
        await p.play(tone(seconds), RATE)
    await p.drained()
    stream = card.streams[-1]
    assert stream.underflows == 0, "the room heard silence between two sentences"
    assert sum(stream.written) == int(RATE * 0.15) + int(RATE * 0.1) + int(RATE * 0.2)
    p.close()


async def test_a_busy_moment_on_the_loop_between_two_sentences_leaves_no_hole(card):
    """The next sentence is asked for while a buffer's worth of this one is still to be written."""
    card.capacity_ms = 500
    p = player(card, "MacBook Speakers", buffer_ms=250)
    await p.play(tone(0.8), RATE)
    # busier than one buffer, less than the two the early handover leaves
    time.sleep(0.35)
    await p.play(tone(0.1), RATE)
    await p.drained()
    assert card.streams[-1].underflows == 0
    p.close()


async def test_the_end_of_a_line_is_when_the_room_hears_it_end(card):
    """Not when the timer says: a fifth of a second of it is still in the headset."""
    p = player(card, "CMF Buds 2")
    started = time.monotonic()
    await p.play(tone(0.3), RATE)
    await p.drained()
    assert time.monotonic() - started >= 0.3 + 0.2 - 0.03
    p.close()


async def test_each_sentence_is_heard_when_it_reaches_the_speaker_and_in_order(card):
    p = player(card, "CMF Buds 2")
    p.prepare()
    await asyncio.sleep(0.05)
    started = time.monotonic()
    heard = []
    for seconds in (0.2, 0.15):
        await p.play(tone(seconds), RATE, on_heard=lambda: heard.append(time.monotonic() - started))
    await p.drained()
    assert len(heard) == 2
    assert heard[0] == pytest.approx(0.2, abs=0.06), "the first sentence waits for the device's latency"
    assert heard[1] - heard[0] == pytest.approx(0.2, abs=0.06), "the second starts where the first ends"
    p.close()


async def test_something_marked_between_two_sentences_happens_between_them(card):
    p = player(card, "CMF Buds 2")
    order = []
    await p.play(tone(0.1), RATE, on_heard=lambda: order.append("first"))
    p.mark(lambda: order.append("face"))
    await p.play(tone(0.1), RATE, on_heard=lambda: order.append("second"))
    await p.drained()
    assert order == ["first", "face", "second"]
    p.close()


async def test_a_line_opens_the_stream_before_its_first_sentence_exists(card):
    p = player(card)
    p.prepare()
    await asyncio.sleep(0.05)
    assert len(card.streams) == 1
    assert card.streams[0].samplerate == FIRST_FORMAT[0]
    p.close()


async def test_a_different_rate_reopens_the_stream_after_the_audio_before_it(card):
    p = player(card)
    await p.play(tone(0.05), RATE)
    await p.play(np.zeros(4410, dtype=np.float32), 44100)
    await p.drained()
    assert [s.samplerate for s in card.streams] == [RATE, 44100]
    assert sum(card.streams[0].written) == int(RATE * 0.05), "the first stream was closed before its audio ran out"
    p.close()


# --- never in the way ------------------------------------------------------------


async def test_a_slow_device_never_stops_the_event_loop(card):
    """Opening a bluetooth stream takes tens of ms; the brain, the call and the dashboard share this loop."""
    card.open_delay = 0.3
    p = player(card)
    stalls = []
    running = True

    async def ticker():
        last = time.perf_counter()
        while running:
            await asyncio.sleep(0.005)
            now = time.perf_counter()
            stalls.append(now - last)
            last = now

    watcher = asyncio.create_task(ticker())
    p.prepare()
    await p.play(tone(0.1), RATE)
    await p.drained()
    running = False
    await watcher
    assert max(stalls) < 0.1
    p.close()


async def test_a_stop_is_heard_within_the_buffer_and_nothing_queued_after_it_plays(card):
    p = player(card, "MacBook Speakers", buffer_ms=40)
    first = asyncio.create_task(p.play(tone(2.0), RATE))
    await asyncio.sleep(0.1)
    stopped = time.monotonic()
    first.cancel()
    await asyncio.gather(first, return_exceptions=True)
    await p.drained()
    assert time.monotonic() - stopped < 0.2
    written = sum(card.streams[-1].written)
    assert written < RATE * 0.4, "the rest of the sentence kept going after the stop"
    p.close()


async def test_a_flush_wakes_everyone_waiting_on_audio_that_will_not_play(card):
    p = player(card)
    waiting = asyncio.create_task(p.play(tone(1.0), RATE))
    ending = asyncio.create_task(p.drained())
    await asyncio.sleep(0.05)
    p.flush()
    await asyncio.wait_for(asyncio.gather(waiting, ending), timeout=1)
    p.close()


async def test_a_device_that_goes_away_mid_sentence_is_reopened_and_the_sentence_goes_on(card):
    p = player(card)
    await p.play(tone(0.05), RATE)
    stream = card.streams[-1]

    def unplugged(data):
        raise OSError("device unavailable")

    stream.write = unplugged
    await p.play(tone(0.1), RATE)
    await p.drained()
    assert len(card.streams) == 2
    assert sum(card.streams[1].written) > 0
    p.close()


async def test_an_idle_stream_lets_the_device_go_and_the_writer_leaves(card):
    p = player(card, idle_close_s=0.1)
    await p.play(tone(0.05), RATE)
    await p.drained()
    await asyncio.sleep(0.4)
    assert card.streams[-1].closed
    assert p._thread is None
    # and the next line simply starts again
    await p.play(tone(0.05), RATE)
    await p.drained()
    assert len(card.streams) == 2
    p.close()


async def test_closing_lets_go_of_the_device_quickly(card):
    p = player(card)
    asyncio.create_task(p.play(tone(2.0), RATE))
    await asyncio.sleep(0.05)
    started = time.monotonic()
    p.close()
    assert time.monotonic() - started < 0.6
    assert card.streams[-1].closed


async def test_portaudio_keeps_its_quickest_latency_unless_a_bigger_buffer_is_asked_for(card):
    quick = player(card)
    await quick.play(tone(0.02), RATE)
    await quick.drained()
    quick.close()
    roomy = player(card, latency_s=0.1)
    await roomy.play(tone(0.02), RATE)
    await roomy.drained()
    roomy.close()
    assert [s.latency_asked for s in card.streams] == [None, 0.1]


async def test_integer_samples_are_played_at_the_right_loudness(card):
    p = player(card)
    await p.play(np.full(2400, 16384, dtype=np.int16), RATE)
    await p.drained()
    assert sum(card.streams[-1].written) == 2400
    assert card.streams[-1].peak == pytest.approx(0.5)
    p.close()


# --- a busy engine ---------------------------------------------------------------


def portaudio_hands_back_late(monkeypatch, by: float):
    """Every call into the device returns `by` late: the gil it let go of is busy elsewhere."""
    from tests.fakes import FakeOutputStream

    available, write = FakeOutputStream.write_available.fget, FakeOutputStream.write

    def late_available(self):
        time.sleep(by)
        return available(self)

    def late_write(self, data):
        time.sleep(by)
        return write(self, data)

    monkeypatch.setattr(FakeOutputStream, "write_available", property(late_available))
    monkeypatch.setattr(FakeOutputStream, "write", late_write)


async def test_a_writer_held_up_by_a_busy_engine_catches_up_and_leaves_no_hole(card, monkeypatch):
    """Two calls a write, each late by most of a chunk: a chunk per write would fall behind the speaker."""
    card.capacity_ms = 120
    portaudio_hands_back_late(monkeypatch, 0.008)
    p = player(card, "MacBook Speakers", buffer_ms=120)
    await p.play(tone(0.6), RATE)
    await p.drained()
    assert card.streams[-1].underflows == 0, "the room heard holes while the writer was held up"
    assert p.starved == 0
    p.close()


async def test_holes_in_her_voice_are_logged_once_for_a_busy_stretch(card, monkeypatch, caplog):
    """Heard in a recording hours later: the log is the only place that can say why."""
    card.capacity_ms = 40
    portaudio_hands_back_late(monkeypatch, 0.05)
    p = player(card, "MacBook Speakers", buffer_ms=40)
    with caplog.at_level("WARNING", logger="bea.expression.player"):
        await p.play(tone(0.4), RATE)
        await p.play(tone(0.4), RATE)
        await p.drained()
    assert p.starved > 0
    assert caplog.text.count("her voice skipped") == 1
    p.close()
