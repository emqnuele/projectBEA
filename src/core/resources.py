from pathlib import Path
from typing import Dict, Tuple, List, Any
from src.utils.logger import get_logger

logger = get_logger("bea.resources")

ALIASES = {"thankingA1": "thanking—"}

def load_avatar_resources(avatar_map: Dict[str, Dict[str, str]]) -> Dict[str, Tuple[Path, Path]]:
    """
    Carica e valida le risorse avatar dalla mappa di configurazione.
    Restituisce un dizionario mood -> (idle_path, talking_path).
    """
    processed_map: Dict[str, Tuple[Path, Path]] = {}
    
    for mood, paths in avatar_map.items():
        idle_str = paths.get("idle")
        talking_str = paths.get("talking")
        
        if not idle_str or not talking_str:
            logger.warning(f"Mood '{mood}' incomplete. Missing 'idle' or 'talking' path.")
            continue
            
        idle_path = Path(idle_str).resolve()
        talking_path = Path(talking_str).resolve()
        
        # warning if not found
        if not idle_path.exists():
            logger.warning(f"Idle image for mood '{mood}' not found at: {idle_path}")
        if not talking_path.exists():
             logger.warning(f"Talking image for mood '{mood}' not found at: {talking_path}")

        processed_map[mood] = (idle_path, talking_path)
        
    return processed_map

def resolve_mood_paths(png_map: Dict[str, Tuple[Path, Path]], mood: str) -> Tuple[Path, Path]:
    """Trova i PNG per il mood, applicando alias e fallback a normal."""
    # 1. exact match
    if mood in png_map:
        return png_map[mood]
        
    # 2. aliases
    alias = ALIASES.get(mood)
    if alias and alias in png_map:
        return png_map[alias]
        
    # 3. fallback normal
    if "normal" in png_map:
        return png_map["normal"]
        
    # 4. fallback any
    if png_map:
        return next(iter(png_map.values()))
    
    # 5. last resort
    return (Path("placeholder_idle.png"), Path("placeholder_talking.png"))
