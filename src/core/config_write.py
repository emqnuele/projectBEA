"""The dashboard's one save, validated.

`POST /config` used to walk the payload with `hasattr` and `setattr`. `hasattr`
answers for methods and class attributes too, not only for settings: the
endpoint could replace `save_to_file` with an integer, or empty `SECRET_KEYS`
and have the very next save write every API key into config.json in clear text.
Nothing checked types either, so an OBS port could be stored as the word
"banana" and only fail much later, somewhere else.

What may be written is derived rather than guessed. A key has to be a field of
`BrainConfig`, and its value has to fit either the type that field declares or,
where `settings_schema` describes it, the stricter rule declared there. The
whole payload is checked before any of it is applied, so a rejected save leaves
the running config exactly as it was.
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, Union, get_args, get_origin, get_type_hints

from src.core.config import MASK, SECRET_ENV_VARS, BrainConfig, deep_merge
from src.core.settings_schema import SECTIONS, Setting, coerce

# `PUT /persona` owns this one: it refuses a blank name and a soul the size of
# a novel, and a second way in would be a way around those
GUARDED = frozenset({"persona"})

# the provider object is built once at startup, so changing it needs a restart
RESTART_FIELDS = ("tts_provider", "stt_provider")

_DECLARED: Dict[str, Dict[str, Setting]] = {
    sec.key: {s.key: s for s in sec.settings} for sec in SECTIONS
}
_SKILL_SECTIONS = frozenset(sec.key for sec in SECTIONS if sec.scope == "skills")

_PRIMITIVES = {bool: "bool", int: "int", float: "float", str: "string"}

_hints: Dict[str, Any] = {}


class WriteRejected(ValueError):
    """A rejected payload, with the offending keys named."""


@dataclass(frozen=True)
class Plan:
    """A validated payload: what would change, and what it needs.

    Validating and applying are two steps because writing the secrets can fail
    on its own — an unwritable `.env` — and a save that reports failure has to
    have changed nothing, rather than having already moved the running config.
    """

    changed: Dict[str, Any] = field(default_factory=dict)
    # secret path (`groq_key`, `discord.token`) -> value, for `.env`
    secrets: Dict[str, str] = field(default_factory=dict)
    restart_required: bool = False

    def apply(self, config: BrainConfig) -> Dict[str, Any]:
        for key, value in self.changed.items():
            if isinstance(value, dict):
                # merged, not replaced: a save carrying only the backend choice
                # must not wipe the model path and the maps it said nothing about
                current = getattr(config, key, None)
                value = deep_merge(current, value) if isinstance(current, dict) else value
            setattr(config, key, value)
        return self.changed


def fields_of(config) -> Dict[str, Any]:
    """The writable fields of `BrainConfig`, by name, with their types."""
    global _hints
    if not _hints:
        # resolved rather than read off `__annotations__`, which is a string
        # the moment anyone adds `from __future__ import annotations`
        resolved = get_type_hints(type(config))
        _hints = {f.name: resolved.get(f.name, Any) for f in dataclasses.fields(config)}
    return _hints


# --- fitting a value to the type its field declares -------------------------


def _fit(value: Any, declared: Any) -> Any:
    """`value` as `declared`, or ValueError saying what was expected."""
    origin = get_origin(declared)

    if origin is Union:
        if value is None:
            return None
        inner = [a for a in get_args(declared) if a is not type(None)]
        return _fit(value, inner[0]) if inner else value

    if origin is dict or declared is dict:
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        return value

    if origin is list or declared is list:
        if not isinstance(value, list):
            raise ValueError("expected a list")
        return value

    kind = _PRIMITIVES.get(declared)
    if kind is None:
        raise ValueError("not a writable setting")
    if isinstance(value, (dict, list)):
        raise ValueError("expected a single value, not an object")
    return coerce(Setting("", "", kind, ""), value)


def _fit_block(
    section_key: str,
    incoming: Dict[str, Any],
    errors: Dict[str, str],
    prefix: str,
) -> Dict[str, Any]:
    """One block of settings, coerced where the schema has something to say.

    Keys the schema does not declare are passed through: they are inside a
    block on the config and cannot reach anything else, and refusing them here
    would break every knob the dashboard has that was never declared.
    """
    declared = _DECLARED.get(section_key, {})
    clean: Dict[str, Any] = {}

    for key, raw in incoming.items():
        setting = declared.get(key)
        if setting is None:
            clean[key] = raw
            continue
        # the ui reads secrets back masked; writing that would replace the real
        # one with asterisks
        if setting.secret and raw == MASK:
            continue
        try:
            clean[key] = coerce(setting, raw)
        except ValueError as e:
            errors[f"{prefix}{key}"] = str(e)

    return clean


def _fit_skills(
    incoming: Dict[str, Any], errors: Dict[str, str]
) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for skill_key, block in incoming.items():
        if not isinstance(block, dict):
            errors[f"skills.{skill_key}"] = "expected an object"
            continue
        clean[skill_key] = _fit_block(skill_key, block, errors, f"skills.{skill_key}.")
    return clean


# --- the save ---------------------------------------------------------------


def _secret_paths(staged: Dict[str, Any]) -> Dict[str, str]:
    """The secrets in a staged payload, keyed the way `SECRET_ENV_VARS` is."""
    found: Dict[str, str] = {}

    for key, value in staged.items():
        if key in SECRET_ENV_VARS:
            found[key] = "" if value is None else str(value)

    for skill_key, block in (staged.get("skills") or {}).items():
        if not isinstance(block, dict):
            continue
        for field_name, value in block.items():
            path = f"{skill_key}.{field_name}"
            if path in SECRET_ENV_VARS:
                found[path] = "" if value is None else str(value)

    return found


def plan_config(config: BrainConfig, payload: Dict[str, Any]) -> Plan:
    """Validates a whole-config payload. Raises WriteRejected, changes nothing.

    All-or-nothing on purpose: a save that half-applies leaves the user unable
    to tell what took effect, and the half that did is already live.
    """
    declared = fields_of(config)
    errors: Dict[str, str] = {}
    staged: Dict[str, Any] = {}

    for key, raw in sorted(payload.items()):
        if key in GUARDED:
            if raw == getattr(config, key, None):
                continue
            errors[key] = "not writable here"
            continue

        declared_type = declared.get(key)
        if declared_type is None:
            errors[key] = "unknown setting"
            continue

        if key in SECRET_ENV_VARS and raw == MASK:
            continue

        try:
            fitted = _fit(raw, declared_type)
        except ValueError as e:
            errors[key] = str(e)
            continue

        if key == "skills":
            fitted = _fit_skills(fitted, errors)
        elif isinstance(fitted, dict) and key in _DECLARED:
            fitted = _fit_block(key, fitted, errors, f"{key}.")

        staged[key] = fitted

    if errors:
        detail = "; ".join(f"{k}: {v}" for k, v in sorted(errors.items()))
        raise WriteRejected(detail)

    return Plan(
        changed=staged,
        secrets=_secret_paths(staged),
        restart_required=any(
            name in staged and staged[name] != getattr(config, name)
            for name in RESTART_FIELDS
        ),
    )


def apply_config(config: BrainConfig, payload: Dict[str, Any]) -> Plan:
    """Validate and apply in one step, for callers with nothing to do between."""
    plan = plan_config(config, payload)
    plan.apply(config)
    return plan


def section_secrets(section_key: str, changed: Dict[str, Any]) -> Dict[str, str]:
    """The secrets in what `apply_section` just wrote, keyed for `.env`."""
    if section_key not in _SKILL_SECTIONS:
        return {}
    found: Dict[str, str] = {}
    for field_name, value in changed.items():
        path = f"{section_key}.{field_name}"
        if path in SECRET_ENV_VARS:
            found[path] = "" if value is None else str(value)
    return found
