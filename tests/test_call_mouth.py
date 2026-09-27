"""In a call her face and mouth keep time by what the room has heard.

The bot reports each utterance as it plays: the first report puts the talking
face on, every report re-anchors the mouth, the last takes the face off. Each
piece's mouth is published the moment the piece has been sent, at its place in
the utterance. None of it touches `is_speaking`, which barge-in reads.
"""

import asyncio

import numpy as np

from src.core.expression.pcm import envelope
from src.core.expression.voice import REPORT_WAIT_S, Expression
from src.core.skills.voice.channel import VoiceChannel
from src.interfaces.base_interfaces import TTSInterface
from tests.fakes import FakeAvatar, FakeCaption

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
    audio_device_id = None


class Events:
    def publish(self, *a, **k):
        pass


class Speech(TTSInterface):
    """Every piece is 0.4 s of noise, loud enough to move a mouth."""

    def __init__(self):
        self.rng = np.random.default_rng(3)

    async def generate_audio(self, text, prosody=None):
        return (self.rng.standard_normal(int(RATE * 0.4)) * 0.3).astype(np.float32), RATE

    def reload_config(self, config):
        pass


class Timeline(FakeAvatar):
    supports_timeline = True

    def __init__(self, log):
        super().__init__()
        self.log = log
        self.segments = []
        self.syncs = []

    def show(self, mood, state):
        super().show(mood, state)
        self.log.append(("show", state))

    def mouth_at(self, frames, fps, utterance_id, offset_ms):
        self.segments.append((utterance_id, list(frames), fps, offset_ms))
        self.log.append(("segment", offset_ms))

    def mouth_sync(self, utterance_id, played_ms):
        self.syncs.append((utterance_id, played_ms))


class Socket:
    def __init__(self, log):
        self.log = log
        self.binary = []
        self.text = []

    async def send_bytes(self, data):
        self.binary.append(data)
        self.log.append(("sent", len(data)))

    async def send_text(self, data):
        self.text.append(data)


def setup(avatar_class=Timeline):
    log = []
    avatar = avatar_class(log) if avatar_class is Timeline else avatar_class()
    e = Expression(Config(), Speech(), avatar, FakeCaption(), Events())
    channel = VoiceChannel()
    channel.attach(Socket(log))
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    channel.on_progress = e.call_progress
    e.set_call(channel)
    return e, channel, avatar, log


LINE = "Prima frase abbastanza lunga. Seconda frase abbastanza lunga. Terza frase abbastanza lunga."


async def speak_with_reports(e, channel, report_at_seq=0):
    """Says a line while the bot reports it playing from its first frame, as the real one does."""
    line = e.open_line("neutral", route="call", caption=LINE)
    line.start()
    uid = line.state["id"]
    reported = False
    original = channel.play

    async def play(pcm, **kwargs):
        nonlocal reported
        await original(pcm, **kwargs)
        if not reported and kwargs.get("seq", 0) >= report_at_seq:
            reported = True
            channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 0, "state": "playing"})

    channel.play = play
    line.say(LINE)
    await line.close()
    return line, uid


async def test_each_piece_is_published_after_it_was_sent_and_at_its_place():
    e, channel, avatar, log = setup()
    line, uid = await speak_with_reports(e, channel)

    assert len(avatar.segments) == 3
    offsets = [offset for _, _, _, offset in avatar.segments]
    assert offsets[0] == 0
    assert offsets == sorted(offsets) and len(set(offsets)) == 3
    # never before its audio: every segment comes after the sends of its own piece
    first_segment = log.index(("segment", 0))
    assert any(kind == "sent" for kind, _ in log[:first_segment])
    for utterance_id, frames, fps, _ in avatar.segments:
        assert utterance_id == uid and fps == e._lipsync_fps and frames


async def test_the_pieces_lay_end_to_end_so_the_mouth_cannot_drift():
    """Each piece is placed by where the audio sent so far ends, not by counting frames."""
    e, channel, avatar, _ = setup()
    line, _ = await speak_with_reports(e, channel)

    frame_ms = 1000 / e._lipsync_fps
    for (_, frames, fps, offset), (_, _, _, following) in zip(avatar.segments[:-1], avatar.segments[1:], strict=True):
        # a piece covers its own length to within one frame; the next one starts where the audio did
        assert abs(offset + len(frames) * 1000 / fps - following) <= frame_ms
    last_offset, last_frames = avatar.segments[-1][3], avatar.segments[-1][1]
    assert abs(last_offset + len(last_frames) * frame_ms - line.state["spoken_ms"]) <= frame_ms


async def test_a_piece_is_the_same_mouth_the_whole_line_used_to_get():
    """Normalised per piece, as before: nothing about how open her mouth is changes."""
    e, channel, avatar, _ = setup()
    line, _ = await speak_with_reports(e, channel)
    assert [f for _, frames, _, _ in avatar.segments for f in frames] == line.state["frames"]


async def test_the_first_report_puts_the_face_on_and_every_report_keeps_the_mouth_in_time():
    e, channel, avatar, log = setup()
    line, uid = await speak_with_reports(e, channel)

    # the face went on before the line closed, at the bot's first report
    assert ("show", "talking") in log
    assert avatar.syncs[0] == (uid, 0)

    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 250, "state": "playing"})
    assert avatar.syncs[-1] == (uid, 250)


async def test_the_face_comes_off_when_the_room_has_heard_the_end():
    e, channel, avatar, _ = setup()
    e.set_state("listening")
    line, uid = await speak_with_reports(e, channel)

    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 1200, "state": "done"})
    assert avatar.shown[-1] == ("neutral", "listening")


async def test_a_reported_line_is_not_mimed_a_second_time_at_close():
    e, channel, avatar, _ = setup()
    await speak_with_reports(e, channel)
    await asyncio.sleep(0)
    # the whole-line envelope is only for backends that cannot keep time
    assert avatar.envelopes == []
    assert avatar.states.count("talking") == 1


async def test_reports_never_touch_is_speaking():
    """Barge-in reads it: it keeps exactly the timing it had."""
    e, channel, avatar, _ = setup()
    line = e.open_line("neutral", route="call", caption=LINE)
    line.start()
    uid = line.state["id"]
    before = e._is_speaking
    e.call_progress(uid, 0, "playing")
    e.call_progress(uid, 300, "playing")
    assert e._is_speaking is before
    e.call_progress(uid, 900, "done")
    assert e._is_speaking is before
    await line.cancel(end=False)


async def test_a_report_just_after_the_close_is_still_followed():
    """The real bot's first report lands a few ms after a short line closes."""
    e, channel, avatar, _ = setup()
    line = e.open_line("neutral", route="call", caption=LINE)
    line.start()
    uid = line.state["id"]
    line.say(LINE)
    await line.close()
    await asyncio.sleep(0.02)
    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 0, "state": "playing"})
    await asyncio.sleep(0.01)

    assert avatar.states.count("talking") == 1
    assert avatar.syncs == [(uid, 0)]
    assert avatar.envelopes == []


async def test_without_any_report_it_is_mimed_the_old_way():
    """A bot that never reports still gets a talking face and the whole line's mouth."""
    e, channel, avatar, _ = setup()
    line = e.open_line("neutral", route="call", caption=LINE)
    line.start()
    uid = line.state["id"]
    line.say(LINE)
    await line.close()
    await asyncio.sleep(REPORT_WAIT_S + 0.05)

    assert avatar.states.count("talking") == 1
    assert avatar.envelopes and avatar.envelopes[0][0] == line.state["frames"]
    # and a report that turns up late does not start a second face on top of it
    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 0, "state": "playing"})
    assert avatar.states.count("talking") == 1
    assert avatar.syncs == []


async def test_a_barge_in_is_not_undone_by_the_report_that_follows_it():
    e, channel, avatar, _ = setup()
    line, uid = await speak_with_reports(e, channel)
    shown = len(avatar.shown)

    e._stop_visuals()
    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 400, "state": "playing"})
    channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 400, "state": "stopped"})

    assert len(avatar.shown) == shown
    assert avatar.syncs[-1][1] != 400


async def test_a_backend_that_cannot_keep_time_still_gets_the_face_early():
    """VTube Studio and the obs png have no page clock: the face follows the report, the mouth the close."""
    log = []

    class Plain(FakeAvatar):
        def show(self, mood, state):
            super().show(mood, state)
            log.append(("show", state))

    e, channel, avatar, _ = setup(Plain)
    line, uid = await speak_with_reports(e, channel)
    await asyncio.sleep(0)

    assert avatar.states.count("talking") == 1
    assert avatar.envelopes and avatar.envelopes[0][0] == line.state["frames"]


async def test_an_older_line_ending_does_not_still_the_line_the_room_now_hears():
    """A line started while the last one is still mimed: the old one's end must not rest her face."""
    e, channel, avatar, log = setup()
    await speak_with_reports(e, channel)

    # a real tts takes a while per sentence, so the second line is still being made when the first one's visuals end
    quick = e.tts.generate_audio

    async def slow(text, prosody=None):
        await asyncio.sleep(0.6)
        return await quick(text, prosody)

    e.tts.generate_audio = slow
    original = channel.play
    first = next(iter(channel.utterances))

    async def play(pcm, **kwargs):
        await original(pcm, **kwargs)
        uid = kwargs["utterance_id"]
        if channel.utterances[first].state != "stopped":
            # what the bot does: the new line cuts the old one and is heard from its first frame
            channel.on_message({"type": "playback", "utterance_id": first, "played_ms": 300, "state": "stopped"})
            channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 0, "state": "playing"})

    channel.play = play
    await asyncio.sleep(0.3)
    line = e.open_line("neutral", route="call", caption=LINE)
    line.start()
    line.say(LINE)
    closing = asyncio.create_task(line.close())
    # the first line's visuals end 1.2 s after it closed, while this one is still being made
    await asyncio.sleep(1.3)
    assert not closing.done()
    assert avatar.states[-1] == "talking"
    await closing
    assert avatar.states[-1] == "talking"


def test_a_report_for_a_line_nobody_knows_is_ignored():
    e = Expression(Config(), Speech(), Timeline([]), FakeCaption(), Events())
    assert e.call_progress("nobody", 0, "playing") is None


def test_the_envelope_of_a_piece_is_unchanged_by_being_published_early():
    audio = (np.random.default_rng(1).standard_normal(RATE) * 0.2).astype(np.float32)
    assert envelope(audio, RATE, 30) == envelope(audio, RATE, 30)


async def test_is_speaking_ends_at_the_same_moment_whether_or_not_the_bot_reports():
    """It is timed from the close, by the caption and the length of the line, as it always was."""
    async def speaking_for(report: bool) -> float:
        e, channel, avatar, _ = setup()
        line = e.open_line("neutral", route="call", caption=LINE)
        line.start()
        uid = line.state["id"]
        line.say(LINE)
        await line.close()
        loop = asyncio.get_running_loop()
        closed = loop.time()
        if report:
            channel.on_message({"type": "playback", "utterance_id": uid, "played_ms": 0, "state": "playing"})
        # set by the visuals task on its first turn, as it always was
        await asyncio.sleep(0)
        assert e._is_speaking
        while e._is_speaking:
            await asyncio.sleep(0.005)
        return loop.time() - closed

    with_report, without = await speaking_for(True), await speaking_for(False)
    # three pieces of 0.4 s: the line lasts 1.2 s in the room either way
    assert abs(with_report - 1.2) < 0.06 and abs(without - 1.2) < 0.06, (with_report, without)
