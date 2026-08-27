import asyncio
from typing import List, Optional, Tuple

from src.core.agent.registry import BACKGROUND, MIND, ModelRegistry
from src.core.attention import Attention
from src.core.config import BrainConfig
from src.core.consciousness import Consciousness
from src.core.events import EventCategory, EventManager
from src.core.expression import Expression
from src.core.memory.profiler import Profiler
from src.core.memory.store import MemoryStore
from src.core.mind import ConversationMind, ConversationScheduler
from src.core.mind.operating import BUILTIN_OPERATING, missing_tools
from src.core.mind.spontaneous import SpontaneousPresence
from src.core.perception.bus import PerceptionBus
from src.core.resources import load_avatar_resources
from src.core.skills.base import SkillRegistry
from src.core.skills.chat import ChatSurface
from src.core.skills.donation.surface import DonationSkill
from src.core.skills.dream.surface import DreamSkill
from src.core.skills.idle import IdleSurface
from src.core.skills.memory.memory import MemorySkill
from src.core.skills.minecraft.surface import MinecraftSurface
from src.core.skills.plan.surface import StreamPlanSkill
from src.core.skills.presence.surface import PresenceSkill
from src.core.skills.social.social import SocialMemory
from src.core.skills.telegram.surface import TelegramSkill
from src.core.skills.twitch.surface import TwitchSkill
from src.core.skills.voice.surface import VoiceSurface
from src.core.social.agenda import AgendaRunner
from src.core.social.reach import Reach
from src.core.social.rhythm import RhythmTick
from src.interfaces.base_interfaces import OBSInterface, STTInterface, TTSInterface
from src.utils.history_manager import HistoryManager
from src.utils.logger import get_logger
from src.utils.prompts import compose, load_text

logger = get_logger("bea.brain")


# every capability the brain wires up. PresenceSkill is core: without it she can
# only ever answer where she was spoken to.
SKILL_CLASSES = (
    ChatSurface, VoiceSurface, TelegramSkill, TwitchSkill, DonationSkill,
    IdleSurface, MinecraftSurface, MemorySkill, SocialMemory, DreamSkill,
    StreamPlanSkill, PresenceSkill,
)


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
        registry: ModelRegistry,
        tts: TTSInterface,
        stt: Optional[STTInterface],
        obs: OBSInterface,
    ):
        self.config = config
        self.registry = registry
        # the mind's client; skills reach for `registry.get("background")` instead
        self.llm = registry.get(MIND)
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

        # everything Bea remembers, in one transactional file
        self.memory = self._build_memory()

        # unified consciousness (built in initialize, started only if enabled)
        self.perception_bus: Optional[PerceptionBus] = None
        self.skill_registry: Optional[SkillRegistry] = None
        self.attention: Optional[Attention] = None
        self.profiler: Optional[Profiler] = None
        self.conversations: Optional[ConversationMind] = None
        self.spontaneous: Optional[SpontaneousPresence] = None
        self._rhythm_task: Optional[asyncio.Task] = None
        self.consciousness: Optional[Consciousness] = None

    @property
    def is_speaking(self) -> bool:
        return self.expression.is_speaking

    @property
    def surface_registry(self) -> Optional[SkillRegistry]:
        # legacy alias kept for the input entrypoints
        return self.skill_registry

    @property
    def memory_skill(self) -> Optional[MemorySkill]:
        skill = self.skill_registry.get("memory") if self.skill_registry else None
        return skill if isinstance(skill, MemorySkill) else None

    @property
    def dream_skill(self) -> Optional[DreamSkill]:
        skill = self.skill_registry.get("dream") if self.skill_registry else None
        return skill if isinstance(skill, DreamSkill) else None

    async def run_dream(self) -> dict:
        """Trigger a dream/consolidation pass (from the UI or a schedule)."""
        if not self.dream_skill or not self.dream_skill.active:
            return {"ok": False, "error": "dream skill not active"}
        return await self.dream_skill.run_dream()

    def wake_up(self) -> None:
        """Force Bea awake (UI button)."""
        if self.consciousness:
            self.consciousness.wake()

    @property
    def plan(self):
        """The owner's plan for the stream."""
        return self.memory.plan

    def plan_changed(self) -> None:
        """The dashboard edited the plan: her toolbox may have just changed.

        Going from no plan to a plan arms `objective_done` and friends, and the
        tool set is cached until something says it moved.
        """
        if self.consciousness:
            self.consciousness.tools.invalidate()

    @property
    def is_sleeping(self) -> bool:
        return bool(self.consciousness and self.consciousness.sleeping)

    def _build_memory(self) -> MemoryStore:
        """Opens `bea.db` and wires the embedder.

        The embedder is optional on purpose: if the model cannot be loaded, Bea
        keeps her roster, her people and her hot facts — she just loses recall
        until it comes back. Losing everything over a missing download would be
        a far worse failure.
        """
        cfg = self.config.skills.get("memory", {})
        embedder = None
        try:
            from src.core.memory.embedder import FastEmbedEmbedder
            embedder = FastEmbedEmbedder(
                cfg.get("embedding_model"),
                cfg.get("embedding_cache_dir", "data/embeddings_cache"),
            )
        except Exception as e:
            logger.error(f"Embedder unavailable ({e}); long-term recall is disabled.")

        store = MemoryStore(
            cfg.get("db_path", "data/bea.db"),
            embedder=embedder,
            min_similarity=float(cfg.get("min_similarity", 0.35)),
        )
        if store.rag is not None and embedder is not None:
            # vectors from two models are not comparable: a change re-embeds
            try:
                store.rag.ensure_model(embedder.model_name)
            except Exception as e:
                logger.error(f"Could not verify the embedding model: {e}")
        return store

    def _load_operating_rules(self) -> str:
        """The operating manual, with a floor under it.

        The file is meant to be edited; it is not meant to be able to vanish.
        Without the built-in copy a deleted file left her with no mood table, no
        inner-monologue rule and no explanation of the digest.
        """
        rules = load_text(self.config.operating_prompt_path)
        if not rules:
            rules = load_text(self.config.system_prompt_path, fallback=BUILTIN_OPERATING)
        return rules

    def check_prompt_integrity(self) -> List[str]:
        """Does the prompt in force still name the tools the mind owns?

        The manual is an editable file, so it can fall behind a rename or a bad
        save. Reporting that on the dashboard is the difference between finding
        out at startup and finding out mid-stream.
        """
        missing = missing_tools(self.system_prompt, sorted(Consciousness._TERMINAL_TOOLS))
        if missing:
            self.event_manager.publish(
                EventCategory.ERROR, "prompt",
                f"The operating manual never mentions: {', '.join(missing)}. "
                f"She may not know how to use them.",
                metadata={"missing": missing},
            )
        return missing

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
        self.check_prompt_integrity()

        self._obs_connect()

        self.history_manager.create_session()
        self.memory.sessions.record(self.history_manager.session_id)
        logger.info(f"Brain Initialized. Session ID: {self.history_manager.session_id}")

        self._build_consciousness()

    def _build_consciousness(self):
        """Wires the single-brain stack. Started later only if enabled in config."""
        self.perception_bus = PerceptionBus(window=self.config.consciousness.get("window", 0.3))
        self.skill_registry = SkillRegistry()

        for skill_cls in SKILL_CLASSES:
            skill = skill_cls(self.config, self.perception_bus, self.expression, self)
            skill.initialize()
            self.skill_registry.register(skill)

        # background passes that keep the cards and summaries fresh between dreams
        self.profiler = Profiler(self.model_for(BACKGROUND), self.memory)

        social = self.skill_registry.get("social")
        self.attention = Attention(
            self.config,
            roster=getattr(social, "roster", None),
            on_verdict=self._publish_verdict,
            conversations=self.memory.conversations,
        )

        self.consciousness = Consciousness(
            config=self.config,
            llm=self.llm,
            bus=self.perception_bus,
            expression=self.expression,
            surfaces=self.skill_registry,
            history_manager=self.history_manager,
            event_manager=self.event_manager,
            soul_getter=lambda: self.soul,
            operating_getter=self._load_operating_rules,
            attention=self.attention,
        )

        # written conversations run beside the live loop: one turn at a time per
        # channel, different channels in parallel
        self.conversations = ConversationMind(
            config=self.config,
            llm=self.llm,
            memory=self.memory,
            surfaces=self.skill_registry,
            soul_getter=lambda: self.soul,
            operating_getter=self._load_operating_rules,
            scheduler=ConversationScheduler(
                max_coalesced_runs=int(self.config.consciousness.get("max_coalesced_runs", 3))
            ),
            event_manager=self.event_manager,
            profiler=self.profiler,
            attention=self.attention,
            now_line=self.consciousness.now_line,
        )
        self.consciousness.conversations = self.conversations

        self.reach = Reach(memory=self.memory, surfaces=self.skill_registry)
        self.spontaneous = SpontaneousPresence(
            config=self.config, memory=self.memory, conversations=self.conversations,
        )
        self.rhythm = RhythmTick(
            agenda=AgendaRunner(
                agenda=self.memory.agenda, conversations=self.conversations,
                reach=self.reach,
            ),
            spontaneous=self.spontaneous,
        )

    def _publish_verdict(self, perception, verdict) -> None:
        """Surfaces every attention decision to the dashboard.

        Without seeing WHY something was ignored, tuning the thresholds is blind
        guessing — so this is not optional instrumentation."""
        self.event_manager.publish(
            EventCategory.SYSTEM, "attention",
            f"{verdict.reaction.value}: {perception.surface} ({verdict.reason})",
            metadata={
                "reaction": verdict.reaction.value,
                "score": round(verdict.score, 3),
                "reason": verdict.reason,
                "surface": perception.surface,
                "preview": (perception.content or "")[:120],
            },
        )

    def model_for(self, role: str = BACKGROUND):
        """A client for `role`, falling back to the mind's if the pool is empty.

        Background work (diary, dreamer, summaries) must not run on the mind's
        model, but a missing background pool should degrade, not crash.
        """
        try:
            return self.registry.get(role)
        except Exception as e:
            logger.warning(f"No '{role}' model ({e}); falling back to the mind's.")
            return self.llm

    @property
    def consciousness_active(self) -> bool:
        return bool(self.consciousness and self.consciousness.alive)

    async def set_skill_enabled(self, name: str, state: bool) -> bool:
        """Single source of truth: the UI toggles a skill (by its config key) and
        the matching capability is armed/disarmed live in the consciousness. Bea
        can only ever use what is toggled on here — she never enables anything."""
        skill = self.skill_registry.get_by_key(name) if self.skill_registry else None
        if not skill:
            return False
        self.config.skills.setdefault(name, {})["enabled"] = state
        self.config.save_to_file()

        if self.consciousness_active:
            await self.consciousness.set_surface_active(skill.name, state)
        return True

    def reload_configuration(self):
        """Hot-reloads configuration for all components after config.json changes."""
        logger.info("Hot Reloading Configuration")

        self.soul = load_text(self.config.soul_path)
        new_prompt = compose(self.soul, self._load_operating_rules())
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
            logger.info("Updated soul + operating manual.")
            self.check_prompt_integrity()

        self.registry.reload_config(self.config)
        self.llm = self.registry.get(MIND)
        if self.consciousness:
            self.consciousness.llm = self.llm
        self.tts.reload_config(self.config)
        self.obs.reload_config(self.config)
        self.expression.reload_config(self.config)
        if self.stt:
            self.stt.reload_config(self.config)

        logger.info("Hot Reload Complete")

    def _obs_connect(self):
        if hasattr(self.obs, "source_name"):
            self.obs.source_name = self.config.obs_avatar_source
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
        self.memory.sessions.record(self.history_manager.session_id)
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

    def _surface(self, name: str):
        """A skill by name, or None when the brain has not been initialized yet.

        The HTTP entrypoints are reachable the moment the server binds; without
        this guard an early request raises AttributeError instead of a 503.
        """
        return self.surface_registry.get(name) if self.surface_registry else None

    async def generate_response(self, user_text: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
        """Deposits a chat perception and waits for Bea to decide to reply."""
        chat = self._surface("chat:ui")
        if not chat or not self.consciousness:
            logger.warning("generate_response called before initialize().")
            return "normal", ""
        payload = await self._perceive_and_wait(
            lambda cid: chat.perceive(user_text, meta={"correlation_id": cid}),
            route="local",
        )
        if not payload:
            return "normal", ""
        return payload.get("mood", "normal"), payload.get("message", "")

    async def generate_audio_response(self, audio_path: str) -> Tuple[str, str, str]:
        """Transcribes audio, deposits a voice perception, waits for the reply."""
        transcript = self.stt.transcribe(audio_path) if self.stt else ""
        text = transcript or "[Audio Message]"
        voice = self._surface("voice:discord")
        if not voice or not self.consciousness:
            return "normal", "", transcript
        payload = await self._perceive_and_wait(
            lambda cid: voice.perceive(text, "user", meta={"correlation_id": cid}),
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

    async def process_discord_interaction(self, audio_path: str, username: str,
                                          user_id: Optional[str] = None) -> Tuple[str, str, str, bytes]:
        """Discord voice: transcribe, feed a voice perception, return Bea's spoken bytes."""
        transcript = ""
        if self.stt:
            transcript = self.stt.transcribe(audio_path)
            logger.info(f"Transcript from {username}: '{transcript}'")

        text = transcript or "[Unintelligible]"
        voice = self._surface("voice:discord")
        if not voice or not self.consciousness:
            return "ignored", "", transcript, b""
        payload = await self._perceive_and_wait(
            lambda cid: voice.perceive(text, username, meta={"correlation_id": cid},
                                       user_id=user_id),
            route="discord",
        )
        if not payload:
            return "ignored", "", transcript, b""
        return payload.get("status", "success"), payload.get("text", ""), transcript, payload.get("audio", b"")

    @property
    def donation_skill(self) -> Optional[DonationSkill]:
        skill = self.skill_registry.get("donation") if self.skill_registry else None
        return skill if isinstance(skill, DonationSkill) else None

    def perceive_discord_text(self, text: str, username: str, channel_id: str,
                              message_id: Optional[str] = None, user_id: Optional[str] = None,
                              is_dm: bool = False, whitelisted: bool = True) -> None:
        """Discord text: deposit a CHAT perception on the bus and return immediately.
        Bea decides on her own whether/how to answer, using the discord tools
        (reply/send_message/react) with the ids carried in the perception. This is
        the 'one mind' path: no synchronous request-reply, full autonomy."""
        surface = self._surface("voice:discord")
        if surface:
            surface.perceive_text(text, username, channel_id, message_id=message_id,
                                  user_id=user_id, is_dm=is_dm, whitelisted=whitelisted)

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

    async def _rhythm_loop(self):
        """The slow clock: every so often, does she want to start something?

        Nothing here is on the hot path — it is what makes her a person with a
        day rather than a process reacting to events.
        """
        rhythm = getattr(self.config, "rhythm", {}) or {}
        interval = float(rhythm.get("tick_seconds", 900))
        while True:
            await asyncio.sleep(interval)
            if self.is_sleeping:
                continue
            try:
                started = await self.rhythm.run_once()
                if started:
                    logger.info(f"Rhythm: opened {started} conversation(s) unprompted.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Rhythm tick failed: {e}")

    async def start_skills(self):
        """Starts the consciousness loop (which starts every enabled skill)."""
        if self.consciousness and self.config.consciousness.get("enabled", False):
            await self.consciousness.start()
            logger.info("Single-brain consciousness is active.")
            # prime cold network paths so the FIRST real message doesn't pay
            # dns/tls/model-routing latency (the 'slow only at first' symptom)
            asyncio.create_task(self._warmup())
            if (getattr(self.config, "rhythm", {}) or {}).get("enabled", True):
                self._rhythm_task = asyncio.create_task(self._rhythm_loop())

    async def _warmup(self):
        """Background priming of the LLM connection and the embedding endpoint."""
        if self.memory.rag is not None:
            # first embed pays the model load; do it before the first real message
            try:
                await asyncio.to_thread(self.memory.rag.recall, "warmup", scope="diary")
            except Exception as e:
                logger.debug(f"memory warmup skipped: {e}")
        try:
            await self.llm.complete([{"role": "user", "content": "hi"}])
        except Exception as e:
            logger.debug(f"llm warmup skipped: {e}")
        logger.info("Warmup complete (LLM + memory primed).")

    async def stop_skills(self):
        if self._rhythm_task:
            self._rhythm_task.cancel()
            self._rhythm_task = None
        if self.conversations:
            # let the in-flight replies land before the process goes away
            await self.conversations.drain()
        if self.consciousness:
            await self.consciousness.stop()

    def shutdown(self):
        self.obs.disconnect()
        self.memory.close()
