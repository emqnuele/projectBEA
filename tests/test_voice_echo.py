"""Telling her own voice, off somebody's speakers, from something they said.

The failure this exists to stop is a loop rather than a wrong line: an echo is
perceived, answered, and the answer is echoed too. Every case here is a real
transcript — what whisper actually returned when her own line was mixed into a
turn at -20 dB, edges mangled the way it mangles them.
"""

import time

from src.core.perception.bus import PerceptionBus
from src.core.skills.voice.channel import Utterance, VoiceChannel
from src.core.skills.voice.echo import is_echo
from src.core.skills.voice.surface import VoiceSurface

SAID = "I am sorry, I did not quite catch that, could you say it again"


# --- is it her ---------------------------------------------------------------


def test_her_own_line_coming_back_is_her_own_line():
    heard = "I am sorry, I did not quite catch that. Could you say it again?"
    assert is_echo(heard, [SAID])


def test_the_transcriber_mangling_the_edges_of_it_does_not_hide_it():
    assert is_echo("i'm sorry, i did not quite catch that, could you say that again", [SAID])


def test_what_somebody_actually_said_is_not_her():
    assert not is_echo("Secondo me questa cosa non funziona per niente bene", [SAID])
    assert not is_echo("no, non intendevo quello, intendevo l'altra cosa", [SAID])


def test_a_turn_that_is_her_echo_plus_a_real_sentence_is_kept():
    """Half of it is hers, but the other half is the only record of what he said."""
    heard = ("I am sorry, I did not quite catch that. Could you say it again? "
             "Secondo me questa cosa non funziona per niente bene")
    assert not is_echo(heard, [SAID])


def test_a_short_answer_is_never_mistaken_for_her():
    """She says "sì" and so does everybody else; dropping a real one costs the turn."""
    for short in ("sì", "ok", "sorry", "aspetta"):
        assert not is_echo(short, [SAID, "sì", "ok", "sorry", "aspetta"])


def test_nothing_recent_means_nothing_to_have_echoed():
    assert not is_echo("I am sorry, I did not quite catch that", [])


def test_a_script_without_spaces_is_compared_the_same_way():
    said = "ごめんなさい、よく聞こえませんでした"
    assert is_echo("ごめんなさい よく聞こえませんでした", [said])
    assert not is_echo("今日はいい天気ですね、どこかに行きますか", [said])


# --- what the call remembers saying ------------------------------------------


def _channel(*utterances: Utterance) -> VoiceChannel:
    channel = VoiceChannel()
    for utterance in utterances:
        channel._track(utterance)
    return channel


def test_only_what_she_said_recently_counts_as_something_to_echo():
    now = time.monotonic()
    channel = _channel(Utterance(id="old", text=SAID, at=now - 600),
                       Utterance(id="new", text="come stai", at=now))
    assert channel.recent_texts() == ["come stai"]


def test_a_line_arriving_in_pieces_is_remembered_whole():
    import asyncio

    channel = VoiceChannel()
    pcm = b"\x00\x00" * 480
    asyncio.run(channel.play(pcm, utterance_id="u", text="allora"))
    asyncio.run(channel.play(pcm, utterance_id="u", text="allora, senti una cosa"))
    assert channel.recent_texts() == ["allora, senti una cosa"]


# --- and what the call does about it -----------------------------------------


def _surface() -> VoiceSurface:
    class Cfg:
        skills = {"discord": {"enabled": True}}
        attention = {}

    surface = VoiceSurface(Cfg(), bus=PerceptionBus(window=0.0), expression=None)
    surface.initialize()
    surface.active = True
    return surface


def test_her_own_voice_never_becomes_something_somebody_said():
    surface = _surface()
    surface.channel._track(Utterance(id="u", text=SAID))

    heard = surface.perceive("I am sorry, I did not quite catch that. Could you "
                             "say it again?", "Ema", user_id="1")
    assert heard is None, "she answered herself, which is how the loop starts"


def test_somebody_talking_over_her_is_still_heard():
    surface = _surface()
    surface.channel._track(Utterance(id="u", text=SAID))

    heard = surface.perceive("no aspetta, volevo dire un'altra cosa", "Ema", user_id="1")
    assert heard is not None
    assert "un'altra cosa" in heard.content
