"""The log level, and when it is decided.

`LOG_LEVEL` is documented as something you put in `.env`, and `.env` is read by
the entrypoint — which necessarily runs after this module has been imported.
Resolving the level once at import time made the documented setting work or not
work depending on the order of the imports above it, silently and with no error
anywhere. These tests pin the level to the moment a logger is asked for.
"""

import logging

import pytest

from src.utils import logger as logger_module


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    """Each test gets its own cache and its own override."""
    monkeypatch.setattr(logger_module, "_loggers", {})
    monkeypatch.setattr(logger_module, "_override", None)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    yield


# --- the environment decides, and it decides late ---------------------------


def test_the_level_defaults_to_info():
    assert logger_module.get_logger("bea.test.default").level == logging.INFO


def test_an_env_var_set_after_import_is_still_honoured(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert logger_module.get_logger("bea.test.late").level == logging.DEBUG


def test_a_logger_built_before_the_env_was_read_catches_up(monkeypatch):
    # exactly the `.env` case: something logs during import, then the entrypoint
    # calls load_dotenv() and every logger must move with it
    early = logger_module.get_logger("bea.test.catchup")
    assert early.level == logging.INFO

    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    again = logger_module.get_logger("bea.test.catchup")

    assert again is early
    assert early.level == logging.DEBUG


def test_the_handler_moves_with_the_logger(monkeypatch):
    # a logger at DEBUG behind a handler still at INFO emits nothing new
    early = logger_module.get_logger("bea.test.handler")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logger_module.get_logger("bea.test.handler")

    assert [h.level for h in early.handlers] == [logging.DEBUG]


def test_a_nonsense_level_falls_back_to_info(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "LOUD")
    assert logger_module.get_logger("bea.test.nonsense").level == logging.INFO


def test_the_level_is_read_case_insensitively(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warning")
    assert logger_module.get_logger("bea.test.case").level == logging.WARNING


# --- an explicit choice outranks the environment ----------------------------


def test_quieten_turns_existing_loggers_down():
    noisy = logger_module.get_logger("bea.test.quieten")
    logger_module.quieten()

    assert noisy.level == logging.WARNING
    assert [h.level for h in noisy.handlers] == [logging.WARNING]


def test_quieten_holds_against_the_environment(monkeypatch):
    # --doctor and --update quieten on purpose: their output *is* the report,
    # and a DEBUG left in `.env` must not bury it
    logger_module.quieten()
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    assert logger_module.get_logger("bea.test.pinned").level == logging.WARNING


def test_quieten_applies_to_loggers_asked_for_afterwards():
    logger_module.quieten(logging.ERROR)
    assert logger_module.get_logger("bea.test.after").level == logging.ERROR
