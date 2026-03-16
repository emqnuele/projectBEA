import asyncio
import time
import collections
from datetime import datetime
from typing import Deque, Optional
from src.modules.skills.base_skill import BaseSkill
from src.utils.logger import get_logger

logger = get_logger("bea.skills.monologue")

class MonologueSkill(BaseSkill):
    def initialize(self):
        logger.info(f"Initializing {self.name} skill...")
        
        # config
        self.interval_seconds = self.skill_config.get("interval_seconds", 30)
        self.chunk_pause_seconds = self.skill_config.get("chunk_pause_seconds", 4.0)
        self.prompt_path = self.skill_config.get("prompt_path", "data/prompts/monologue.txt")
        
        # load prompt
        self.monologue_rules = ""
        try:
            with open(self.prompt_path, "r", encoding="utf-8") as f:
                self.monologue_rules = f.read()
            logger.info(f"Loaded Monologue prompt from {self.prompt_path}")
        except Exception as e:
            logger.error(f"Error loading Monologue prompt: {e}")
            self.monologue_rules = "Error loading prompt."

        # state management
        self.recent_topics: Deque[str] = collections.deque(maxlen=20)
        
        # current story state
        self.current_topic: Optional[str] = None
        self.story_conversation_history: list = []
        self.is_telling_story: bool = False
        self.last_speech_time: float = time.time()

    async def update(self):
        # 1. global busy check
        if self.context.is_speaking:
            self.last_speech_time = time.time()
            return

        # 2. check locks
        if self._execution_lock.locked():
            return

        now = time.time()
        time_since_speech = now - self.last_speech_time
        
        # 3. state machine
        async with self._execution_lock:
            if self.is_telling_story:
                # mode: storytelling
                if time_since_speech > self.chunk_pause_seconds:
                    await self._continue_story()
            else:
                # mode: idle
                last_global_interaction = self._get_last_interaction_time()
                global_idle_time = now - last_global_interaction
                
                if global_idle_time > self.interval_seconds:
                    self.log(f"Idle timeout ({global_idle_time:.1f}s). Starting new story.")
                    await self._start_new_story()

    def _get_last_interaction_time(self) -> float:
        """Returns unix timestamp of last message in main history."""
        # Note: We rely on the context's history manager.
        history = self.context.history_manager.history
        if not history:
            return 0.0
        
        last_msg = history[-1]
        ts_str = last_msg.get("timestamp")
        if ts_str:
            try:
                dt = datetime.fromisoformat(ts_str)
                return dt.timestamp()
            except ValueError:
                pass
        return time.time()

    async def _start_new_story(self):
        """Generates a topic and starts the first chunk."""
        try:
            # step a: generate topic
            topic = await self._generate_topic()
            if not topic:
                self.log("Failed to generate topic. Aborting.")
                self.last_speech_time = time.time()
                return

            self.current_topic = topic
            self.recent_topics.append(topic)
            self.is_telling_story = True
            self.story_conversation_history = []
            
            self.log(f"Starting new story about: {topic}")
            
            # step b: start telling it
            await self._continue_story()
            
        except Exception as e:
            self.log(f"Error starting story: {e}")
            self.is_telling_story = False

    async def _generate_topic(self) -> str:
        """Asks LLM for a short topic string, avoiding recent ones."""
        
        avoid_list = ", ".join([f"'{t}'" for t in self.recent_topics])
        
        sys_prompt = (
            "You are an AI Vtuber's inner consciousness. "
            "Your job is to select a NEW, interesting topic or anecdote to talk about to entertain the void (0 viewers). "
            "Think of: Gaming memories, tech opinions, funny life mishaps, anime reviews, or philosophical shower thoughts.\n"
            f"AVOID these recently used topics: [{avoid_list}]\n\n"
            "INSTRUCTIONS:\n"
            "1. Output ONLY the topic title/concept.\n"
            "2. Do NOT write the story yet.\n"
            "3. Do NOT ask questions."
        )

        try:
            # direct llm call
            history = []
            
            _, topic_text, _ = await asyncio.to_thread(
                self.context.llm.chat,
                user_input="[Gen Topic]",
                system_prompt=sys_prompt,
                history=history
            )
            
            return topic_text.strip()
            
        except Exception as e:
            logger.error(f"Topic Gen Error: {e}")
            return "Random random thoughts"

    async def _continue_story(self):
        """Generates the next chunk of the story."""
        if not self.current_topic:
            self.is_telling_story = False
            return

        try:
            # construct prompt

            # user trigger
            user_trigger = f"(System: Continue the story about '{self.current_topic}'. Remember: NO questions. If finished, add [END].)"
            
            # custom instruction
            base_prompt = self.context.system_prompt
            combined_prompt = f"{base_prompt}\n\n{self.monologue_rules}"

            logger.info(f"Generating chunk for topic: {self.current_topic}")
            mood, message = await self.context.generate_response(user_trigger, system_prompt=combined_prompt)
            
            # check for end token
            is_finished = "[END]" in message
            clean_message = message.replace("[END]", "").strip()
            
            if clean_message:
                await self.context.perform_output_task(mood, clean_message)
                self.last_speech_time = time.time()
            
            if is_finished:
                self.log(f"Story '{self.current_topic}' finished.")
                self.is_telling_story = False
                self.current_topic = None
                self.story_conversation_history = []
            
            # if empty message and not finished
            if not clean_message and not is_finished:
                 self.is_telling_story = False

        except Exception as e:
            self.log(f"Error in story chunk: {e}")
            self.is_telling_story = False

    def on_config_reload(self):
        """Updates interval settings from config."""
        self.interval_seconds = self.skill_config.get("interval_seconds", 30)
        self.chunk_pause_seconds = self.skill_config.get("chunk_pause_seconds", 4.0)
        self.log(f"Reloaded config. Interval: {self.interval_seconds}s")
