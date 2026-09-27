"""The mouth's clock for a backend that has none of its own, like VTube Studio."""

from src.modules.avatar.mouth_timeline import RESYNC_S, MouthTimeline

A = [[0.1, 0.0], [0.2, 0.0], [0.3, 0.0]]
B = [[0.7, 1.0], [0.8, 1.0]]


def test_a_whole_line_runs_from_the_moment_it_arrived():
    mouth = MouthTimeline()
    mouth.whole(A, 10, now=5.0)
    assert mouth.frame_at(4.99) is None
    assert mouth.frame_at(5.0) == A[0]
    assert mouth.frame_at(5.25) == A[2]
    assert mouth.frame_at(5.3) is None
    assert not mouth.over(5.29) and mouth.over(5.3)


def test_a_call_line_waits_for_the_room_then_places_each_piece():
    mouth = MouthTimeline()
    mouth.add("u1", A, 10, 0)
    assert mouth.waiting() and mouth.frame_at(100.0) is None and not mouth.over(100.0)
    mouth.sync("u1", 0, now=10.0)
    mouth.add("u1", B, 10, 300)
    assert mouth.frame_at(10.1) == A[1]
    assert mouth.frame_at(10.3) == B[0]
    assert mouth.frame_at(10.5) is None and mouth.over(10.5)


def test_a_report_moves_the_clock_to_what_was_heard():
    mouth = MouthTimeline()
    mouth.add("u1", A * 3, 10, 0)
    mouth.sync("u1", 0, now=10.0)
    # the player ran dry: at 10.6 the room has heard only 0.4 s
    mouth.sync("u1", 400, now=10.6)
    assert abs(mouth.started_at - 10.2) < 1e-9
    assert mouth.frame_at(10.6) == (A * 3)[4]


def test_jitter_under_the_resync_step_leaves_the_clock_alone():
    mouth = MouthTimeline()
    mouth.add("u1", A, 10, 0)
    mouth.sync("u1", 0, now=10.0)
    mouth.sync("u1", 250, now=10.25 + RESYNC_S * 0.9)
    assert mouth.started_at == 10.0


def test_a_new_line_drops_the_old_one():
    mouth = MouthTimeline()
    mouth.add("u1", A, 10, 0)
    mouth.sync("u1", 0, now=10.0)
    mouth.add("u2", B, 10, 0)
    assert mouth.id == "u2" and mouth.frame_at(10.0) is None


def test_the_same_timing_as_the_page():
    """`mouth.js` and this agree frame for frame on the same input."""
    mouth = MouthTimeline()
    mouth.add("u1", A, 10, 0)
    mouth.sync("u1", 0, now=1.0)
    mouth.add("u1", B, 10, 300)
    assert [mouth.frame_at(t) for t in (1.0, 1.25, 1.3, 1.45, 1.5)] == [A[0], A[2], B[0], B[1], None]
