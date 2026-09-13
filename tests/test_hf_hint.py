"""Both models she downloads come from the same place and fail the same ways.

What is asserted here is that the two failures with a real answer get one, and
that nothing else is guessed at — a wrong explanation is worse than none.
"""

from src.utils.huggingface import OFFLINE_HINT, TOKEN_HINT, download_hint


def test_a_refusal_points_at_the_token_that_would_fix_it():
    assert download_hint(OSError("401 Client Error: Unauthorized")) == TOKEN_HINT
    assert download_hint(OSError("429 Too Many Requests")) == TOKEN_HINT
    assert download_hint(OSError("Access to this gated repo is restricted")) == TOKEN_HINT


def test_a_connection_that_died_says_so_instead():
    assert download_hint(OSError("Connection reset by peer")) == OFFLINE_HINT
    assert download_hint(TimeoutError("timed out")) == OFFLINE_HINT


def test_an_error_with_no_answer_is_left_to_speak_for_itself():
    assert download_hint(ValueError("Invalid model size 'nonsense'")) is None
    assert download_hint(RuntimeError("no wheel for this platform")) is None


def test_the_type_of_the_error_counts_too():
    """huggingface_hub says it in the class name as often as in the message."""
    assert download_hint(type("GatedRepoError", (Exception,), {})()) == TOKEN_HINT
