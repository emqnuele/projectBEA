"""Six questions, and a persona at the end of them.

The CLI wizard sets up the plumbing and never asks who she is, so the shipped
personality is what most people end up running forever. This is the other half,
and it only runs once.

The model helps, but it does not decide the shape: it answers in JSON and the
markdown is assembled here. A model writing free-form markdown gives a
different structure every time — which is exactly the failure mode we spent the
last phase digging out of.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence

from src.core.persona import DEFAULT_NAME
from src.utils.logger import get_logger

logger = get_logger("bea.onboarding")

# a persona is a page, not a book
MAX_LINE_CHARS = 240
MAX_LINES_PER_SECTION = 8


@dataclass(frozen=True)
class Question:
    key: str
    label: str
    help: str
    type: str = "text"
    placeholder: str = ""
    options: Sequence[str] = field(default_factory=tuple)
    default: str = ""
    required: bool = False

    def describe(self) -> Dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "help": self.help,
            "type": self.type, "placeholder": self.placeholder,
            "options": list(self.options), "default": self.default,
            "required": self.required,
        }


QUESTIONS: List[Question] = [
    Question(
        "name", "What is she called?",
        "Everything follows this: what she answers to, how she signs her messages, "
        "the name in the corner of this dashboard.",
        placeholder="Bea", default=DEFAULT_NAME, required=True,
    ),
    Question(
        "what", "What is she?",
        "One line. It sets what she thinks she is doing all day.",
        type="select",
        options=("a streamer", "a co-host", "someone to talk to", "something else"),
        default="a streamer",
    ),
    Question(
        "adjectives", "Three words for her character",
        "The ones you would use describing her to a friend.",
        placeholder="sarcastic, curious, competitive",
    ),
    Question(
        "loves", "What lights her up?",
        "The things she actually wants to talk about.",
        placeholder="money, cats, winning an argument",
    ),
    Question(
        "hates", "What can she not stand?",
        "Just as defining as what she likes, and funnier.",
        placeholder="being corrected, small talk, people explaining the obvious",
    ),
    Question(
        "voice", "How does she talk?",
        "Length and temperature, more than vocabulary.",
        type="select",
        options=("short and sharp", "warm and rambly", "deadpan", "dramatic"),
        default="short and sharp",
    ),
    Question(
        "owner", "Who are you to her?",
        "She treats messages from you differently from everyone else's.",
        placeholder="the person whose stream this is",
    ),
]


SYSTEM = """You write the character sheet for an AI persona, from an owner's answers.

Reply with JSON only, in this shape:
{"identity": ["...", "..."], "voice": ["...", "..."], "constants": ["...", "..."]}

- `identity` — who she is: 3 to 5 lines, each one trait with a bit of colour.
- `voice` — how she talks: 3 to 4 lines about length, register and reflexes.
- `constants` — what is true in every situation: 2 to 3 lines.

Write in the second person ("You are...", "You talk..."). Refer to her as {name}
literally — that placeholder, never a real name, because she can be renamed later.
Match the language the answers are written in. Be specific and a little unkind
rather than warm and generic: a persona made of nice adjectives has no character.
Return the JSON and nothing else."""


def _clean(value: Any) -> List[str]:
    """Whatever the model gave for a section, as a list of usable lines."""
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        return []
    lines = []
    for item in items[:MAX_LINES_PER_SECTION]:
        # a heading the model snuck in would give us two of the same section
        text = " ".join(str(item).replace("#", "").split()).strip(" -*")
        if text:
            lines.append(text[:MAX_LINE_CHARS])
    return lines


def _section(title: str, lines: Sequence[str]) -> str:
    return f"## {title}\n" + "\n".join(f"- {line}" for line in lines)


def _answer(answers: Dict[str, Any], key: str, fallback: str = "") -> str:
    return str((answers or {}).get(key) or "").strip() or fallback


def build_soul(answers: Dict[str, Any]) -> str:
    """A persona from the answers alone.

    This is the template, and it is also the fallback: if the model is down or
    talking nonsense, the answers are still enough for something usable.
    Onboarding must never dead-end.
    """
    answers = answers or {}
    what = _answer(answers, "what", "an AI VTuber")
    adjectives = _answer(answers, "adjectives")
    loves = _answer(answers, "loves")
    hates = _answer(answers, "hates")
    voice = _answer(answers, "voice", "short and sharp")
    owner = _answer(answers, "owner")

    identity = [f"You are {{name}}, {what}."]
    if adjectives:
        identity.append(f"People would describe you as {adjectives}.")
    if loves:
        identity.append(f"What genuinely lights you up: {loves}.")
    if hates:
        identity.append(f"What you cannot stand: {hates}.")
    if owner:
        identity.append(f"{owner} — you treat what they say differently from anyone else's.")

    voice_lines = [
        f"You talk {voice}.",
        "React with attitude instead of narrating what you are doing.",
        "Short lines. You speak in quips, not paragraphs.",
    ]

    constants = [
        "Stay in character at all times — in chat, in a call, or thinking out loud.",
        "You are not an assistant and you never mention being a language model.",
        "Be worth listening to. Even complaining should be fun to hear.",
    ]

    return "\n\n".join([
        "# SOUL — Who {name} Is",
        _section("Identity", identity),
        _section("Voice", voice_lines),
        _section("Constants", constants),
    ])


def parse_draft(draft: Any, answers: Dict[str, Any]) -> str:
    """The model's JSON into the shape every soul has. Falls back on nonsense."""
    if not isinstance(draft, dict):
        return build_soul(answers)

    identity = _clean(draft.get("identity"))
    voice = _clean(draft.get("voice"))
    constants = _clean(draft.get("constants"))

    if not identity and not voice:
        return build_soul(answers)

    template = build_soul(answers)
    if not identity:
        return template
    if not voice:
        voice = ["You talk " + _answer(answers, "voice", "short and sharp") + "."]
    if not constants:
        constants = ["Stay in character at all times.",
                     "You are not an assistant and you never mention being a language model."]

    return "\n\n".join([
        "# SOUL — Who {name} Is",
        _section("Identity", identity),
        _section("Voice", voice),
        _section("Constants", constants),
    ])


async def draft_soul(llm, answers: Dict[str, Any]) -> str:
    """Asks the model for a persona, and always returns one."""
    payload = "\n".join(
        f"{q.label} {_answer(answers, q.key, '(not answered)')}" for q in QUESTIONS
    )
    try:
        draft = await llm.complete_json(payload, SYSTEM)
    except Exception as e:
        logger.warning(f"Could not draft a persona ({e}); using the answers alone.")
        return build_soul(answers)
    return parse_draft(draft, answers)


def needed(*, customised: bool, completed: bool) -> bool:
    """Only when the soul is still the shipped one and nobody has said no.

    "Does soul.md exist" is not the question — it always does, we ship it.
    """
    return not customised and not completed
