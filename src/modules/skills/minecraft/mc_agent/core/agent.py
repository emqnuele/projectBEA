import json
import time
from typing import Dict, Any, List
from .state_machine import StateMachine, AgentState
from .config import Config
from ..interfaces.minecraft_ws import MinecraftClient
from ..interfaces.openai_client import OpenAIClient
from ..utils.logger import setup_logger


logger = setup_logger("Agent")

INITIAL_SURVIVAL_PLAN = """- [ ] GET WOOD: Mine 4-5 logs using find_block('log')
- [ ] CRAFT BASICS (1): Planks(x3) -> Crafting Table 
- [ ] CRAFT BASICS (2): Planks -> Sticks
- [ ] CRAFT BASICS (3): Wooden Pickaxe
- [ ] GET STONE: Mine 3 Stone/Cobble
- [ ] UPGRADE: Craft Stone Pickaxe (Discard Wooden)
- [ ] GATHER: Coal (Torches) & Iron (Armor/Shield)
- [ ] FOOD: Hunt animals if Hunger < 15"""

# define the tools available to the llm
MINECRAFT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "mine_block",
            "description": "Navigate to and mine a specific block.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"}
                },
                "required": ["x", "y", "z"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "attack_entity",
            "description": "Attack a specific entity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "integer", "description": "Entity ID of the target."}
                },
                "required": ["target"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_to",
            "description": "Move to specific coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"}
                },
                "required": ["x", "y", "z"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "stop_moving",
            "description": "Stop all movement immediately.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
     {
        "type": "function",
        "function": {
            "name": "request_screenshot",
            "description": "Request a visual screenshot of the current view.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "look_at",
            "description": "Look at specific coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"}
                },
                "required": ["x", "y", "z"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "place_block",
            "description": "Place a block at specific coordinates. Can specify block type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"},
                    "block": {"type": "string", "description": "Optional block name to place"}
                },
                "required": ["x", "y", "z"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "select_slot",
            "description": "Select a hotbar slot (0-8).",
            "parameters": {
                "type": "object",
                "properties": {
                    "slot": {"type": "integer", "minimum": 0, "maximum": 8}
                },
                "required": ["slot"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_block",
            "description": "Find the nearest block of a given type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "block": {"type": "string"},
                    "max_distance": {"type": "integer", "default": 100, "description": "Maximum search radius. Use 100 for long range."}
                },
                "required": ["block"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "pillar_up",
            "description": "Pillar up a certain height.",
            "parameters": {
                "type": "object",
                "properties": {
                    "height": {"type": "integer"},
                    "block": {"type": "string"}
                },
                "required": ["height"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mine_down",
            "description": "Mine downwards a certain depth.",
            "parameters": {
                "type": "object",
                "properties": {
                    "depth": {"type": "integer"}
                },
                "required": ["depth"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "bridge",
            "description": "Build a bridge in a direction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["NORTH", "SOUTH", "EAST", "WEST"]},
                    "count": {"type": "integer"}
                },
                "required": ["direction", "count"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "craft_item",
            "description": "Craft an item using a nearby crafting table or inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"}
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "use_block",
            "description": "Interact (Right Click) with a block at coordinates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "z": {"type": "integer"}
                },
                "required": ["x", "y", "z"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "smelt_item",
            "description": "Smelt an item in a furnace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "input_item": {"type": "string"},
                    "fuel_item": {"type": "string"}
                },
                "required": ["input_item", "fuel_item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "store_item",
            "description": "Store items in a container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"}
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "retrieve_item",
            "description": "Retrieve items from a container.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"}
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "equip_item",
            "description": "Equip an item from inventory to main hand.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"}
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "discard_item",
            "description": "Discard (throw away) items.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "all": {"type": "boolean", "description": "Discard all stacks of this item?"}
                },
                "required": ["item"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "eat_food",
            "description": "Eat the best available food.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_death_log",
            "description": "Check the last death details.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "chat",
            "description": "Send a chat message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"}
                },
                "required": ["message"]
            }
        }
    }
]

class Agent:
    def __init__(self, on_thought_callback=None):
        self.state_machine = StateMachine()
        self.mc_client = MinecraftClient(Config.MC_SERVER_URL, self.on_mc_message)
        self.llm_client = OpenAIClient()
        self.latest_state: Dict[str, Any] = {}
        self.event_history: List[str] = []
        self.on_thought_callback = on_thought_callback
        
        # action history & plan
        from collections import deque
        self.action_history = deque(maxlen=10)
        self.current_plan = INITIAL_SURVIVAL_PLAN
        self.last_action_context: Dict[str, Any] = None

        self.task_start_time = 0
        self.running = False
        
        # load system prompt
        self.system_prompt = self._load_system_prompt()
    
    def _load_system_prompt(self) -> str:
        """Loads the system prompt from Config or JSON file."""
        # 1. check config override
        if hasattr(Config, "SYSTEM_PROMPT") and Config.SYSTEM_PROMPT:
            return Config.SYSTEM_PROMPT
            
        # 2. fallback
        logger.warning("Config.SYSTEM_PROMPT was not set. Check skill configuration.")
        return "You are a Minecraft Agent."

    def _update_history(self, action_name: str, params: Dict, result: str):
        """Adds an entry to the rolling action history."""
        # format: [HH:MM:SS] action(params) -> RESULT
        timestamp = time.strftime("%H:%M:%S")
        param_str = ", ".join(f"{k}={v}" for k, v in params.items())
        entry = f"[{timestamp}] {action_name}({param_str}) -> {result}"
        self.action_history.append(entry)
        logger.debug(f"History Update: {entry}")

    def start(self):
        """Starts the agent background threads."""
        logger.info("Starting Agent...")
        self.running = True
        self.mc_client.connect()

    def stop(self):
        """Stops the agent and its components."""
        logger.info("Stopping Agent...")
        self.running = False
        self.mc_client.stop()
        logger.info("Agent Stopped.")

    def on_mc_message(self, data: Dict[str, Any]):
        """Handler for incoming Minecraft data."""
        # debug: inspect incoming connection data
        if "status" in data:
             logger.debug(f"RX Packet: {data}")
        
        # 1. update internal knowledge base
        packet_type = None
        if "player" in data:
            self.latest_state = data
            packet_type = "STATE_UPDATE"
        elif "status" in data:
            packet_type = "EVENT_BINDING" # e.g., Task Finished from Mod
        
        # 2. check for interrupts/events in the packet
        # mod sends {"status": "INTERRUPTED", "event": {"reason": "...", ...}}
        if data.get("status") == "INTERRUPTED":
            event_details = data.get("event", {})
            
            # default fallback
            reason = data.get("reason", event_details.get("reason", "Unknown Emergency"))
            
            # enhanced context
            if event_details:
                detailed_reason = f"Action interrupted by {event_details.get('type', 'system')}: {reason}"
                if "last_action" in event_details:
                    detailed_reason += f" while performing '{event_details['last_action']}'"
                if "coordinates" in event_details:
                     coords = event_details["coordinates"]
                     detailed_reason += f" at ({coords.get('x', '?'):.1f}, {coords.get('y', '?'):.1f}, {coords.get('z', '?'):.1f})"
                reason = detailed_reason
            
            logger.warning(f"INTERRUPTED: {reason}")
            self.state_machine.transition_to(AgentState.INTERRUPTED, reason)
            self.event_history.append(f"INTERRUPTED: {reason}")
            self.trigger_llm()
            return
        
        # 3. handle auto-action engagement (silent takeover)
        # if mod says "ENGAGED_AUTO_ACTION", we switch to BUSY but DO NOT call LLM.
        if data.get("status") == "ENGAGED_AUTO_ACTION":
            reason = data.get("reason", "Auto-Action Engaged")
            logger.info(f"Mod engaged Auto-Action: {reason}")
            
            # transition to BUSY so we expect a FINISHED signal later
            self.state_machine.transition_to(AgentState.BUSY, f"Auto-Action: {reason}")
            self.state_machine.set_task(f"Auto-Action: {reason}")
            
            # log event for context when it finishes
            self.event_history.append(f"Auto-Action Engaged: {reason}")
            return

        # 4. handle task completion events
        remote_status = data.get("status")
        if remote_status == "IDLE" or remote_status == "FINISHED":
            result = data.get("result", "SUCCESS")
            message = data.get("message", "")
            status_msg = f"Task Finished: {result}"
            if message:
                status_msg += f". Message: {message}"
            
            logger.info(f"Task Completion Event: {status_msg}")
            self.event_history.append(status_msg)
            
            # update action history
            if self.last_action_context:
                self._update_history(
                    self.last_action_context.get("name", "unknown"),
                    self.last_action_context.get("params", {}),
                    result
                )
                self.last_action_context = None # reset
            
            # we do NOT trigger LLM here anymore. We wait for state update to confirm IDLE.
            return

        # 4. state update & synchronization
        if packet_type == "STATE_UPDATE" or packet_type == "game_state": # handle both type names if they vary
             current_time = time.time()
             is_busy = data.get("is_busy", False)
             
             # sync state machine
             if is_busy and self.state_machine.current_state == AgentState.IDLE:
                 logger.info(f"Mod reported BUSY ({data.get('current_action')}). Transitioning to BUSY.")
                 self.state_machine.transition_to(AgentState.BUSY, f"Sync: {data.get('current_action')}")
             
             elif not is_busy and self.state_machine.current_state == AgentState.BUSY:
                 # grace period check
                 # we ignore "IDLE" signals for the first 2 seconds of a task.
                 duration = current_time - self.task_start_time
                 if duration < 2.0:
                      pass
                 else:
                      logger.info("Mod reported IDLE. Task complete. Waking up LLM...")
                      self.state_machine.transition_to(AgentState.IDLE, "Sync: Mod Idle")
                      self.trigger_llm()
             
             # a. initial trigger
             if not getattr(self, "has_started_interaction", False):
                 logger.info("Received first state. Waking up LLM...")
                 self.has_started_interaction = True
                 self.trigger_llm()
                 self.last_idle_poke = current_time
                 return

             # b. idle polling
             if not hasattr(self, "last_idle_poke"):
                  self.last_idle_poke = current_time

             if self.state_machine.current_state == AgentState.IDLE and (current_time - self.last_idle_poke > 10.0):
                  # only poke if truly idle
                  logger.info("Agent is IDLE for too long. Poking LLM...")
                  self.last_idle_poke = current_time
                  self.trigger_llm()

    def trigger_llm(self):
        """Constructs the prompt and calls the LLM."""
        try:
            logger.info("Preparing to call LLM...")
            
            # build context
            context = {
                "state": self.latest_state,
                "recent_events": self.event_history[-5:], # Last 5 events
                "agent_state": self.state_machine.current_state.name
            }
    
            # inject history & plan into the prompt text
            # we wrap the json state with the text blocks
            history_str = "\n".join(self.action_history) if self.action_history else "None yet."
            
            # check for recent failure to prevent hallucinations
            failure_warning = ""
            if self.action_history:
                last_entry = self.action_history[-1]
                if "-> FAILURE" in last_entry:
                    failure_warning = f"""
    !!! CRITICAL: LAST ACTION FAILED !!!
    The previous action reported FAILURE.
    Log: {last_entry}
    You MUST acknowledge this failure. Do NOT assume success.
    """
    
            final_user_message = f"""
    === ACTION HISTORY (Last 10 steps) ===
    {history_str}
    
    {failure_warning}
    
    === YOUR CURRENT PLAN (Update this) ===
    {self.current_plan}
    
    === CURRENT GAME STATE ===
    {json.dumps(context)}
    """
            
            # log prompt size
            logger.debug(f"LLM Prompt Size: {len(final_user_message)} chars")
            
            try:
                response = self.llm_client.generate_response(
                    self.system_prompt,
                    final_user_message,
                    tools=MINECRAFT_TOOLS
                )
                
                self.handle_llm_response(response)
                
            except Exception as e:
                logger.error(f"Error during LLM cycle (API Call): {e}")

        except Exception as e:
             logger.error(f"CRITICAL: Error in trigger_llm (Preparation): {e}")

    def handle_llm_response(self, response: Dict[str, Any]):
        """Executes the action decided by the LLM."""
        
        thought = response.get("thought")
        plan = response.get("plan")
        action = response.get("action")
        params = response.get("parameters", {})
        
        # 1. update plan
        if plan:
            self.current_plan = plan
            logger.info(f"LLM Plan:\n{plan}")
        
        if thought:
            logger.info(f"LLM Thought: {thought}")

            # trigger callback
            # we assume the callback itself checks if it should run
            if self.on_thought_callback:
                try:
                    self.on_thought_callback(thought)
                except Exception as e:
                    logger.error(f"Error in on_thought_callback: {e}")
            
            # auto-chat feature
            if Config.AUTO_CHAT_THOUGHTS:
                # sanitize and validate message
                safe_thought = thought.replace("\n", " ").strip()
                if len(safe_thought) > 100:
                    safe_thought = safe_thought[:97] + "..."

                chat_cmd = {
                    "action": "chat",
                    "parameters": {"message": safe_thought}
                }
                self.mc_client.send(chat_cmd)
                time.sleep(0.1) # Brief pause to ensure chat packet is processed before action

            
        if action:
            logger.info(f"Executing Action: {action} with args {params}")
            
            # construct json command for mod
            command = {
                "action": action,
                "parameters": params
            }
            
            # send to mod
            self.mc_client.send(command)
            
            # update state
            instant_actions = ["request_screenshot", "check_death_log", "stop_moving", "chat"]
            
            # store context for history logging
            self.last_action_context = {"name": action, "params": params}
            if action in instant_actions:
                # instant actions don't have a start/finish event usually, or return immediately.
                # we log them immediately to history to keep it snappy.
                self._update_history(action, params, "SENT")
                self.last_action_context = None # clear immediately
            
            if action not in instant_actions:
                self.state_machine.transition_to(AgentState.BUSY, f"Executing {action}")
                self.state_machine.set_task(action)
                self.task_start_time = time.time()
        else:
            logger.warning("LLM Response contained no action.")

