# only the pure half is re-exported here: `memory.store` imports `affect.rules`,
# and pulling `state` in from this file would close the loop back through it
from src.core.affect.rules import Affect, decay, is_strong, render, stir, warmth_phrase

__all__ = ["Affect", "decay", "stir", "render", "is_strong", "warmth_phrase"]
