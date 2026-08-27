"""Who she is called, in one place.

Her name used to be the literal string "Bea" in the soul, in the body prompt,
in the trigger words the attention gate listens for, in the display name her
own messages are filed under, and in the dashboard chrome. Renaming her in one
of those broke the others — most visibly the gate, which kept listening for
"bea" while the persona had become someone else.

The product is still called Bea: `uv run bea`, `bea.db`, the loggers. That is
the software's name. This is hers.
"""

import re
from dataclasses import dataclass
from typing import Any, Dict, List

DEFAULT_NAME = "Bea"
DEFAULT_PRONOUNS = "she/her"

# what a prompt file may write. Anything else is left alone: these files are
# hand-edited, and a typo must not eat the line it is on
_PLACEHOLDER = re.compile(r"\{(name|pronouns|subject|object|possessive)\}")


@dataclass(frozen=True)
class Persona:
    """Her name and how she is referred to."""

    name: str = DEFAULT_NAME
    pronouns: str = DEFAULT_PRONOUNS
    # empty means "work them out from the name"
    configured_triggers: tuple = ()

    # --- pronouns -----------------------------------------------------------

    @property
    def _parts(self) -> List[str]:
        parts = [p.strip() for p in (self.pronouns or "").split("/") if p.strip()]
        return parts or [p.strip() for p in DEFAULT_PRONOUNS.split("/")]

    @property
    def subject(self) -> str:
        return self._parts[0]

    @property
    def object(self) -> str:
        parts = self._parts
        return parts[1] if len(parts) > 1 else parts[0]

    @property
    def possessive(self) -> str:
        """The third form when given, otherwise the object form.

        "she/her" makes both "her", which is right. "they/them" gives "them"
        where "their" would be better — so write "they/them/their" if it
        matters to you.
        """
        parts = self._parts
        return parts[2] if len(parts) > 2 else self.object

    # --- what the gate listens for -------------------------------------------

    @property
    def trigger_words(self) -> List[str]:
        """What counts as calling her. Derived from the name unless set."""
        if self.configured_triggers:
            return [str(w).strip().lower() for w in self.configured_triggers if str(w).strip()]

        full = self.name.strip().lower()
        if not full:
            return []
        words = [full]
        # people call you by your first name, not your full name
        first = full.split()[0]
        if first != full:
            words.append(first)
        return words

    # --- filling a prompt ----------------------------------------------------

    def fill(self, text: str) -> str:
        """Substitutes `{name}` and the pronoun placeholders. Leaves the rest."""
        if not text:
            return text
        values = {
            "name": self.name,
            "pronouns": self.pronouns,
            "subject": self.subject,
            "object": self.object,
            "possessive": self.possessive,
        }
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pronouns": self.pronouns,
            "trigger_words": self.trigger_words,
            "derived_triggers": not self.configured_triggers,
        }


def persona_of(config) -> Persona:
    """The persona a config describes, with every default filled in."""
    block = getattr(config, "persona", None) or {}
    attention = getattr(config, "attention", None) or {}

    name = str(block.get("name") or "").strip() or DEFAULT_NAME
    pronouns = str(block.get("pronouns") or "").strip() or DEFAULT_PRONOUNS
    triggers = tuple(attention.get("trigger_words") or ())

    return Persona(name=name, pronouns=pronouns, configured_triggers=triggers)
