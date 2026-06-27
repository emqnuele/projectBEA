import asyncio
from typing import Tuple, Optional
from src.interfaces.base_interfaces import TTSInterface, OBSInterface, STTInterface
from src.core.config import BrainConfig
from src.core.resources import load_avatar_resources
from src.utils.history_manager import HistoryManager
from src.modules.skills.skill_manager import SkillManager
from src.core.events import EventManager
from src.core.expression import Expression
from src.core.perception.bus import PerceptionBus
from src.core.surfaces.base import SurfaceRegistry
from src.core.surfaces.chat import ChatSurface
from src.core.surfaces.voice import VoiceSurface
from src.core.surfaces.idle import IdleSurface
from src.core.surfaces.minecraft import MinecraftSurface
from src.core.consciousness import Consciousness
from src.core.agent import LLMClient
from src.modules.skills.memory.memory_skill import MemorySkill
from src.utils.prompts import load_text, compose
from src.utils.logger import get_logger

logger = get_logger("bea.brain")


class AIVtuberBrain:
    """Composition root for the single-brain stack.

    Builds the perception bus, the surfaces, the expression sink and the one
    consciousness loop, then wires the HTTP/CLI entrypoints to deposit
    perceptions and wait for Bea's spoken reply via correlation. There is no
    separate reactive chat path anymore: the consciousness is the only mind.
    """

    def __init__(
        self,
        config: BrainConfig,
        llm: LLMClient,
        tts: TTSInterface,
        stt: Optional[STTInterface],
        obs: OBSInterface,
    ):
        self.config = config
        self.llm = llm
        self.tts = tts
        self.stt = stt
        self.obs = obs
        self.png_map = {}
        self.soul = ""           # shared persona, prepended to the operating manual
        self.system_prompt = ""  # composed: soul + operating manual
        self.history_manager = HistoryManager()

        self.event_manager = EventManager()

        # single output sink (VOICE actuator + barge-in)
        self.expression = Expression(config, tts, obs, self.event_manager)

        # unified consciousness (built in initialize, started only if enabled)
        self.perception_bus: Optional[PerceptionBus] = None
        self.surface_registry: Optional[SurfaceRegistry] = None
        self.consciousness: Optional[Consciousness] = None

        # background services (memory RAG, discord transport)
        self.skill_manager = SkillManager(config, self)

    @property
    def is_speaking(self) -> bool:
        return self.expression.is_speaking

    @property
    def memory_skill(self) -> Optional[MemorySkill]:
        skill = self.skill_manager.skills.get("memory")
        return skill if isinstance(skill, MemorySkill) else None

    def _load_operating_rules(self) -> str:
        """The unified operating manual; falls back to the legacy chat rules."""
        rules = load_text(self.config.operating_prompt_path)
        if not rules:
            rules = load_text(self.config.system_prompt_path)
        return rules

    def initialize(self):
        """Loads resources and connects to services."""
        logger.info("Initializing Brain...")

        self.png_map = load_avatar_resources(self.config.avatar_map)
        if not self.png_map:
            logger.warning("No avatar resources loaded from avatar_map.")
        self.expression.set_png_map(self.png_map)

        self.soul = load_text(self.config.soul_path)
        self.system_prompt = compose(self.soul, self._load_operating_rules())
        logger.info(f"Loaded soul + operating manual ({len(self.system_prompt)} chars).")

        self._obs_connect()

        self.history_manager.create_session()
        logger.info(f"Brain Initialized. Session ID: {self.history_manager.session_id}")

        self.skill_manager.initialize()

        self._build_consciousness()

    def _build_consciousness(self):
        """Wires the single-brain stack. Started later only if enabled in config."""
        self.perception_bus = PerceptionBus(window=self.config.consciousness.get("window", 0.3))
        self.surface_registry = SurfaceRegistry()

        for surface_cls in (ChatSurface, VoiceSurface, IdleSurface, MinecraftSurface):
            surface = surface_cls(self.config, self.perception_bus, self.expression, self)
            surface.initialize()
            self.surface_registry.register(surface)

        self.consciousness = Consciousness(
            config=self.config,
            llm=self.llm,
            bus=self.perception_bus,
            expression=self.expression,
            surfaces=self.surface_registry,
            history_manager=self.history_manager,
            event_manager=self.event_manager,
            memory_skill_getter=lambda: self.memory_skill,
            soul_getter=lambda: self.soul,
            operating_getter=self._load_operating_rules,
        )

    @property
    def consciousness_active(self) -> bool:
        return bool(self.consciousness and self.consciousness.alive)

    # maps a UI skill toggle to the surface that gates the matching capability
    _SKILL_SURFACE = {"monologue": "idle", "minecraft": "game:mc", "discord": "voice:discord"}

    async def set_skill_enabled(self, name: str, state: bool) -> bool:
        """Single source of truth: the UI toggles a skill, and the matching
        consciousness surface is armed/disarmed live. Bea can only ever use what
        is toggled on here — she never enables anything herself."""
        if name not in self.skill_manager.skills:
            return False
        self.config.skills.setdefault(name, {})["enabled"] = state
        self.config.save_to_file()

        # transport-owning skills (discord bot process) are handled by the skill loop;
        # here we reflect the capability gate into the live consciousness.
        if self.consciousness_active:
            surface_name = self._SKILL_SURFACE.get(name)
            if surface_name:
                await self.consciousness.set_surface_active(surface_name, state)
        return True

    def reload_configuration(self):
        """Hot-reloads configuration for all components after config.json changes."""
        logger.info("Hot Reloading Configuration")

        self.soul = load_text(self.config.soul_path)
        new_prompt = compose(self.soul, self._load_operating_rules())
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
            logger.info("Updated soul + operating manual.")

        self.llm.reload_config(self.config)
        self.tts.reload_config(self.config)
        self.obs.reload_config(self.config)
        self.expression.reload_config(self.config)
        if self.stt:
            self.stt.reload_config(self.config)

        self.skill_manager.reload_config()

        logger.info("Hot Reload Complete")

    def _obs_connect(self):
        if hasattr(self.obs, "source_name"):
            setattr(self.obs, "source_name", self.config.obs_avatar_source)
        self.obs.connect()

    def list_sessions(self):
        return self.history_manager.list_sessions()

    def load_session(self, session_id):
        if self.history_manager.load_session(session_id):
            logger.info(f"Loaded session: {session_id}")
            return True
        return False

    def create_new_session(self):
        prev_session_id = self.history_manager.session_id
        prev_history = self.history_manager.history

        self.history_manager.create_session()
        logger.info(f"Created new session: {self.history_manager.session_id}")

        if prev_session_id and prev_history and self.memory_skill:
            self.memory_skill.process_previous_session(prev_session_id, prev_history)

        return self.history_manager.session_id

    # --- input entrypoints: deposit a perception, await Bea's reply ----------

    async def _perceive_and_wait(self, putter, route: str):
        """Deposits a perception (via `putter(correlation_id)`) and waits for the reply."""
        cid, fut = self.consciousness.register_correlation(route)
        putter(cid)
        try:
            return await asyncio.wait_for(fut, timeout=self.consciousness.correlation_timeout)
        except asyncio.TimeoutError:
            logger.info("Correlation timed out (Bea did not respond).")
            return None

    async def perform_output_task(self, mood: str, message: str):
        """Kept for the CLI loop: the consciousness already renders speech, so
        rendering here would double the output. No-op while the brain is alive."""
        if self.consciousness_active:
            return
        await self.expression.speak(mood, message, route="local")

    async def interrupt(self):
        """Barge-in: stops current speech via Expression and logs it."""
        result = await self.expression.interrupt()
        self.history_manager.add_message("system", "[Interrupted by User]")
        return result

    async def generate_response(self, user_text: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
        """Deposits a chat perception and waits for Bea to decide to reply."""
        payload = await self._perceive_and_wait(
            lambda cid: self.surface_registry.get("chat:ui").perceive(
                user_text, meta={"correlation_id": cid}),
            route="local",
        )
        if not payload:
            return "normal", ""
        return payload.get("mood", "normal"), payload.get("message", "")

    async def generate_audio_response(self, audio_path: str) -> Tuple[str, str, str]:
        """Transcribes audio, deposits a voice perception, waits for the reply."""
        transcript = self.stt.transcribe(audio_path) if self.stt else ""
        text = transcript or "[Audio Message]"
        payload = await self._perceive_and_wait(
            lambda cid: self.surface_registry.get("voice:discord").perceive(
                text, "user", meta={"correlation_id": cid}),
            route="local",
        )
        if not payload:
            return "normal", "", transcript
        return payload.get("mood", "normal"), payload.get("message", ""), transcript

    async def process_text_input(self, user_text: str):
        mood, message = await self.generate_response(user_text)
        await self.perform_output_task(mood, message)
        return mood, message

    async def process_audio_input(self, audio_path: str):
        mood, message, _ = await self.generate_audio_response(audio_path)
        await self.perform_output_task(mood, message)
        return mood, message

    async def process_discord_interaction(self, audio_path: str, username: str) -> Tuple[str, str, str, bytes]:
        """Discord voice: transcribe, feed a voice perception, return Bea's spoken bytes."""
        transcript = ""
        if self.stt:
            transcript = self.stt.transcribe(audio_path)
            logger.info(f"Transcript from {username}: '{transcript}'")

        text = transcript or "[Unintelligible]"
        payload = await self._perceive_and_wait(
            lambda cid: self.surface_registry.get("voice:discord").perceive(
                text, username, meta={"correlation_id": cid}),
            route="discord",
        )
        if not payload:
            return "ignored", "", transcript, b""
        return payload.get("status", "success"), payload.get("text", ""), transcript, payload.get("audio", b"")

    async def run_loop(self):
        logger.info("Starting interactive loop. Type 'exit' to quit.")
        logger.info("To send audio, type 'audio:path/to/file.wav'")

        while True:
            user_text = await asyncio.to_thread(input, "You > ")
            user_text = user_text.strip()

            if user_text.lower() in ("exit", "quit"):
                break
            if not user_text:
                continue

            if user_text.lower().startswith("audio:"):
                audio_path = user_text[6:].strip()
                logger.info(f"I will process audio from: {audio_path}")
                await self.process_audio_input(audio_path)
            else:
                await self.process_text_input(user_text)

    async def start_skills(self):
        """Starts background services and the consciousness loop (if enabled)."""
        await self.skill_manager.start()

        if self.consciousness and self.config.consciousness.get("enabled", False):
            await self.consciousness.start()
            logger.info("Single-brain consciousness is active.")

    def shutdown(self):
        self.obs.disconnect()
