import asyncio
from typing import Dict, Tuple, Optional
from src.interfaces.base_interfaces import TTSInterface, OBSInterface, STTInterface
from src.core.config import BrainConfig
from src.core.resources import load_avatar_resources
from src.utils.history_manager import HistoryManager
from src.modules.skills.skill_manager import SkillManager
from src.core.events import EventManager, EventCategory
from src.core.expression import Expression
from src.core.perception.bus import PerceptionBus
from src.core.surfaces.base import SurfaceRegistry
from src.core.surfaces.chat import ChatSurface
from src.core.surfaces.voice import VoiceSurface
from src.core.surfaces.idle import IdleSurface
from src.core.surfaces.minecraft import MinecraftSurface
from src.core.consciousness import Consciousness
from src.core.agent import AgentRunner, AgentHooks, ToolRegistry, LLMClient
from src.modules.skills.memory.memory_skill import MemorySkill
from src.utils.llm_utils import parse_llm_json
from src.utils.prompts import load_text, compose
from src.utils.logger import get_logger
import datetime

logger = get_logger("bea.brain")


class _SpeechIntent:
    """Captures what Bea decides to say via the `speak` tool during a turn.

    Rendering still happens through the existing output pipeline; this only
    records the chosen mood/message so the turn can return it to its caller.
    """

    def __init__(self):
        self.spoke = False
        self.mood = "normal"
        self.message = ""

    def speak(self, mood: str, message: str) -> str:
        self.spoke = True
        self.mood = mood or "normal"
        # support multi-sentence turns: concatenate successive speak calls
        self.message = f"{self.message} {message}".strip() if self.message else message
        return "Spoken."

    def stay_silent(self, reason: str = "") -> str:
        self.spoke = True
        self.message = ""
        return "Staying silent."


class AIVtuberBrain:
    def __init__(
        self, 
        config: BrainConfig,
        llm: LLMClient,
        tts: TTSInterface,
        stt: Optional[STTInterface],
        obs: OBSInterface
    ):
        self.config = config
        self.llm = llm
        self.tts = tts
        self.stt = stt
        self.obs = obs
        self.png_map = {}
        self.soul = ""           # shared persona, prepended to every context's rules
        self.system_prompt = ""  # composed: soul + chat rules
        self.history_manager = HistoryManager()

        # event manager
        self.event_manager = EventManager()

        # single output sink (VOICE actuator + barge-in/resume)
        self.expression = Expression(config, tts, obs, self.event_manager)

        # unified consciousness (built in initialize, started only if enabled)
        self.perception_bus: Optional[PerceptionBus] = None
        self.surface_registry: Optional[SurfaceRegistry] = None
        self.consciousness: Optional[Consciousness] = None

        # skills
        self.skill_manager = SkillManager(config, self)

        # discord voice aggregation
        self.interaction_buffer = [] 
        self.buffer_lock = asyncio.Lock()
        self.flush_task = None
        self.BUFFER_WINDOW = 0.3
        self.pending_transcripts = []
        self.transcript_buffer_lock = asyncio.Lock()


    @property
    def is_speaking(self) -> bool:
        return self.expression.is_speaking

    @property
    def resume_buffer(self):
        return self.expression.resume_buffer

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

    def _build_tool_registry(self, speech: Optional["_SpeechIntent"] = None) -> ToolRegistry:
        """Aggregates tools for a chat turn: speak/silence/recall + skill tools."""
        registry = ToolRegistry()

        if speech is not None:
            registry.add(
                "speak",
                "Say something out loud to your audience with a facial expression.",
                {
                    "type": "object",
                    "properties": {
                        "mood": {"type": "string", "description": "one of: normal, shock, love, cry, angry, ew, bored"},
                        "message": {"type": "string", "description": "the spoken line"},
                    },
                    "required": ["mood", "message"],
                },
                speech.speak,
            )
            registry.add(
                "stay_silent",
                "Choose to say nothing right now.",
                {"type": "object", "properties": {"reason": {"type": "string"}}, "required": []},
                speech.stay_silent,
            )

        if self.memory_skill and self.memory_skill.enabled:
            registry.add(
                "recall_memory",
                "Search your long-term memory (past sessions) for relevant context.",
                {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                lambda query: self.memory_skill.retrieve_context(query),
            )

        for skill in self.skill_manager.skills.values():
            if not skill.enabled:
                continue
            for tool in skill.get_tools():
                registry.register(tool)
        return registry

    async def _run_agent_turn(self, user_text: str, system_prompt: str, history: list) -> Tuple[str, str, Dict]:
        """Runs one conversational turn through the agent harness.

        Bea speaks by calling the `speak` tool; if she never does, we fall back to
        parsing a legacy JSON {mood, message} from her final message.
        """
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_text})

        speech = _SpeechIntent()
        hooks = AgentHooks(
            on_tool_call=lambda name, args: self.event_manager.publish(
                EventCategory.SKILL, f"tool:{name}", str(args)
            ),
        )
        runner = AgentRunner(self.llm, self._build_tool_registry(speech), max_steps=6, hooks=hooks)
        final = await runner.run(messages)

        if speech.spoke:
            return speech.mood, speech.message, {}
        # legacy fallback: parse JSON from the final plain-text answer
        return parse_llm_json(final.content or "")

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

    def reload_configuration(self):
        """
        Hot-reloads configuration for all components.
        Called after config.json is updated via API.
        """
        logger.info("Hot Reloading Configuration")
        
        self.soul = load_text(self.config.soul_path)
        new_prompt = compose(self.soul, self._load_operating_rules())
        if new_prompt != self.system_prompt:
            self.system_prompt = new_prompt
            logger.info("Updated soul + chat rules.")

        self.llm.reload_config(self.config)
        self.tts.reload_config(self.config)
        self.obs.reload_config(self.config)
        self.expression.reload_config(self.config)
        if self.stt:
            self.stt.reload_config(self.config)
        
        self.skill_manager.reload_config()
        
        logger.info("Hot Reload Complete")

    def _obs_connect(self):
        if hasattr(self.obs, 'source_name'):
             setattr(self.obs, 'source_name', self.config.obs_avatar_source)
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
        """Renders a spoken turn locally through the single Expression sink.

        In single-brain mode the consciousness already rendered the speech, so this
        becomes a no-op to avoid double output.
        """
        if self.consciousness_active:
            return
        await self.expression.speak(mood, message, route="local")

    async def interrupt(self):
        """Barge-in: stops current speech via Expression and logs it."""
        result = await self.expression.interrupt()
        self.history_manager.add_message("system", "[Interrupted by User]")
        return result

    async def _resume_speech(self):
        await self.expression.resume()

    def _is_backchannel(self, text: str) -> bool:
        """
        Heuristic to decide if input is just a backchannel (resume signal).
        """
        text = text.strip().lower()
        if len(text) > 30: 
            return False
            
        backchannels = {
            "ok", "okay", "k", "kk", 
            "yes", "yeah", "yep", "yup", "sì", "si", "certo",
            "mh", "mm", "mmm", "mhm", "uh-huh",
            "go on", "continue", "procedi", "continua", "vai avanti"
        }
        
        if text in backchannels:
            return True
            
        return False

    async def generate_response(self, user_text: str, system_prompt: Optional[str] = None) -> Tuple[str, str]:
        """Generates the response but does NOT play it."""

        # single-brain path: deposit a perception and wait for Bea to decide to reply
        if self.consciousness_active:
            payload = await self._perceive_and_wait(
                lambda cid: self.surface_registry.get("chat:ui").perceive(
                    user_text, meta={"correlation_id": cid}),
                route="local",
            )
            if not payload:
                return "normal", ""
            return payload.get("mood", "normal"), payload.get("message", "")

        if self.resume_buffer is not None and self._is_backchannel(user_text):
            logger.info(f"Backchannel detected ('{user_text}'). Resuming...")
            self.history_manager.add_message("user", user_text)
            await self._resume_speech()
            return "neutral", "[RESUMED]"


        self.event_manager.publish(EventCategory.INPUT, "user", user_text)
        history = self.history_manager.get_recent_history()
        self.history_manager.add_message("user", user_text)
        
        final_prompt = system_prompt if system_prompt else self.system_prompt
        
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        final_prompt = f"CURRENT DATE: {today_str}\n\n{final_prompt}"

        # --- MEMORY INJECTION (RAG) ---
        if self.memory_skill and self.memory_skill.enabled:
             # 2. retrieve context
             context = self.memory_skill.retrieve_context(user_text)
             
             # 3. inject context at the end
             memory_section = f"\n\n[LONG TERM MEMORY]\n{context}\n"
             final_prompt += memory_section

        
        mood, message, metadata = await self._run_agent_turn(user_text, final_prompt, history)

        # save with metadata
        if "mood" in metadata:
            del metadata["mood"]
        self.history_manager.add_message("assistant", message, mood=mood, **metadata)
        
        self.event_manager.publish(EventCategory.OUTPUT, "llm", message, metadata={"mood": mood})
        return mood, message

    async def generate_audio_response(self, audio_path: str) -> Tuple[str, str, str]:
        history = self.history_manager.get_recent_history()
        transcript = ""

        if self.consciousness_active:
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

        if self.stt:
             transcript = self.stt.transcribe(audio_path)
             if transcript:
                  logger.info(f"Audio Transcript: '{transcript}'")
                  if self.resume_buffer is not None and self._is_backchannel(transcript):
                       logger.info("Audio Backchannel detected. Resuming...")
                       self.history_manager.add_message("user", transcript)
                       await self._resume_speech()
                       return "neutral", "[RESUMED]", transcript
        
        # prepare context (same as generate_response)
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        final_prompt = f"CURRENT DATE: {today_str}\n\n{self.system_prompt}"
        
        if self.memory_skill and self.memory_skill.enabled:
             # use transcript for retrieval if available, else generic
             query = transcript if transcript else "Audio Message"
             context = self.memory_skill.retrieve_context(query) 
             memory_section = f"\n\n[LONG TERM MEMORY]\n{context}\n"
             final_prompt += memory_section

        # save user turn to history (mirrors generate_response behaviour)
        user_content = transcript if transcript else "[Audio Message]"
        self.event_manager.publish(EventCategory.INPUT, "user", user_content)
        self.history_manager.add_message("user", user_content)

        # call LLM
        
        if transcript:
             mood, message, metadata = await self._run_agent_turn(transcript, final_prompt, history)
        else:
             # no STT transcript available; current providers have no multimodal audio path
             mood, message, metadata = "neutral", "Sorry, I couldn't make out any audio.", {}
             transcript = "[Audio Message]"
        
        if "mood" in metadata:
            del metadata["mood"]
        self.history_manager.add_message("assistant", message, mood=mood, **metadata)
        
        return mood, message, transcript

    # deprecated single-call methods kept for compatibility if needed, but updated to use new flow
    async def process_text_input(self, user_text: str):
        mood, message = await self.generate_response(user_text)
        await self.perform_output_task(mood, message)
        return mood, message

    async def process_audio_input(self, audio_path: str):
        mood, message, _ = await self.generate_audio_response(audio_path)
        await self.perform_output_task(mood, message)
        return mood, message

    async def process_discord_interaction(self, audio_path: str, username: str) -> Tuple[str, str, str, bytes]:
        """
        BUFFERED pipeline for Discord Voice.
        Aggregates simultaneous speakers into one LLM context.
        """
        # 1. transcribe immediately
        transcript = ""
        if self.stt:
            transcript = self.stt.transcribe(audio_path)
            logger.info(f"Transcript from {username}: '{transcript}'")

        # single-brain path: feed a voice perception, wait for Bea's spoken reply (bytes)
        if self.consciousness_active:
            text = transcript or "[Unintelligible]"
            payload = await self._perceive_and_wait(
                lambda cid: self.surface_registry.get("voice:discord").perceive(
                    text, username, meta={"correlation_id": cid}),
                route="discord",
            )
            if not payload:
                return "ignored", "", transcript, b""
            return payload.get("status", "success"), payload.get("text", ""), transcript, payload.get("audio", b"")
        
        if not transcript:
             transcript = "[Unintelligible]"

        is_backchannel = self._is_backchannel(transcript)

        # 2. add to buffer
        future = asyncio.Future()
        
        async with self.buffer_lock:
            self.interaction_buffer.append({
                "future": future,
                "username": username,
                "transcript": transcript,
                "is_backchannel": is_backchannel
            })
            
            # start flush timer if not running
            if not self.flush_task:
                 self.flush_task = asyncio.create_task(self._schedule_flush())

        # 3. wait for flush result
        try:
            return await future
        except Exception as e:
            logger.error(f"Error waiting for flush: {e}")
            return "error", "", "", b""

    async def _schedule_flush(self):
        """Waits for window then flushes."""
        await asyncio.sleep(self.BUFFER_WINDOW)
        async with self.buffer_lock:
            await self._flush_buffer()
            self.flush_task = None

    async def _flush_buffer(self):
        """
        Combines all buffered inputs and calls LLM once.
        Includes any pending_transcripts accumulated while Bea was speaking.
        """
        if not self.interaction_buffer:
            return

        items = self.interaction_buffer[:]
        self.interaction_buffer.clear()
        
        logger.info(f"Flushing {len(items)} items...")

        all_backchannel = all(item['is_backchannel'] for item in items)
        
        if all_backchannel:
             logger.info("All inputs are backchannels. Resuming.")
             for item in items:
                 if not item['future'].done():
                     item['future'].set_result(("resume", "[RESUMED]", item['transcript'], b""))
             return

        buffered_context = ""
        async with self.transcript_buffer_lock:
            if self.pending_transcripts:
                buffered_context = "\n".join(self.pending_transcripts)
                logger.info(f"Draining {len(self.pending_transcripts)} buffered transcript(s)")
                self.pending_transcripts.clear()

        combined_text = ""
        full_transcript_log = ""
        
        if buffered_context:
            combined_text += f"[While you were talking, you overheard:]\n{buffered_context}\n\n[Then they said:]\n"
        
        for item in items:
            combined_text += f"[{item['username']}]: {item['transcript']}\n"
            full_transcript_log += f"{item['username']}: {item['transcript']} | "

        logger.info(f"Combined Context:\n{combined_text.strip()}")

        mood, message = await self.generate_response(combined_text.strip())

        audio_bytes = await self.expression.speak(mood, message, route="remote")

        leader = items[0]
        
        if not leader['future'].done():
             leader['future'].set_result(("success", message, full_transcript_log, audio_bytes))
             
        # resolve followers (empty audio)
        for item in items[1:]:
             if not item['future'].done():
                 item['future'].set_result(("success", "(Merged)", item['transcript'], b""))

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
        """Starts the background skill manager loop (and the consciousness if enabled)."""
        await self.skill_manager.start()

        if self.consciousness and self.config.consciousness.get("enabled", False):
            await self.consciousness.start()
            logger.info("Single-brain consciousness is active.")

    def shutdown(self):
        self.obs.disconnect()
        try:
             loop = asyncio.get_event_loop()
             if loop.is_running():
                 pass
        except:
            pass
