"""Speaking in pieces: the room hears the first sentence while the rest is made.

The cheapest latency win in the whole voice path, and the one with the most ways
to go subtly wrong — a seam in the middle of a number, a piece too small to be
worth a synthesis, a barge-in that keeps paying for words nobody will hear.
"""

import numpy as np
import pytest

from src.core.expression.chunking import SpeechChunker, split_for_speech
from src.core.expression.pcm import duration_ms
from src.core.expression.voice import Expression
from src.core.skills.voice.channel import VoiceChannel, unframe
from src.interfaces.base_interfaces import TTSInterface
from tests.fakes import FakeAvatar, FakeCaption

# --- where a line gets cut ---------------------------------------------------


def test_a_turn_of_several_sentences_is_cut_between_them():
    pieces = split_for_speech(
        "Ma tu guarda questa cosa. Non ci posso credere davvero. "
        "Comunque va bene così, tanto lo sapevo."
    )
    assert pieces == [
        "Ma tu guarda questa cosa.",
        "Non ci posso credere davvero.",
        "Comunque va bene così, tanto lo sapevo.",
    ]


def test_a_decimal_number_is_not_a_sentence_boundary():
    assert split_for_speech("il ping sta a 3.14 ms e non scende mai sotto") == [
        "il ping sta a 3.14 ms e non scende mai sotto"
    ]


def test_a_piece_too_short_to_be_worth_a_round_trip_joins_the_next():
    """'Ok.' on its own costs a whole synthesis and buys nothing."""
    assert split_for_speech("Ok. Allora facciamo come dici tu, tanto è uguale.") == [
        "Ok. Allora facciamo come dici tu, tanto è uguale."
    ]


def test_a_trailing_scrap_joins_the_piece_before_it():
    pieces = split_for_speech("Questa cosa non ha alcun senso per me. Boh.")
    assert pieces == ["Questa cosa non ha alcun senso per me. Boh."]


def test_a_breathless_line_is_cut_at_a_comma_rather_than_never():
    line = ("allora ti spiego per bene come stanno le cose, " * 8).strip()
    pieces = split_for_speech(line)

    assert len(pieces) > 1
    assert all(len(p) <= 240 for p in pieces)
    # the seams land on commas, where a person would breathe
    assert all(p.endswith(",") for p in pieces[:-1])


def test_newlines_are_boundaries_too():
    assert split_for_speech("la prima cosa importante\nla seconda cosa importante") == [
        "la prima cosa importante", "la seconda cosa importante",
    ]


def test_nothing_to_say_produces_nothing_to_synthesise():
    assert split_for_speech("   ") == []


def test_the_pieces_always_add_back_up_to_the_line():
    line = "Guarda che non è vero! Davvero, te lo giuro. Poi fai come vuoi."
    assert " ".join(split_for_speech(line)) == line


def test_a_closing_quote_stays_with_the_sentence_it_closes():
    """A lone `"` stranded on the next piece is how a seam becomes audible."""
    pieces = split_for_speech('Mi ha detto "va bene così." Poi se ne è andato senza salutare.')
    assert pieces == ['Mi ha detto "va bene così."', "Poi se ne è andato senza salutare."]


# --- cutting a line that is still being written ------------------------------


def drip(text: str, size: int = 4) -> list:
    """Feed a line to the chunker the way a model writes it."""
    chunker = SpeechChunker()
    pieces = []
    for start in range(0, len(text), size):
        pieces += chunker.push(text[start:start + size])
    return pieces + chunker.flush()


def test_the_first_sentence_leaves_before_the_rest_of_the_line_exists():
    """The whole reason any of this exists."""
    chunker = SpeechChunker()
    assert chunker.push("Ma tu guarda questa cosa. ") == ["Ma tu guarda questa cosa."]


def test_the_first_piece_goes_earlier_than_the_ones_behind_it():
    """Nothing is waiting on piece four; the room is waiting on piece one."""
    chunker = SpeechChunker()
    assert chunker.push("Ah davvero? ") == ["Ah davvero?"]
    # the same length, later in the line, is not worth a round trip of its own
    assert chunker.push("Ma dai. ") == []


def test_a_line_cut_while_it_arrives_says_the_same_words_as_one_cut_whole():
    line = ("Ma tu guarda questa cosa. Non ci posso credere davvero. "
            "Comunque va bene così, tanto lo sapevo.")
    assert " ".join(drip(line)) == line


def test_a_direction_is_never_cut_in_half():
    chunker = SpeechChunker()
    assert chunker.push("Ma tu guarda questa cosa. <mood:sm") == ["Ma tu guarda questa cosa."]
    assert chunker.push("ug> e adesso che si fa, secondo te?") == []
    assert chunker.flush() == ["<mood:smug> e adesso che si fa, secondo te?"]


def test_direction_does_not_count_towards_being_worth_a_round_trip():
    """Otherwise three tags and two words would go out as their own synthesis."""
    chunker = SpeechChunker()
    assert chunker.push("<mood:extremely pleased with herself><do:shrug>Ok. ") == []


def test_a_breathless_stream_is_cut_at_a_comma_rather_than_never():
    line = ("allora ti spiego per bene come stanno le cose, " * 8).strip()
    pieces = drip(line)

    assert len(pieces) > 1
    assert all(p.endswith(",") for p in pieces[:-1])
    assert " ".join(pieces) == line


def test_nothing_arrives_until_there_is_a_whole_thought_to_say():
    chunker = SpeechChunker()
    assert chunker.push("Ma tu guarda") == []
    assert chunker.push(" questa cosa") == []


def test_a_full_stop_at_the_edge_of_the_stream_may_still_be_a_decimal_point():
    """"Il ping sta a 3." is not a sentence; the next delta says so."""
    chunker = SpeechChunker()
    assert chunker.push("Il ping sta a 3.") == []
    assert chunker.push("14 e non scende. ") == ["Il ping sta a 3.14 e non scende."]


# --- the engine contract -----------------------------------------------------


class OneShotTTS(TTSInterface):
    """An engine that only knows how to render a whole line, like most of them."""

    def __init__(self):
        self.rendered = []

    async def generate_audio(self, text, prosody=None):
        self.rendered.append(text)
        return np.zeros(2400, dtype=np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass


class ChunkedTTS(OneShotTTS):
    """An engine whose source is already chunked, the way Orpheus's really is."""

    async def generate_stream(self, text, prosody=None):
        self.rendered.append(text)
        for _ in range(3):
            yield np.zeros(800, dtype=np.float32), 24000


class Events:
    def publish(self, *a, **k):
        pass


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


def expression(tts) -> Expression:
    e = Expression(Config(), tts, FakeAvatar(), FakeCaption(), Events())
    return e


def live_channel():
    class Socket:
        def __init__(self):
            self.binary = []
            self.text = []

        async def send_bytes(self, data):
            self.binary.append(data)

        async def send_text(self, data):
            self.text.append(data)

    channel, socket = VoiceChannel(), Socket()
    channel.attach(socket)
    channel.on_message({"type": "joined", "channel_id": "c1", "listeners": 1})
    return channel, socket


async def test_an_engine_that_only_renders_whole_lines_still_streams_by_sentence():
    """No engine had to change for this to work."""
    tts = OneShotTTS()
    e = expression(tts)
    channel, socket = live_channel()
    e.set_call(channel)

    await e.speak("neutral", "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga.",
                  route="call")

    assert tts.rendered == ["Prima frase, abbastanza lunga.", "Seconda frase, altrettanto lunga."]
    # two chunks of audio plus the frame that closes the utterance
    headers = [unframe(f)[0] for f in socket.binary]
    assert [h["seq"] for h in headers] == [0, 1, -1]
    assert [h["last"] for h in headers] == [False, False, True]


async def test_an_engine_with_a_chunked_source_sends_sooner_still():
    tts = ChunkedTTS()
    e = expression(tts)
    channel, socket = live_channel()
    e.set_call(channel)

    await e.speak("neutral", "Una frase sola ma abbastanza lunga da contare.", route="call")

    # three pieces of one sentence, then the close
    assert len(socket.binary) == 4
    assert unframe(socket.binary[-1])[0]["last"] is True


async def test_the_whole_line_is_what_the_room_ends_up_hearing():
    e = expression(OneShotTTS())
    channel, socket = live_channel()
    e.set_call(channel)

    await e.speak("neutral", "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga.",
                  route="call")

    played = b"".join(unframe(f)[1] for f in socket.binary)
    assert duration_ms(played) == pytest.approx(200, abs=5)


async def test_a_barge_in_stops_her_paying_for_words_nobody_will_hear():
    """Interruption lands while the later sentences are still being synthesised."""

    class Interrupting(OneShotTTS):
        def __init__(self, channel_getter):
            super().__init__()
            self.channel_getter = channel_getter

        async def generate_audio(self, text, prosody=None):
            self.rendered.append(text)
            channel = self.channel_getter()
            # the first piece is already playing when someone talks over her
            if len(self.rendered) == 2 and channel.current is not None:
                channel.on_message({"type": "playback", "utterance_id": channel.current.id,
                                    "played_ms": 120, "state": "stopped"})
            return np.zeros(2400, dtype=np.float32), 24000

    holder = {}
    tts = Interrupting(lambda: holder["channel"])
    e = expression(tts)
    channel, _ = live_channel()
    holder["channel"] = channel
    e.set_call(channel)

    await e.speak("neutral", "Prima frase, abbastanza lunga. Seconda frase, altrettanto lunga. "
                            "Terza frase, ancora lunga assai.", route="call")

    # the third was never synthesised: nobody was going to hear it
    assert tts.rendered == ["Prima frase, abbastanza lunga.", "Seconda frase, altrettanto lunga."]


async def test_with_no_call_nothing_is_synthesised_for_one():
    tts = OneShotTTS()
    e = expression(tts)
    assert await e.speak("neutral", "ciao a tutti quanti voi", route="call") is None
    assert tts.rendered == []
