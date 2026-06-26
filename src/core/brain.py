import asyncio
from pathlib import Path
from typing import Dict, Tuple, Optional
from src.interfaces.base_interfaces import LLMInterface, TTSInterface, OBSInterface, STTInterface
from src.core.config import BrainConfig
from src.core.resources import load_avatar_resources, resolve_mood_paths
from src.utils.history_manager import HistoryManager
from src.modules.skills.skill_manager import SkillManager
from src.core.events import EventManager, EventCategory
from src.core.agent import AgentRunner, AgentHooks, ToolRegistry
from src.modules.skills.memory.memory_skill import MemorySkill
from src.utils.llm_utils import parse_llm_json
from src.utils.logger import get_logger
import datetime

logger = get_logger("bea.brain")

class AIVtuberBrain:
    def __init__(
        self, 
        config: BrainConfig, 
        llm: LLMInterface, 
        tts: TTSInterface,
        stt: STTInterface,
        obs: OBSInterface
    ):
        self.config = config
        self.llm = llm
        self.tts = tts
        self.stt = stt
        self.obs = obs
        self.png_map = {}
        self.system_prompt = ""
        self.history_manager = HistoryManager()
        self.is_speaking = False
        self.current_typing_task: Optional[asyncio.Task] = None
        self.current_speech_task: Optional[asyncio.Task] = None
        self.audio_lock = asyncio.Lock() 
        self.current_audio_buffer = None
        self.playback_start_time = 0
        self.playback_sample_rate = 24000
        self.resume_buffer = None
        
        # event manager
        self.event_manager = EventManager()
        
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
    def memory_skill(self) -> MemorySkill:
        return self.skill_manager.skills.get("memory")

    def _build_tool_registry(self) -> ToolRegistry:
        """Aggregates tools contributed by enabled skills for a chat turn."""
        registry = ToolRegistry()
        for skill in self.skill_manager.skills.values():
            if not skill.enabled:
                continue
            for tool in skill.get_tools():
                registry.register(tool)
        return registry

    async def _run_agent_turn(self, user_text: str, system_prompt: str, history: list) -> Tuple[str, str, Dict]:
        """Runs one conversational turn through the agent harness.

        Tools (if any enabled skills expose them) let Bea act mid-turn; the
        final spoken answer is JSON {mood, message}, parsed leniently.
        """
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_text})

        hooks = AgentHooks(
            on_tool_call=lambda name, args: self.event_manager.publish(
                EventCategory.SKILL, f"tool:{name}", str(args)
            ),
        )
        runner = AgentRunner(self.llm, self._build_tool_registry(), max_steps=6, hooks=hooks)
        final = await runner.run(messages)
        return parse_llm_json(final.content or "")

    def initialize(self):
        """Loads resources and connects to services."""
        logger.info("Initializing Brain...")

        self.png_map = load_avatar_resources(self.config.avatar_map)
        if not self.png_map:
            logger.warning("No avatar resources loaded from avatar_map.")

        sys_path = Path(self.config.system_prompt_path)
        try:
            if sys_path.exists():
                self.system_prompt = sys_path.read_text(encoding="utf-8")
                logger.info(f"Loaded system prompt from {sys_path}")
            else:
                logger.warning(f"System prompt file not found: {sys_path}")
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")


        self._obs_connect()

        self.history_manager.create_session()
        logger.info(f"Brain Initialized. Session ID: {self.history_manager.session_id}")

        self.skill_manager.initialize()

    def reload_configuration(self):
        """
        Hot-reloads configuration for all components.
        Called after config.json is updated via API.
        """
        logger.info("Hot Reloading Configuration")
        
        sys_path = Path(self.config.system_prompt_path)
        try:
            if sys_path.exists():
                new_prompt = sys_path.read_text(encoding="utf-8")
                if new_prompt != self.system_prompt:
                    self.system_prompt = new_prompt
                    logger.info("Updated System Prompt.")
        except Exception as e:
            logger.error(f"Error reloading system prompt: {e}")

        self.llm.reload_config(self.config)
        self.tts.reload_config(self.config)
        self.obs.reload_config(self.config)
        if self.stt:
            self.stt.reload_config(self.config)
        
        self.skill_manager.reload_config()
        
        logger.info("Hot Reload Complete")

    def _obs_connect(self):
        if hasattr(self.obs, 'source_name'):
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
        logger.info(f"Created new session: {self.history_manager.session_id}")
        
        if prev_session_id and prev_history:
             self.memory_skill.process_previous_session(prev_session_id, prev_history)
             
        return self.history_manager.session_id

    async def _play_audio(self, audio_data, sample_rate, device_id):
        """
        Internal helper to play audio via sounddevice with tracking.
        """
        import sounddevice as sd
        import time
        import numpy as np

        if len(audio_data) == 0:
            return

        self.current_audio_buffer = audio_data
        self.playback_sample_rate = sample_rate
        self.playback_start_time = time.time()
        
        if audio_data.ndim == 1:
            channels = 1
        else:
            channels = audio_data.shape[1]

        sd.play(audio_data, samplerate=sample_rate, device=device_id, blocking=False)
        
        duration = len(audio_data) / sample_rate
        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            sd.stop()
            raise

    async def perform_output_task(self, mood: str, message: str):
        """Background task to handle audio/visual output."""
        import sounddevice as sd
        self.is_speaking = True
        try:
            logger.info(f"Mood: {mood}")
            logger.info(f"Message: {message}")

            if self.current_typing_task and not self.current_typing_task.done():
                logger.info("Interrupting previous typing task...")
                self.current_typing_task.cancel()
            
            if self.current_speech_task and not self.current_speech_task.done():
                logger.info("Interrupting previous speech task...")
                self.current_speech_task.cancel()

            if self.config.obs_text_source:
                self.obs.set_text("", self.config.obs_text_source)

            try:
                idle_path, talking_path = resolve_mood_paths(self.png_map, mood)
            except KeyError:
                 logger.warning(f"Could not resolve mood {mood}, checking 'normal'...")
                 if "normal" in self.png_map:
                     idle_path, talking_path = self.png_map["normal"]
                 else:
                     idle_path = talking_path = Path("placeholder.png") 

            if self.config.obs_source_type == "media":
                self.obs.set_media(talking_path)
            else:
                self.obs.set_image(talking_path)


            async with self.audio_lock:
                self.current_typing_task = None
                if self.config.obs_text_source:
                    self.current_typing_task = asyncio.create_task(
                        self.obs.type_text(
                            text=message,
                            source_name=self.config.obs_text_source,
                            line_width=self.config.text_line_width,
                            max_lines=self.config.text_lines,
                            base_font_size=self.config.text_font_size,
                            min_font_size=self.config.text_min_font_size,
                            font_step=self.config.text_font_step,
                            typing_delay=self.config.typing_delay,
                            min_page_duration=self.config.text_min_duration
                        )
                    )

                self.event_manager.publish(EventCategory.OUTPUT, "tts", f"Speaking: {message[:50]}...", metadata={"device_id": self.config.audio_device_id})

                if message:
                    audio_data, fs = await self.tts.generate_audio(message)
                    self.current_speech_task = asyncio.create_task(
                        self._play_audio(audio_data, fs, self.config.audio_device_id)
                    )

                    font_used = self.config.text_font_size
                    try:
                        if self.current_typing_task:
                            results = await asyncio.gather(self.current_typing_task, self.current_speech_task)
                            font_used = results[0]
                        else:
                            await self.current_speech_task
                    except asyncio.CancelledError:
                        logger.info("Output tasks cancelled (Interruption).")
                        pass

            if self.config.obs_text_source:
                 self.obs.set_text("", self.config.obs_text_source, font_size=font_used)
            
            if self.config.obs_source_type == "media":
                self.obs.set_media(idle_path)
            else:
                self.obs.set_image(idle_path)
        finally:
            self.is_speaking = False

    async def interrupt(self):
        """
        Stops current speech/typing immediately.
        Intended for 'Barge-in' functionality.
        """
        logger.info("Interruption Signal Received!")
        import sounddevice as sd
        import time
        
        if self.is_speaking and self.current_audio_buffer is not None:
            try:
                elapsed = time.time() - self.playback_start_time
                consumed_samples = int(elapsed * self.playback_sample_rate)
                total_samples = len(self.current_audio_buffer)
                
                if consumed_samples < total_samples:
                    remaining = self.current_audio_buffer[consumed_samples:]
                    if len(remaining) > (0.5 * self.playback_sample_rate):
                        self.resume_buffer = remaining
                        logger.info(f"Buffered {len(remaining)/self.playback_sample_rate:.2f}s for resume.")
                    else:
                        self.resume_buffer = None
                else:
                    self.resume_buffer = None
            except Exception as e:
                logger.error(f"Error calculating resume buffer: {e}")
                self.resume_buffer = None
        
        try:
            sd.stop()
        except Exception as e:
             logger.error(f"Error stopping sounddevice: {e}")
        
        if self.current_speech_task and not self.current_speech_task.done():
            self.current_speech_task.cancel()
        
        if self.current_typing_task and not self.current_typing_task.done():
            self.current_typing_task.cancel()
            
        if self.config.obs_text_source:
             self.obs.set_text("", self.config.obs_text_source)
        
        self.history_manager.add_message("system", "[Interrupted by User]")
        
        self.is_speaking = False
        return "Interrupted"

    async def _resume_speech(self):
        """
        Resumes speech from the resume_buffer.
        """
        if self.resume_buffer is None:
            logger.info("No resume buffer found.")
            return

        logger.info("Resuming speech...")
        self.is_speaking = True
        try:
             async with self.audio_lock:

                 if "normal" in self.png_map:
                     _, talking_path = self.png_map["normal"]
                     if self.config.obs_source_type == "media":
                        self.obs.set_media(talking_path)
                     else:
                        self.obs.set_image(talking_path)

                 self.current_speech_task = asyncio.create_task(
                     self._play_audio(self.resume_buffer, self.playback_sample_rate, self.config.audio_device_id)
                 )
                 try:
                    await self.current_speech_task
                 except asyncio.CancelledError:
                    pass
                 
                 self.resume_buffer = None
        finally:
            self.is_speaking = False
            if "normal" in self.png_map:
                 idle_path, _ = self.png_map["normal"]
                 if self.config.obs_source_type == "media":
                    self.obs.set_media(idle_path)
                 else:
                    self.obs.set_image(idle_path)

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

    async def generate_response(self, user_text: str, system_prompt: str = None) -> Tuple[str, str]:
        """Generates the response but does NOT play it."""
        
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
        import os
        filename = os.path.basename(audio_path)       
        history = self.history_manager.get_recent_history()
        transcript = ""
        
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
             mood, message, metadata = self.llm.chat_audio(audio_path, system_prompt=final_prompt, history=history)
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
        
        audio_data, sample_rate = await self.tts.generate_audio(message)
        
        import io
        import soundfile as sf
        byte_io = io.BytesIO()
        sf.write(byte_io, audio_data, sample_rate, format='WAV')
        audio_bytes = byte_io.getvalue()
        
        asyncio.create_task(self._perform_visual_only_task(mood, message, len(audio_data)/sample_rate))

        leader = items[0]
        
        if not leader['future'].done():
             leader['future'].set_result(("success", message, full_transcript_log, audio_bytes))
             
        # resolve followers (empty audio)
        for item in items[1:]:
             if not item['future'].done():
                 item['future'].set_result(("success", "(Merged)", item['transcript'], b""))

    async def _perform_visual_only_task(self, mood: str, message: str, duration: float):
        """
        Updates OBS visuals/text without playing local audio.
        """
        self.is_speaking = True
        try:
             # resolve imagse
            try:
                _, talking_path = resolve_mood_paths(self.png_map, mood)
            except KeyError:
                 _, talking_path = self.png_map.get("normal", (Path("placeholder.png"), Path("placeholder.png")))

            # START ANIMATOIN
            if self.config.obs_source_type == "media":
                self.obs.set_media(talking_path)
            else:
                self.obs.set_image(talking_path)

            if self.config.obs_text_source:
                 await self.obs.type_text(
                    text=message,
                    source_name=self.config.obs_text_source,
                    line_width=self.config.text_line_width,
                    max_lines=self.config.text_lines,
                    base_font_size=self.config.text_font_size,
                    min_font_size=self.config.text_min_font_size,
                    font_step=self.config.text_font_step,
                    typing_delay=self.config.typing_delay,
                    min_page_duration=self.config.text_min_duration
                )
            else:
                await asyncio.sleep(duration)
                
            # END ANIMATION
            if "normal" in self.png_map:
                 idle_path, _ = self.png_map["normal"]
                 if self.config.obs_source_type == "media":
                    self.obs.set_media(idle_path)
                 else:
                    self.obs.set_image(idle_path)

            if self.config.obs_text_source:
                 self.obs.set_text("", self.config.obs_text_source)
                 
        finally:
            self.is_speaking = False

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
        """Starts the background skill manager loop."""
        await self.skill_manager.start()

    def shutdown(self):
        self.obs.disconnect()
        try:
             loop = asyncio.get_event_loop()
             if loop.is_running():
                 pass
        except:
            pass
