"""Reading her words out of a tool call that has not finished arriving.

This is the piece that decides whether she starts talking a second early or a
second late, and it runs on text that is, by definition, malformed — a JSON
object with no closing brace. Every case here is a way that text can be cut.
"""

from types import SimpleNamespace

import pytest

from src.core.agent.streaming import JsonFieldStream, SpokenCall, spoken_call
from src.modules.llm.openai_compat import OpenAICompatibleClient


def drip(raw: str, field: str = "message", size: int = 1) -> str:
    stream = JsonFieldStream(field)
    return "".join(stream.push(raw[i:i + size]) for i in range(0, len(raw), size))


# --- the field ---------------------------------------------------------------


def test_the_words_arrive_before_the_object_closes():
    stream = JsonFieldStream("message")
    stream.push('{"mood": "happy", "message": "ciao a ')
    assert stream.started
    assert not stream.done


def test_a_whole_object_reads_back_exactly():
    assert drip('{"mood": "happy", "message": "ciao a tutti"}') == "ciao a tutti"


def test_it_does_not_matter_where_the_stream_is_cut():
    raw = '{"mood": "angry", "message": "ma tu guarda questa cosa"}'
    for size in (1, 2, 3, 5, 7, 13):
        assert drip(raw, size=size) == "ma tu guarda questa cosa"


def test_the_field_ends_at_its_closing_quote_and_not_before():
    stream = JsonFieldStream("message")
    stream.push('{"message": "ciao"')
    assert stream.done
    assert stream.push(', "mood": "happy"}') == ""


# --- text that looks like structure ------------------------------------------


def test_a_quote_inside_the_words_does_not_end_them():
    assert drip('{"message": "ha detto \\"va bene\\" e se ne e andato"}') == \
        'ha detto "va bene" e se ne e andato'


def test_an_escape_split_across_two_deltas_still_decodes():
    stream = JsonFieldStream("message")
    out = stream.push('{"message": "ha detto \\')
    out += stream.push('"ciao\\" e basta"}')
    assert out == 'ha detto "ciao" e basta'


def test_a_unicode_escape_split_anywhere_still_decodes():
    stream = JsonFieldStream("message")
    out = stream.push('{"message": "per\\u00')
    out += stream.push('f2 no"}')
    assert out == "però no"


def test_a_newline_escape_is_a_newline():
    assert drip('{"message": "prima riga\\nseconda riga"}') == "prima riga\nseconda riga"


def test_the_field_name_appearing_in_another_value_starts_nothing():
    assert drip('{"mood": "message", "message": "eccomi"}') == "eccomi"


def test_a_nested_object_with_the_same_key_is_not_the_field():
    assert drip('{"meta": {"message": "nope"}, "message": "eccomi"}') == "eccomi"


def test_a_field_that_never_appears_yields_nothing():
    assert drip('{"mood": "happy", "reason": "niente da dire"}') == ""


def test_a_braceless_fragment_yields_nothing_rather_than_guessing():
    assert drip('"message": "eccomi"') == ""


# --- the two fields of a speak call ------------------------------------------


def test_the_words_wait_for_a_mood_to_say_them_in():
    call = SpokenCall()
    assert call.push('{"mood": "ang') == ""
    assert not call.ready

    out = call.push('ry", "message": "ma tu guarda"')
    assert call.ready
    assert call.mood == "angry"
    assert out == "ma tu guarda"


def test_the_words_held_back_are_not_lost():
    """A model that writes the mood in two deltas must not swallow the start."""
    call = SpokenCall()
    call.push('{"message": "ciao a tutti", "mood": "hap')
    out = call.push('py"}')
    assert call.mood == "happy"
    assert out == "ciao a tutti"


def test_the_end_of_the_words_is_reported():
    call = SpokenCall()
    call.push('{"mood": "happy", "message": "ciao"}')
    assert call.finished


@pytest.mark.parametrize("tool", ["stay_silent", "remember_person", "go_to_sleep"])
def test_a_tool_that_says_nothing_out_loud_is_not_watched(tool):
    assert spoken_call(tool) is None


def test_the_speaking_tool_is_watched():
    assert isinstance(spoken_call("speak"), SpokenCall)


# --- what the provider hands over --------------------------------------------
#
# The sdk yields chunks, not a response, and a tool call arrives spread across
# them: the name in one, the arguments a few characters at a time in the rest.


class Sdk:
    """The smallest thing that looks like the sdk's streaming iterator."""

    def __init__(self, chunks, fail_with=None):
        self.chunks = chunks
        self.fail_with = fail_with
        self.calls = []
        self.chat = type("Chat", (), {"completions": self})()

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with and kwargs.get("stream"):
            raise self.fail_with
        if not kwargs.get("stream"):
            return _whole_reply()
        return iter(self.chunks)


def _part(index=0, call_id=None, name=None, arguments=None):
    function = SimpleNamespace(name=name, arguments=arguments)
    return SimpleNamespace(index=index, id=call_id, function=function)


def _chunk(*parts, content=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=list(parts) or None)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage)


def _whole_reply():
    message = SimpleNamespace(content="said all at once", tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=None)


def _writes(text: str, size: int = 5):
    """A tool call written the way a provider writes one."""
    yield _chunk(_part(call_id="c1", name="speak", arguments=""))
    for start in range(0, len(text), size):
        yield _chunk(_part(arguments=text[start:start + size]))


def client(chunks, fail_with=None) -> OpenAICompatibleClient:
    return OpenAICompatibleClient(Sdk(list(chunks), fail_with), "a/model")


async def test_the_arguments_are_handed_over_as_they_are_written():
    raw = '{"mood": "happy", "message": "ciao a tutti quanti"}'
    seen = []
    reply = await client(_writes(raw)).stream_complete(
        [], tools=[{}], on_tool_delta=lambda name, delta: seen.append((name, delta)))

    assert {name for name, _ in seen} == {"speak"}
    assert "".join(delta for _, delta in seen) == raw
    assert reply.tool_calls[0].arguments == {"mood": "happy", "message": "ciao a tutti quanti"}


async def test_the_response_is_the_same_one_a_plain_call_would_have_given():
    raw = '{"mood": "angry", "message": "ma tu guarda"}'
    reply = await client(_writes(raw)).stream_complete([], tools=[{}], on_tool_delta=lambda *_: None)

    call = reply.tool_calls[0]
    assert (call.id, call.name) == ("c1", "speak")
    assert call.arguments["message"] == "ma tu guarda"


async def test_nothing_is_handed_over_before_the_tool_has_a_name():
    """Characters with nobody to attribute them to are held, never dropped."""
    seen = []
    chunks = [_chunk(_part(arguments='{"mood": "happy"')),
              _chunk(_part(call_id="c1", name="speak", arguments=', "message": "ok"}'))]
    await client(chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda name, delta: seen.append((name, delta)))

    assert seen == [("speak", '{"mood": "happy", "message": "ok"}')]


async def test_two_tool_calls_at_once_stay_apart():
    chunks = [
        _chunk(_part(index=0, call_id="a", name="speak", arguments='{"message": "ciao"}')),
        _chunk(_part(index=1, call_id="b", name="go_to_sleep", arguments="{}")),
    ]
    seen = []
    reply = await client(chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda name, delta: seen.append((name, delta)))

    assert seen == [("speak", '{"message": "ciao"}'), ("go_to_sleep", "{}")]
    assert [c.name for c in reply.tool_calls] == ["speak", "go_to_sleep"]


async def test_free_text_alongside_a_tool_call_still_arrives():
    chunks = [_chunk(content="thinking out loud"),
              _chunk(_part(call_id="c1", name="speak", arguments='{"message": "ok"}'))]
    reply = await client(chunks).stream_complete([], tools=[{}], on_tool_delta=lambda *_: None)
    assert reply.content == "thinking out loud"


async def test_the_token_counts_come_off_the_last_chunk():
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=8,
                            prompt_tokens_details=SimpleNamespace(cached_tokens=96))
    chunks = list(_writes('{"message": "ok"}')) + [_chunk(usage=usage)]
    reply = await client(chunks).stream_complete([], tools=[{}], on_tool_delta=lambda *_: None)

    assert reply.usage.prompt_tokens == 120
    assert reply.usage.cached_tokens == 96


async def test_arguments_that_never_parse_cost_the_arguments_and_not_the_turn():
    chunks = [_chunk(_part(call_id="c1", name="speak", arguments="{not json"))]
    reply = await client(chunks).stream_complete([], tools=[{}], on_tool_delta=lambda *_: None)
    assert reply.tool_calls[0].arguments == {}


# --- when speaking early cannot work -----------------------------------------


async def test_a_listener_that_falls_over_costs_nothing_but_itself():
    """Speaking early is an optimisation: it may never cost the turn."""
    def explode(name, delta):
        raise RuntimeError("the engine fell over")

    reply = await client(_writes('{"message": "ciao"}')).stream_complete(
        [], tools=[{}], on_tool_delta=explode)
    assert reply.tool_calls[0].arguments == {"message": "ciao"}


async def test_a_provider_that_cannot_stream_falls_back_to_a_plain_call():
    c = client([], fail_with=RuntimeError("stream_options is not supported"))
    reply = await c.stream_complete([], on_tool_delta=lambda *_: None)
    assert reply.content == "said all at once"


async def test_a_model_that_could_not_stream_is_not_asked_twice():
    """Otherwise every turn pays for the failed attempt and the real call."""
    c = client([], fail_with=RuntimeError("no streaming here"))
    await c.stream_complete([], on_tool_delta=lambda *_: None)
    await c.stream_complete([], on_tool_delta=lambda *_: None)

    assert [k.get("stream", False) for k in c.client.calls] == [True, False, False]


async def test_a_different_model_is_given_its_own_chance():
    c = client([], fail_with=RuntimeError("no streaming here"))
    await c.stream_complete([], on_tool_delta=lambda *_: None)
    c.model_name = "another/model"
    await c.stream_complete([], on_tool_delta=lambda *_: None)

    assert [k.get("stream", False) for k in c.client.calls].count(True) == 2


async def test_a_failure_after_the_first_chunk_is_a_real_failure():
    """Half a turn is not a turn: falling back would say the first half twice."""
    def chunks():
        yield _chunk(_part(call_id="c1", name="speak", arguments='{"message": "ci'))
        raise RuntimeError("the connection dropped")

    with pytest.raises(RuntimeError):
        await client(chunks()).stream_complete([], tools=[{}], on_tool_delta=lambda *_: None)


async def test_with_nobody_listening_it_is_just_an_ordinary_call():
    c = client([])
    reply = await c.stream_complete([])
    assert reply.content == "said all at once"
    assert not c.client.calls[0].get("stream")
