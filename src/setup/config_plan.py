"""Turning wizard answers into the two files the engine actually reads.

Pure on purpose: the interactive half in `wizard.py` only collects a dict, and
everything that decides what lands in config.json or `.env` lives here, where a
test can reach it without a terminal.
"""

from typing import Any, Dict

# provider -> (config field for the key, env var the engine reads it from)
PROVIDER_KEYS = {
    "openrouter": ("openrouter_key", "OPENROUTER_API_KEY"),
    "openai": ("openai_key", "OPENAI_API_KEY"),
    "groq": ("groq_key", "GROQ_API_KEY"),
}

# provider -> (config field for the model, a default that exists today)
PROVIDER_MODELS = {
    "openrouter": ("openrouter_model", "deepseek/deepseek-v4-flash"),
    "openai": ("openai_model", "gpt-5"),
    "groq": ("groq_model", "openai/gpt-oss-120b"),
}

# only these two can transcribe, so voice input needs a key for one of them
STT_PROVIDERS = ("groq", "openrouter")

# secrets that belong to a skill rather than to a provider
SKILL_SECRETS = {
    "discord": "DISCORD_TOKEN",
    "telegram": "TELEGRAM_TOKEN",
    "twitch": "TWITCH_OAUTH_TOKEN",
    "donations": "DONATION_SECRET",
}

# every capability the wizard can arm, in the order it asks about them
PLATFORM_SKILLS = ("discord", "telegram", "twitch", "minecraft", "donations")


def apply_answers(config, answers: Dict[str, Any]):
    """Fold the wizard's answers into `config`, leaving everything else alone.

    Secrets are set on the in-memory config so a connection test right after
    setup works; `save_to_file` drops them again on the way to disk.
    """
    provider = answers["llm_provider"]
    key_field, _ = PROVIDER_KEYS[provider]
    model_field, default_model = PROVIDER_MODELS[provider]

    config.llm_provider = provider
    setattr(config, model_field, answers.get("llm_model") or default_model)
    if answers.get("llm_key"):
        setattr(config, key_field, answers["llm_key"])

    # an empty pool falls back to llm_provider, which is what a fresh setup wants
    config.models = {"mind": [], "background": []}

    if answers.get("stt_provider"):
        config.stt_provider = answers["stt_provider"]

    config.tts_provider = answers.get("tts_provider", "edge")
    if answers.get("tts_voice"):
        config.tts_voice = answers["tts_voice"]
    if answers.get("orpheus_endpoint"):
        config.orpheus_endpoint = answers["orpheus_endpoint"]
    if answers.get("orpheus_voice"):
        config.orpheus_voice = answers["orpheus_voice"]
    if answers.get("audio_device_id") is not None:
        config.audio_device_id = answers["audio_device_id"]

    obs = answers.get("obs")
    if obs:
        config.obs_host = obs.get("host", config.obs_host)
        config.obs_port = obs.get("port", config.obs_port)
        config.obs_password = obs.get("password", config.obs_password)
        config.obs_avatar_source = obs.get("avatar_source", config.obs_avatar_source)
        config.obs_text_source = obs.get("text_source", config.obs_text_source)

    # every platform skill is decided here, so an unchecked one is turned off
    # rather than left however a previous run happened to leave it
    chosen = answers.get("skills", {})
    for name in PLATFORM_SKILLS:
        block = config.skills.setdefault(name, {})
        settings = chosen.get(name)
        block["enabled"] = settings is not None
        if settings:
            block.update({k: v for k, v in settings.items() if k != "token"})

    return config


def env_updates(answers: Dict[str, Any]) -> Dict[str, str]:
    """The secrets from `answers`, keyed by the env var the engine reads."""
    updates: Dict[str, str] = {}

    _, env_var = PROVIDER_KEYS[answers["llm_provider"]]
    if answers.get("llm_key"):
        updates[env_var] = answers["llm_key"]

    # voice input may use a provider the mind does not, so it carries its own key
    stt = answers.get("stt_provider")
    if stt and answers.get("stt_key"):
        updates[PROVIDER_KEYS[stt][1]] = answers["stt_key"]

    if answers.get("orpheus_key"):
        updates["ORPHEUS_API_KEY"] = answers["orpheus_key"]
    if answers.get("orpheus_endpoint"):
        updates["ORPHEUS_ENDPOINT"] = answers["orpheus_endpoint"]

    for name, settings in answers.get("skills", {}).items():
        env_var = SKILL_SECRETS.get(name)
        if env_var and settings.get("token"):
            updates[env_var] = settings["token"]

    return updates
