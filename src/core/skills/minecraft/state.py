"""Turns the mod's game-state packet into a few readable lines.

The raw packet is a wall of JSON: ~700 lidar entries underground, 36 inventory
slots most of them air, every entity within 20 blocks. Dropped whole into the
prompt it drowns the personality in logs and costs a fortune in tokens.

Pure functions: a dict in, a string out. The definitive fix is on the mod side
(send less), but the mind should never depend on that.
"""

from typing import Any, Dict, List, Optional

# blocks worth naming individually; everything else becomes a tally
INTERESTING = (
    "ore", "chest", "barrel", "furnace", "crafting", "water", "lava", "bed",
    "door", "torch", "spawner", "portal", "anvil", "shulker", "hopper",
)

MAX_ENTITIES = 8
MAX_BLOCK_KINDS = 5
MAX_CRAFTABLE = 8


def render_state(state: Optional[Dict[str, Any]]) -> str:
    """A compact, human-readable view of where Bea's body is and what it holds."""
    if not state or "player" not in state:
        return ""

    lines: List[str] = []
    lines.extend(_player_lines(state))

    inventory = _inventory_line(state.get("inventory") or {})
    if inventory:
        lines.append(inventory)

    craftable = _craftable_line(state.get("inventory") or {})
    if craftable:
        lines.append(craftable)

    surroundings = _lidar_line(state.get("lidar") or {})
    if surroundings:
        lines.append(surroundings)

    entities = _entities_line(state.get("entities") or [])
    if entities:
        lines.append(entities)

    gui = _gui_line(state.get("gui_state") or {})
    if gui:
        lines.append(gui)

    return "\n".join(lines)


def _player_lines(state: Dict[str, Any]) -> List[str]:
    p = state.get("player") or {}
    pos = p.get("position") or {}
    where = ""
    if pos:
        where = f" at ({pos.get('x', 0):.0f}, {pos.get('y', 0):.0f}, {pos.get('z', 0):.0f})"

    lines = [
        f"- health {_num(p.get('health'))}/20, food {_num(p.get('food'))}/20{where}"
    ]
    if not p.get("is_alive", True):
        lines.append("- you are DEAD")
    action = state.get("current_action")
    if state.get("is_busy") and action:
        lines.append(f"- your body is busy: {action}")
    return lines


def _inventory_line(inv: Dict[str, Any]) -> str:
    held = _item_name(inv.get("hand_main"))
    counts: Dict[str, int] = {}
    for slot in list(inv.get("hotbar") or []) + list(inv.get("main") or []):
        name = _item_name(slot)
        if name:
            counts[name] = counts.get(name, 0) + int(slot.get("count", 0) or 0)

    if not counts:
        return f"- holding: {held or 'nothing'}; inventory empty"
    carried = ", ".join(f"{n}×{c}" for n, c in sorted(counts.items(), key=lambda kv: -kv[1]))
    return f"- holding: {held or 'nothing'}; carrying: {carried}"


def _craftable_line(inv: Dict[str, Any]) -> str:
    ctx = inv.get("context") or {}
    items = list(ctx.get("craftable_3x3") or ctx.get("craftable_2x2") or [])
    if not items:
        return ""
    names = [_short(str(i.get("item", ""))) for i in items[:MAX_CRAFTABLE] if i.get("item")]
    if not names:
        return ""
    more = " …" if len(items) > MAX_CRAFTABLE else ""
    return f"- can craft now: {', '.join(names)}{more}"


def _lidar_line(lidar: Dict[str, Any]) -> str:
    blocks = lidar.get("blocks") or []
    if not blocks:
        return ""
    counts: Dict[str, int] = {}
    notable: Dict[str, int] = {}
    for b in blocks:
        name = _short(str(b.get("name", "")))
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
        if any(k in name for k in INTERESTING):
            notable[name] = notable.get(name, 0) + 1

    parts = []
    if notable:
        parts.append("nearby: " + ", ".join(f"{n}×{c}" for n, c in sorted(notable.items())))
    bulk = sorted(((n, c) for n, c in counts.items() if n not in notable),
                  key=lambda kv: -kv[1])[:MAX_BLOCK_KINDS]
    if bulk:
        parts.append("surrounded by " + ", ".join(f"{n}×{c}" for n, c in bulk))
    return "- " + "; ".join(parts) if parts else ""


def _entities_line(entities: List[Dict[str, Any]]) -> str:
    if not entities:
        return ""
    ordered = sorted(entities, key=lambda e: float(e.get("distance", 999) or 999))
    described = []
    for e in ordered[:MAX_ENTITIES]:
        name = e.get("name") or _short(str(e.get("type", "")))
        distance = float(e.get("distance", 0) or 0)
        who = f"{name} {distance:.0f}m"
        if e.get("is_player"):
            who = f"PLAYER {who}"
        described.append(who)
    more = f" (+{len(ordered) - MAX_ENTITIES} more)" if len(ordered) > MAX_ENTITIES else ""
    return f"- around you: {', '.join(described)}{more}"


def _gui_line(gui: Dict[str, Any]) -> str:
    if not gui.get("is_open"):
        return ""
    return f"- you have a {gui.get('type', 'container')} open"


def _item_name(slot: Optional[Dict[str, Any]]) -> str:
    if not slot:
        return ""
    name = _short(str(slot.get("item", "")))
    if not name or name == "air":
        return ""
    return name


def _short(item_id: str) -> str:
    return item_id.split(":")[-1]


def _num(value: Any) -> str:
    try:
        return f"{float(value):.0f}"
    except (TypeError, ValueError):
        return "?"
