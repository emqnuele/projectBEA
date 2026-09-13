"""Everything the settings screens read and write.

Two shapes reach the same place: the dashboard's single save posts the whole
config, and each schema-rendered section posts only itself. Both are validated
against declared rules before anything is applied, and both send secrets to
`.env` rather than to config.json, which strips them.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core import secrets as secret_store
from src.core.brain import AIVtuberBrain
from src.core.config import SECRET_SKILL_FIELDS
from src.core.config_write import WriteRejected, plan_config, section_secrets
from src.core.settings_schema import ValidationError, describe, plan_section, write_section
from src.core.settings_schema import restart_needed as _restart_needed
from src.core.settings_schema import section as _section
from src.utils.logger import get_logger
from src.web.deps import get_brain

logger = get_logger("bea.web.settings")

router = APIRouter(tags=["settings"])


class ConfigUpdateRequest(BaseModel):
    config: Dict[str, Any]


def store_secrets(values: Dict[str, str]) -> List[str]:
    """Secrets to `.env`, the only place they survive a restart.

    Called before anything is applied: an unwritable `.env` has to fail the
    whole save, rather than leave a token live until the next start drops it.
    """
    if not values:
        return []
    try:
        return secret_store.persist(values)
    except OSError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Nothing was saved: the secrets could not be written to .env ({e.strerror}).",
        ) from e


@router.get("/config")
def get_config(brain: AIVtuberBrain = Depends(get_brain)):
    return brain.config.public_dict()


@router.post("/config")
def update_config(request: ConfigUpdateRequest, brain: AIVtuberBrain = Depends(get_brain)):
    try:
        plan = plan_config(brain.config, request.config)
    except WriteRejected as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    stored = store_secrets(plan.secrets)
    plan.apply(brain.config)
    brain.config.save_to_file()
    brain.reload_configuration()

    msg = "Configuration updated."
    if plan.restart_required:
        msg += " RESTART REQUIRED to apply new provider settings."

    return {
        "status": "success",
        "message": msg,
        "restart_required": plan.restart_required,
        "secrets_written_to_env": stored,
    }


@router.get("/settings")
def get_settings(brain: AIVtuberBrain = Depends(get_brain)):
    return describe(brain.config)


@router.get("/settings/{key}")
def get_settings_section(key: str, brain: AIVtuberBrain = Depends(get_brain)):
    data = describe(brain.config)
    for block in data["sections"]:
        if block["key"] == key:
            return block
    raise HTTPException(status_code=404, detail=f"Unknown settings section: {key}")


@router.post("/settings/{key}")
async def update_settings_section(
    key: str, payload: Dict[str, Any], brain: AIVtuberBrain = Depends(get_brain)
):
    try:
        sec = _section(key)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown settings section: {key}") from e

    try:
        changed = plan_section(brain.config, key, payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    stored = store_secrets(section_secrets(key, changed))
    write_section(brain.config, key, changed)
    brain.config.save_to_file()

    # a platform's on/off switch is the skill registry's business: it starts and
    # stops a live connection, which a config reload does not do
    if sec.toggleable and "enabled" in changed:
        try:
            await brain.set_skill_enabled(key, bool(changed["enabled"]))
        except Exception as e:
            logger.error(f"Toggling {key} failed: {e}")

    brain.reload_configuration()

    return {
        "status": "success",
        "changed": changed,
        "secrets_written_to_env": stored,
        "restart_required": _restart_needed(key, changed),
    }


@router.get("/secrets")
def secrets_state(brain: AIVtuberBrain = Depends(get_brain)):
    """Which secrets are set — never their values.

    `public_dict()` strips them entirely, so the UI could not tell a missing key
    from a stored one and every field looked empty.
    """
    config = brain.config
    state = {key: bool(getattr(config, key, None)) for key in config.SECRET_KEYS}
    for skill_key, field_name in SECRET_SKILL_FIELDS:
        state[f"{skill_key}.{field_name}"] = bool(config.skills.get(skill_key, {}).get(field_name))
    return state


@router.get("/audio/devices")
def audio_devices():
    """Output devices, so picking one is not guesswork about an integer."""
    try:
        import sounddevice as sd

        return [
            {"id": index, "name": device.get("name", f"Device {index}"),
             "channels": device.get("max_output_channels", 0)}
            for index, device in enumerate(sd.query_devices())
            if device.get("max_output_channels", 0) > 0
        ]
    except Exception as e:
        logger.warning(f"Could not enumerate audio devices: {e}")
        return []
