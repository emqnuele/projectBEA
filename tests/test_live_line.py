"""A line delivered while it is still being written.

Two things are worth pinning here, and they pull against each other. Sound has
to start before the line is finished, or none of this was worth doing. And every
piece of it — words, face, behaviour — has to come out in the order she wrote
it, or she ends up smiling at the end of the sentence she was angry about.
"""

import asyncio

import numpy as np

from src.core.expression.voice import Expression
from src.interfaces.base_interfaces import TTSInterface
from tests.fakes import FakeCaption


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


class Script:
    """One list, everything in it: what was said and what was shown, in order."""

    def __init__(self):
        self.entries = []

    def add(self, kind, value):
        self.entries.append((kind, value))

    def of(self, kind):
        return [v for k, v in self.entries if k == kind]


class ScriptedTTS(TTSInterface):
    def __init__(self, script: Script, fails_on: str = ""):
        self.script = script
        self.fails_on = fails_on

    async def generate_audio(self, text, prosody=None):
        if self.fails_on and self.fails_on in text:
            raise RuntimeError("the engine fell over")
        self.script.add("render", text)
        # a real buffer so playback is awaited rather than skipped
        return np.zeros(240, dtype=np.float32), 24000

    async def speak(self, text, output_device_id):
        pass

    def reload_config(self, config):
        pass


class ScriptedAvatar:
    def __init__(self, script: Script):
        self.script = script

    def show(self, mood, state):
        self.script.add("show", (mood, state))

    def perform(self, clip):
        self.script.add("perform", clip)

    def mouth(self, envelope, fps):
        pass

    def reload_config(self, config):
        pass

    def close(self):
        pass


def expression(script: Script, **kwargs) -> Expression:
    e = Expression(Config(), ScriptedTTS(script, **kwargs),
                   ScriptedAvatar(script), FakeCaption(), Events())

    # rendering deliberately runs ahead of playback, so "what was made" and
    # "what was heard" are two different orders. Ordering is about the second.
    played = e.play

    async def recording(line, item):
        script.add("play", item.beat.value)
        await played(line, item)

    e.play = recording
    return e


# --- ordering ----------------------------------------------------------------


async def test_a_local_line_is_made_a_sentence_at_a_time():
    """Not one synthesis of the whole turn: the first sentence goes on its own."""
    script = Script()
    await expression(script).speak(
        "neutral", "Ma tu guarda questa cosa. Non ci posso credere davvero.")

    assert script.of("render") == ["Ma tu guarda questa cosa.",
                                   "Non ci posso credere davvero."]


async def test_her_face_changes_on_the_word_she_wrote_it_on():
    script = Script()
    await expression(script).speak(
        "neutral",
        "Ma certo, hai proprio ragione tu. <mood:angry> Anzi no, non hai ragione affatto.")

    heard = [(k, v) for k, v in script.entries if k in ("play", "show")]
    assert heard == [
        ("show", ("neutral", "talking")),
        ("play", "Ma certo, hai proprio ragione tu."),
        ("show", ("angry", "talking")),
        ("play", "Anzi no, non hai ragione affatto."),
        ("show", ("angry", "idle")),
    ]


async def test_a_behaviour_lands_between_the_sentences_it_sits_between():
    script = Script()
    await expression(script).speak(
        "neutral", "Guarda un po' qua che roba. <do:shrug> Comunque non mi interessa niente.")

    order = [k for k, _ in script.entries if k in ("play", "perform")]
    assert order == ["play", "perform", "play"]
    assert script.of("perform") == ["shrug"]


async def test_direction_is_never_read_out_loud():
    """The one failure the audience notices."""
    script = Script()
    await expression(script).speak(
        "neutral", "<mood:angry>Ma tu guarda questa cosa qui. <do:shrug>")

    assert script.of("render") == ["Ma tu guarda questa cosa qui."]


async def test_a_word_she_invented_still_lands_on_a_face_she_has():
    script = Script()
    await expression(script).speak(
        "neutral", "Che bello vederti qui oggi. <mood:excited> Davvero, sono contenta.")

    assert ("show", ("happy", "talking")) in script.entries


async def test_the_matcher_the_brain_installs_is_the_one_that_is_used():
    """Anything the plain table misses is matched by meaning, when it can be."""
    script = Script()
    e = expression(script)
    e.set_matchers(mood=lambda word: "angry" if word == "quietly seething" else "neutral",
                   clip=lambda word: f"clip-{word}")

    await e.speak("neutral", "<mood:quietly seething>Ma tu guarda questa cosa. <do:sigh>")

    assert ("show", ("angry", "talking")) in script.entries
    assert script.of("perform") == ["clip-sigh"]


# --- starting before the end -------------------------------------------------


async def test_she_starts_speaking_before_the_line_is_finished():
    """The whole point: the first sentence is out while the rest is written."""
    script = Script()
    line = expression(script).open_line("neutral")

    line.say("Ma tu guarda questa cosa. ")
    for _ in range(8):
        await asyncio.sleep(0)

    assert script.of("render") == ["Ma tu guarda questa cosa."]

    line.say("Non ci posso credere davvero.")
    await line.close()
    assert script.of("render") == ["Ma tu guarda questa cosa.",
                                   "Non ci posso credere davvero."]


async def test_the_next_piece_is_made_while_the_current_one_is_playing():
    """Otherwise every seam costs a whole synthesis of silence."""
    script = Script()
    playing = asyncio.Event()
    released = asyncio.Event()

    e = expression(script)

    async def slow_play(audio, rate, device):
        playing.set()
        await released.wait()

    e._play_audio = slow_play

    line = e.open_line("neutral")
    line.say("Ma tu guarda questa cosa. Non ci posso credere davvero. E invece si.")
    await asyncio.wait_for(playing.wait(), timeout=1)
    for _ in range(8):
        await asyncio.sleep(0)

    # the second piece was rendered while the first had not finished playing
    assert len(script.of("render")) >= 2

    released.set()
    await line.close()


# --- when something goes wrong ------------------------------------------------


async def test_a_piece_the_engine_could_not_make_costs_only_that_piece():
    script = Script()
    e = expression(script, fails_on="Non ci posso credere")
    await e.speak("neutral",
                  "Ma tu guarda questa cosa. Non ci posso credere davvero. E invece si, guarda.")

    assert script.of("render") == ["Ma tu guarda questa cosa.", "E invece si, guarda."]


async def test_being_talked_over_stops_the_rest_of_the_line():
    script = Script()
    released = asyncio.Event()
    e = expression(script)

    async def slow_play(audio, rate, device):
        await released.wait()

    e._play_audio = slow_play

    line = e.open_line("neutral")
    line.say("Ma tu guarda questa cosa. Non ci posso credere davvero. E invece si, guarda.")
    for _ in range(8):
        await asyncio.sleep(0)

    await e.interrupt()
    released.set()
    await line.close()

    assert e.is_speaking is False
