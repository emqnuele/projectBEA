"""Where her mouth is in the line she is saying, for a backend with no page clock.

The same model as the browser source's `mouth.js`: a line is a list of
segments, each one piece's envelope at its offset into the line, and the moment
the line started. A local line is one segment starting when it arrives; a call
line arrives piece by piece and starts when the bot says the room is hearing
it, and every report after that moves the start to what was actually heard.
Pure: every time is passed in, so it is tested without a clock.
"""

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

# a report this close to where the line already is changes nothing, so jitter never shakes the mouth
RESYNC_S = 0.05

Frame = Sequence[float]


@dataclass
class Segment:
    offset: float
    frames: List[Frame]
    fps: int

    @property
    def end(self) -> float:
        return self.offset + len(self.frames) / self.fps


class MouthTimeline:
    def __init__(self) -> None:
        self.id: Optional[str] = None
        self.started_at: Optional[float] = None
        self.segments: List[Segment] = []

    def clear(self) -> None:
        self.id, self.started_at, self.segments = None, None, []

    def whole(self, frames: Sequence[Frame], fps: int, now: float) -> None:
        """A whole line, heard from `now`."""
        self.id, self.started_at = None, now
        self.segments = [Segment(0.0, list(frames), max(1, int(fps)))]

    def add(self, utterance_id: str, frames: Sequence[Frame], fps: int, offset_ms: int) -> None:
        """One piece of a call line. A piece of another line starts that line."""
        if utterance_id != self.id:
            self.id, self.started_at, self.segments = utterance_id, None, []
        self.segments.append(Segment(offset_ms / 1000.0, list(frames), max(1, int(fps))))

    def sync(self, utterance_id: str, played_ms: int, now: float) -> None:
        """The room has heard `played_ms` of the line as of `now`."""
        started = now - played_ms / 1000.0
        if utterance_id != self.id:
            self.id, self.started_at, self.segments = utterance_id, started, []
            return
        if self.started_at is None or abs(self.started_at - started) > RESYNC_S:
            self.started_at = started

    def frame_at(self, now: float) -> Optional[Frame]:
        if self.started_at is None:
            return None
        at = now - self.started_at
        for segment in self.segments:
            # floor, not int, so a moment before the line is no frame; the nudge absorbs float error in seconds
            index = math.floor((at - segment.offset) * segment.fps + 1e-9)
            if 0 <= index < len(segment.frames):
                return segment.frames[index]
        return None

    def waiting(self) -> bool:
        """A call line whose pieces are here but whose sound is not yet."""
        return self.started_at is None and bool(self.segments)

    def over(self, now: float) -> bool:
        """Nothing is left to mouth, and nothing is waiting to start."""
        if self.started_at is None:
            return not self.segments
        return all(now - self.started_at + 1e-9 >= segment.end for segment in self.segments)
