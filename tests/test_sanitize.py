"""Scaffolding the model leaks must never be spoken out loud."""

import pytest

from src.utils.sanitize import clean_model_output


def test_clean_text_passes_through():
    assert clean_model_output("ciao, come va?") == "ciao, come va?"


def test_empty_input_stays_empty():
    assert clean_model_output("") == ""
    assert clean_model_output(None) == ""


def test_a_closed_think_block_is_removed():
    raw = "<think>should I answer this</think>ok, sure"
    assert clean_model_output(raw) == "ok, sure"


def test_a_think_block_in_the_middle_is_removed():
    assert clean_model_output("prima <think>hmm</think> dopo") == "prima  dopo"


@pytest.mark.parametrize("tag", ["think", "thinking", "reasoning", "analysis", "scratchpad"])
def test_every_reasoning_tag_variant_is_removed(tag):
    assert clean_model_output(f"<{tag}>noise</{tag}>real answer") == "real answer"


def test_an_unclosed_think_block_swallows_the_rest():
    # a truncated generation leaves the block open; keeping the tail would speak it
    assert clean_model_output("visible part\n<think>cut off mid-thou") == "visible part"


def test_an_output_that_is_only_reasoning_becomes_empty():
    assert clean_model_output("<think>only thinking, no answer</think>") == ""


def test_the_harmony_format_keeps_only_the_final_channel():
    raw = ("<|channel|>analysis<|message|>the user wants a joke"
           "<|channel|>final<|message|>here's your joke<|end|>")
    assert clean_model_output(raw) == "here's your joke"


def test_the_harmony_format_without_a_terminator_still_works():
    raw = "<|channel|>analysis<|message|>thinking<|channel|>final<|message|>the answer"
    assert clean_model_output(raw) == "the answer"


@pytest.mark.parametrize("token", ["<|endoftext|>", "<|im_end|>", "<|eot_id|>", "<|im_start|>"])
def test_special_tokens_are_stripped(token):
    assert clean_model_output(f"hello{token}") == "hello"


@pytest.mark.parametrize("prefix", ["assistant:", "assistant>", "final:", "response:"])
def test_a_leading_role_marker_is_stripped(prefix):
    assert clean_model_output(f"{prefix} the actual line") == "the actual line"


def test_a_role_word_inside_the_text_is_left_alone():
    assert clean_model_output("the assistant: was useless") == "the assistant: was useless"


def test_blank_line_runs_left_by_removals_are_collapsed():
    raw = "line one\n\n<think>x</think>\n\n\nline two"
    assert clean_model_output(raw).count("\n\n\n") == 0


def test_surrounding_whitespace_is_trimmed():
    assert clean_model_output("   spaced out   ") == "spaced out"


def test_a_realistic_gpt_oss_leak():
    raw = (
        "<|channel|>analysis<|message|>User greeted me. I should be sassy."
        "<|channel|>final<|message|>oh look who decided to show up<|return|>"
    )
    assert clean_model_output(raw) == "oh look who decided to show up"
