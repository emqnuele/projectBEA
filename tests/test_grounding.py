from unittest.mock import MagicMock

from src.core.consciousness import Consciousness
from src.core.perception.types import Author, Perception, PerceptionKind


def test_needs_mind():
    # Noise does not need mind
    p1 = Perception(PerceptionKind.GAME, "minecraft", "noise", meta={"noise": True})
    assert Consciousness._needs_mind([p1]) is False

    # Real message needs mind
    p2 = Perception(PerceptionKind.CHAT, "discord", "hello")
    assert Consciousness._needs_mind([p2]) is True


def test_orientation_grounding():
    # Setup mock dependencies
    mock_config = MagicMock()
    mock_config.consciousness = {}
    mock_llm = MagicMock()
    mock_bus = MagicMock()
    mock_expression = MagicMock()
    mock_surfaces = MagicMock()
    mock_history = MagicMock()
    mock_events = MagicMock()

    c = Consciousness(
        config=mock_config,
        llm=mock_llm,
        bus=mock_bus,
        expression=mock_expression,
        surfaces=mock_surfaces,
        history_manager=mock_history,
        event_manager=mock_events,
        soul_getter=lambda: "soul",
        operating_getter=lambda: "operating"
    )

    author = Author(platform="discord", native_id="123", display_name="Alice")
    p = Perception(PerceptionKind.CHAT, "discord", "hello", author=author, meta={"channel_id": "888", "is_dm": False})

    annotated = [(p, 1.0)]
    orientation = c._orientation(annotated)

    assert "[WHERE YOU ARE]" in orientation
    assert "You are on discord in conversation 888 with Alice" in orientation
    assert "send_message(platform='discord', channel='888')" in orientation


def test_attention_wired_to_sliding_window():
    from src.core.attention.gate import Attention

    mock_config = MagicMock()
    mock_config.consciousness = {}
    mock_config.attention = {}

    attention = Attention.__new__(Attention)
    attention.window = None
    c = Consciousness(
        config=mock_config,
        llm=MagicMock(),
        bus=MagicMock(),
        expression=MagicMock(),
        surfaces=MagicMock(),
        history_manager=MagicMock(),
        event_manager=MagicMock(),
        soul_getter=lambda: "soul",
        operating_getter=lambda: "operating",
        attention=attention,
    )
    assert attention.window is c.sliding_window
