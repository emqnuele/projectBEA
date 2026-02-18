from enum import Enum, auto

class AgentState(Enum):
    IDLE = auto()           # free, ready to receive commands (calls llm)
    BUSY = auto()           # executing a long-running task (silences llm)
    INTERRUPTED = auto()    # emergency occurred (force calls llm)

class StateMachine:
    def __init__(self):
        self._current_state = AgentState.IDLE
        self._current_task = None
    
    @property
    def current_state(self):
        return self._current_state

    def transition_to(self, new_state: AgentState, reason: str = ""):
        """Transitions to a new state if allowed."""
        print(f"[StateMachine] Transition: {self._current_state.name} -> {new_state.name} ({reason})")
        self._current_state = new_state

    def set_task(self, task_name: str):
        self._current_task = task_name

    def clear_task(self):
        self._current_task = None

    def should_call_llm(self) -> bool:
        """Determines if we need to wake up the Brain."""
        return self._current_state == AgentState.IDLE or self._current_state == AgentState.INTERRUPTED
