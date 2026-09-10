"""Reading a string out of JSON that has not finished arriving.

She speaks by calling a tool, and a tool call is JSON. Waiting for that JSON to
close before the first word can be synthesised is the single largest delay in a
spoken turn — and it is avoidable, because the words are already there, sitting
inside a string that simply has no closing quote yet.

So this walks the JSON character by character as it streams and hands over the
value of one field the moment each character of it is known. It is a state
machine rather than a parser: nothing is ever built, nothing is ever validated,
and the complete tool call is still parsed properly afterwards by the caller.
Being wrong here can only ever mean speaking early or not speaking early — the
turn itself is decided by the parsed arguments, as before.

Pure: characters in, characters out.
"""

from typing import Optional

# what a backslash means inside a JSON string
_ESCAPES = {
    '"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
    "n": "\n", "r": "\r", "t": "\t",
}


class JsonFieldStream:
    """Emits the value of one top-level string field as it arrives.

    Only the top level is considered, so a key of the same name nested inside
    another object never starts it, and a value that happens to contain the
    field's name never ends it.
    """

    def __init__(self, field: str):
        self.field = field
        self._depth = 0
        self._in_string = False
        self._escape = False
        self._hex = ""
        self._collecting_hex = False
        self._expect_key = False
        self._is_key = False
        self._current: list = []
        self._last_key = ""
        self._emitting = False
        self._done = False

    @property
    def done(self) -> bool:
        """The field has closed: nothing more of it is coming."""
        return self._done

    @property
    def started(self) -> bool:
        return self._emitting or self._done

    def push(self, delta: str) -> str:
        """Take more raw JSON; return whatever of the field it revealed."""
        if self._done or not delta:
            return ""
        return "".join(self._char(ch) for ch in delta)

    # --- internals ----------------------------------------------------------

    def _char(self, ch: str) -> str:
        if self._done:
            return ""
        return self._in_string_char(ch) if self._in_string else self._structure_char(ch)

    def _in_string_char(self, ch: str) -> str:
        if self._collecting_hex:
            self._hex += ch
            if len(self._hex) < 4:
                return ""
            self._collecting_hex = False
            try:
                decoded = chr(int(self._hex, 16))
            except ValueError:
                decoded = ""
            self._hex = ""
            return self._take(decoded)

        if self._escape:
            self._escape = False
            if ch == "u":
                self._collecting_hex = True
                self._hex = ""
                return ""
            return self._take(_ESCAPES.get(ch, ch))

        if ch == "\\":
            self._escape = True
            return ""

        if ch == '"':
            self._in_string = False
            if self._emitting:
                self._emitting = False
                self._done = True
            elif self._is_key and self._depth == 1:
                self._last_key = "".join(self._current)
            self._current = []
            return ""

        return self._take(ch)

    def _take(self, text: str) -> str:
        """One decoded character: out to the caller, or kept for a key."""
        if self._emitting:
            return text
        self._current.append(text)
        return ""

    def _structure_char(self, ch: str) -> str:
        if ch == '"':
            self._in_string = True
            self._is_key = self._expect_key
            self._current = []
            if not self._is_key and self._depth == 1 and self._last_key == self.field:
                self._emitting = True
            return ""
        if ch == "{":
            self._depth += 1
            self._expect_key = True
        elif ch == "}":
            self._depth -= 1
        elif ch == ",":
            self._expect_key = True
        elif ch == ":":
            self._expect_key = False
        return ""


class SpokenCall:
    """The two things a `speak` call says, as soon as each of them is known.

    The mood is held back for nobody: it arrives first because the schema puts
    it first, and the words are buffered until it does. A model that writes them
    the other way round simply never streams — the turn still happens, on the
    path it took before any of this existed.
    """

    def __init__(self, mood_field: str = "mood", text_field: str = "message"):
        self._mood = JsonFieldStream(mood_field)
        self._text = JsonFieldStream(text_field)
        self._held: list = []
        self.mood = ""

    def push(self, delta: str) -> str:
        """Take more raw arguments; return the words that are ready to speak."""
        self.mood += self._mood.push(delta)
        said = self._text.push(delta)
        if said:
            self._held.append(said)
        if not self._mood.done:
            return ""
        ready, self._held = "".join(self._held), []
        return ready

    @property
    def ready(self) -> bool:
        """Whether there is a mood to speak the words in yet."""
        return self._mood.done

    @property
    def finished(self) -> bool:
        return self._text.done


def spoken_call(tool: str, speak_tool: str = "speak") -> Optional[SpokenCall]:
    """A reader for `tool`, or None when that tool says nothing out loud."""
    return SpokenCall() if tool == speak_tool else None
