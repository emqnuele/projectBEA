import os
from typing import Dict, Any
from dotenv import load_dotenv

# load_dotenv() - handled by main.py


class Config:
    # minecraft connection
    MC_SERVER_URL = os.getenv("MC_SERVER_URL", "ws://localhost:8080")
    
    # web ui
    WEB_PORT = int(os.getenv("WEB_PORT", 5000))
    
    # llm configuration
    OPENAI_API_KEY = os.getenv("MC_OPENAI_KEY") or os.getenv("OPENAI_API_KEY") # prioritize specific, fallback to global
    OPENAI_MODEL = os.getenv("MC_OPENAI_MODEL", "gpt-4o-mini")
    
    # agent behavior
    MAX_HISTORY_EVENTS = 20
    DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() == "true"
    
    # feature flags
    AUTO_CHAT_THOUGHTS = os.getenv("AUTO_CHAT_THOUGHTS", "False").lower() == "true"
    AUTO_SPEAK_THOUGHTS = False
    
    SYSTEM_PROMPT = None
    SYSTEM_PROMPT_PATH = None

    # validation
    @classmethod
    def validate(cls):
        pass

    @classmethod
    def update_from_dict(cls, data: Dict[str, Any]):
        """Updates config from a dictionary (e.g. from BrainConfig)."""
        changed = False
        if "minecraft" in data:
            mc_conf = data["minecraft"]
            if "server_url" in mc_conf and cls.MC_SERVER_URL != mc_conf["server_url"]:
                cls.MC_SERVER_URL = mc_conf["server_url"]
            
            # optional overrides
            if "max_history_events" in mc_conf and cls.MAX_HISTORY_EVENTS != mc_conf["max_history_events"]:
                cls.MAX_HISTORY_EVENTS = mc_conf["max_history_events"]
            if "debug_mode" in mc_conf and cls.DEBUG_MODE != mc_conf["debug_mode"]:
                cls.DEBUG_MODE = mc_conf["debug_mode"]
            if "auto_chat_thoughts" in mc_conf and cls.AUTO_CHAT_THOUGHTS != mc_conf["auto_chat_thoughts"]:
                cls.AUTO_CHAT_THOUGHTS = mc_conf["auto_chat_thoughts"]
            if "auto_speak_thoughts" in mc_conf and cls.AUTO_SPEAK_THOUGHTS != mc_conf["auto_speak_thoughts"]:
                cls.AUTO_SPEAK_THOUGHTS = mc_conf["auto_speak_thoughts"]
            
            # system prompt
            if "system_prompt_path" in mc_conf and mc_conf["system_prompt_path"]:
                path = mc_conf["system_prompt_path"]
                if cls.SYSTEM_PROMPT_PATH != path:
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            cls.SYSTEM_PROMPT = f.read()
                            cls.SYSTEM_PROMPT_PATH = path
                            print(f"Loaded Minecraft System Prompt from {path}")
                    except Exception as e:
                         print(f"Error loading Minecraft prompt from file: {e}")

            if "system_prompt" in mc_conf and mc_conf["system_prompt"]:
                cls.SYSTEM_PROMPT = mc_conf["system_prompt"]
            
            # namespaced logic
            if "mc_openai_model" in mc_conf and cls.OPENAI_MODEL != mc_conf["mc_openai_model"]:
                cls.OPENAI_MODEL = mc_conf["mc_openai_model"]
            
            # key logic - prioritize specific key
            new_key = None
            if "mc_openai_key" in mc_conf and mc_conf["mc_openai_key"]:
                new_key = mc_conf["mc_openai_key"]
            elif "openai_key" in data and data["openai_key"]:
                new_key = data["openai_key"]
            
            if new_key and cls.OPENAI_API_KEY != new_key:
                cls.OPENAI_API_KEY = new_key
                changed = True

        # helper for libs that read env directly
        # only update os environ if key actually changed to avoid syscall overhead/spam in loops
        if changed and cls.OPENAI_API_KEY:
            os.environ["OPENAI_API_KEY"] = cls.OPENAI_API_KEY
