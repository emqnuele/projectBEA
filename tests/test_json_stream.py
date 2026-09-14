"""Reading her words out of a tool call that has not finished arriving.

This is the piece that decides whether she starts talking a second early or a
second late, and it runs on text that is, by definition, malformed — a JSON
object with no closing brace. Every case here is a way that text can be cut.
"""

import pytest

from src.core.agent.streaming import JsonFieldStream, SpokenCall, spoken_call


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
# The wire yields SSE blocks, not a response, and a tool call arrives spread
# across them: the name in one, the arguments a few characters at a time in
# the rest.


class FakeContent:
    def __init__(self, lines):
        self._lines = lines

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                if isinstance(line, Exception):
                    raise line
                yield (line + "\n").encode()
        return gen()


class FakeResponse:
    def __init__(self, status=200, payload=None, lines=None):
        self.status = status
        self._payload = payload
        self.content = FakeContent(lines or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        import json as _json

        return _json.dumps(self._payload) if self._payload is not None else ""


class FakeSession:
    posts = []

    def __init__(self, shared):
        self._shared = shared

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def post(self, url, headers=None, json=None):
        FakeSession.posts.append(json)
        # the last response repeats: a test that only cares about the request
        # shapes must not run the queue dry on its fallback calls
        if len(self._shared) > 1:
            return self._shared.pop(0)
        return self._shared[0]


def serve(monkeypatch, *responses):
    import aiohttp

    FakeSession.posts = []
    shared = list(responses)
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: FakeSession(shared))


def sse(doc):
    import json as _json

    return f"data: {_json.dumps(doc)}"


def _part(index=0, call_id=None, name=None, arguments=None):
    part = {"index": index}
    if call_id is not None:
        part["id"] = call_id
    function = {}
    if name is not None:
        function["name"] = name
    if arguments is not None:
        function["arguments"] = arguments
    part["function"] = function
    return part


def _chunk(*parts, content=None, usage=None):
    delta = {}
    if content is not None:
        delta["content"] = content
    if parts:
        delta["tool_calls"] = list(parts)
    doc = {"choices": [{"delta": delta}]}
    if usage is not None:
        doc["usage"] = usage
    return sse(doc)


def _whole_reply():
    return {"choices": [{"message": {"content": "said all at once"}}],
            "usage": None}


def _writes(text: str, size: int = 5):
    """A tool call written the way a provider writes one."""
    yield _chunk(_part(call_id="c1", name="speak", arguments=""))
    for start in range(0, len(text), size):
        yield _chunk(_part(arguments=text[start:start + size]))


def client(monkeypatch, chunks, fail_with=None):
    from src.modules.llm.chat import ChatCompletionsClient

    chunks = list(chunks)
    if fail_with is not None:
        serve(monkeypatch,
              FakeResponse(status=400, payload={"error": {"message": str(fail_with)}}),
              FakeResponse(payload=_whole_reply()))
    elif chunks:
        serve(monkeypatch, FakeResponse(lines=chunks),
              FakeResponse(payload=_whole_reply()))
    else:
        serve(monkeypatch, FakeResponse(payload=_whole_reply()))
    return ChatCompletionsClient(base_url="https://x/v1", model_name="a/model")


async def test_the_arguments_are_handed_over_as_they_are_written(monkeypatch):
    raw = '{"mood": "happy", "message": "ciao a tutti quanti"}'
    seen = []
    reply = await client(monkeypatch, _writes(raw)).stream_complete(
        [], tools=[{}], on_tool_delta=lambda index, name, delta: seen.append((index, name, delta)))

    assert {name for _, name, _ in seen} == {"speak"}
    assert "".join(delta for _, _, delta in seen) == raw
    assert reply.tool_calls[0].arguments == {"mood": "happy", "message": "ciao a tutti quanti"}


async def test_the_response_is_the_same_one_a_plain_call_would_have_given(monkeypatch):
    raw = '{"mood": "angry", "message": "ma tu guarda"}'
    reply = await client(monkeypatch, _writes(raw)).stream_complete(
        [], tools=[{}], on_tool_delta=lambda *_: None)

    call = reply.tool_calls[0]
    assert (call.id, call.name) == ("c1", "speak")
    assert call.arguments["message"] == "ma tu guarda"


async def test_nothing_is_handed_over_before_the_tool_has_a_name(monkeypatch):
    """Characters with nobody to attribute them to are held, never dropped."""
    seen = []
    chunks = [sse({"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": '{"mood": "happy"'}}]}}]}),
        sse({"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "c1", "function": {
                "name": "speak", "arguments": ', "message": "ok"}'}}]}}]})]
    await client(monkeypatch, chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda index, name, delta: seen.append((index, name, delta)))

    assert seen == [(0, "speak", '{"mood": "happy", "message": "ok"}')]


async def test_two_tool_calls_at_once_stay_apart(monkeypatch):
    chunks = [
        _chunk(_part(index=0, call_id="a", name="speak", arguments='{"message": "ciao"}')),
        _chunk(_part(index=1, call_id="b", name="go_to_sleep", arguments="{}")),
    ]
    seen = []
    reply = await client(monkeypatch, chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda index, name, delta: seen.append((index, name, delta)))

    assert seen == [(0, "speak", '{"message": "ciao"}'), (1, "go_to_sleep", "{}")]
    assert [c.name for c in reply.tool_calls] == ["speak", "go_to_sleep"]


async def test_free_text_alongside_a_tool_call_still_arrives(monkeypatch):
    chunks = [_chunk(content="thinking out loud"),
              _chunk(_part(call_id="c1", name="speak", arguments='{"message": "ok"}'))]
    reply = await client(monkeypatch, chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda *_: None)
    assert reply.content == "thinking out loud"


async def test_the_token_counts_come_off_the_last_chunk(monkeypatch):
    usage = {"prompt_tokens": 120, "completion_tokens": 8,
             "prompt_tokens_details": {"cached_tokens": 96}}
    chunks = list(_writes('{"message": "ok"}')) + [_chunk(usage=usage)]
    reply = await client(monkeypatch, chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda *_: None)

    assert reply.usage.prompt_tokens == 120
    assert reply.usage.cached_tokens == 96


async def test_arguments_that_never_parse_cost_the_arguments_and_not_the_turn(monkeypatch):
    chunks = [_chunk(_part(call_id="c1", name="speak", arguments="{not json"))]
    reply = await client(monkeypatch, chunks).stream_complete(
        [], tools=[{}], on_tool_delta=lambda *_: None)
    assert reply.tool_calls[0].arguments == {}


# --- when speaking early cannot work -----------------------------------------


async def test_a_listener_that_falls_over_costs_nothing_but_itself(monkeypatch):
    """Speaking early is an optimisation: it may never cost the turn."""
    def explode(index, name, delta):
        raise RuntimeError("the engine fell over")

    reply = await client(monkeypatch, _writes('{"message": "ciao"}')).stream_complete(
        [], tools=[{}], on_tool_delta=explode)
    assert reply.tool_calls[0].arguments == {"message": "ciao"}


async def test_a_provider_that_cannot_stream_falls_back_to_a_plain_call(monkeypatch):
    c = client(monkeypatch, [], fail_with=RuntimeError("stream_options is not supported"))
    reply = await c.stream_complete([], on_tool_delta=lambda *_: None)
    assert reply.content == "said all at once"


async def test_a_model_that_could_not_stream_is_not_asked_twice(monkeypatch):
    """Otherwise every turn pays for the failed attempt and the real call."""
    c = client(monkeypatch, [], fail_with=RuntimeError("no streaming here"))
    await c.stream_complete([], on_tool_delta=lambda *_: None)
    await c.stream_complete([], on_tool_delta=lambda *_: None)

    assert [k.get("stream", False) for k in FakeSession.posts] == [True, False, False]


async def test_a_different_model_is_given_its_own_chance(monkeypatch):
    c = client(monkeypatch, [], fail_with=RuntimeError("no streaming here"))
    await c.stream_complete([], on_tool_delta=lambda *_: None)
    c.model_name = "another/model"
    await c.stream_complete([], on_tool_delta=lambda *_: None)

    assert [k.get("stream", False) for k in FakeSession.posts].count(True) == 2


async def test_a_failure_after_the_first_chunk_is_a_real_failure(monkeypatch):
    """Half a turn is not a turn: falling back would say the first half twice."""
    chunks = [_chunk(_part(call_id="c1", name="speak", arguments='{"message": "ci')),
              RuntimeError("the connection dropped")]

    with pytest.raises(RuntimeError):
        await client(monkeypatch, chunks).stream_complete(
            [], tools=[{}], on_tool_delta=lambda *_: None)


async def test_with_nobody_listening_it_is_just_an_ordinary_call(monkeypatch):
    c = client(monkeypatch, [])
    reply = await c.stream_complete([])
    assert reply.content == "said all at once"
    assert not FakeSession.posts[0].get("stream")


# --- characters that arrive as escapes ---------------------------------------


def test_an_emoji_survives_being_written_as_two_escapes():
    """Everything above the basic plane is escaped as a surrogate pair.

    Decoded one half at a time it becomes two lone surrogates, which is a string
    python cannot encode as utf-8 at all — so the piece holding it died on the
    way to the engine and the sentence was simply never spoken.
    """
    stream = JsonFieldStream("message")
    said = stream.push('{"message": "hi \\ud83d\\ude00 there"}')

    assert said == "hi 😀 there"
    assert said.encode("utf-8")  # the whole point: this used to raise


def test_a_pair_split_across_three_deltas_still_arrives():
    stream = JsonFieldStream("message")
    said = "".join(stream.push(part) for part in
                   ['{"message": "hi \\ud8', '3d\\ude0', '0 there"}'])
    assert said == "hi 😀 there"


def test_half_a_pair_is_dropped_rather_than_kept():
    """A lone surrogate cannot be encoded either, and nothing can rescue it."""
    stream = JsonFieldStream("message")
    said = stream.push('{"message": "x \\ud83d y"}')

    assert said.encode("utf-8")
    assert "x" in said and "y" in said


def test_a_string_in_an_array_is_not_taken_for_a_key():
    """Inside an array a comma separates values, not pairs."""
    stream = JsonFieldStream("message")
    assert stream.push('{"tags": ["a", "message"], "other": "not the message"}') == ""


def test_an_array_does_not_stop_the_real_field_being_found():
    stream = JsonFieldStream("message")
    assert stream.push('{"tags": ["a", "b"], "message": "ciao"}') == "ciao"
