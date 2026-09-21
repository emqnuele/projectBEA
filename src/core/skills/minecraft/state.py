"""Turns the mod's game-state packet into a few readable lines.

The raw packet is a wall of JSON — ~700 lidar entries underground, 36 inventory
slots, every nearby entity — which would drown the personality in logs and cost
a fortune in tokens. Pure: a dict in, a string out.
"""

from typing import Any, Dict, List, Optional

MAX_ENTITIES = 8
MAX_BLOCK_KINDS = 5
MAX_CRAFTABLE = 8
# blocks named one by one, with the coordinates she would act on
MAX_BLOCKS = 12
# so a row of torches cannot spend the whole budget and hide the ore behind it
MAX_PER_KIND = 3


def render_state(state: Optional[Dict[str, Any]]) -> str:
    """A compact, human-readable view of where Bea's body is and what it holds."""
    if not state or "player" not in state:
        return ""

    lines: List[str] = []
    lines.extend(_player_lines(state))

    inventory = _inventory_line(state.get("inventory") or {})
    if inventory:
        lines.append(inventory)

    worn = _worn_line(state.get("inventory") or {})
    if worn:
        lines.append(worn)

    craftable = _craftable_line(state.get("inventory") or {})
    if craftable:
        lines.append(craftable)

    lines.extend(_lidar_lines(state.get("lidar") or {}))

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


def count_items(state: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """Everything she has, worn or carried, by short name.

    `hand_main` is one of the hotbar slots rather than a slot of its own, so it
    is left out: counting it would report every held tool twice.
    """
    inv = (state or {}).get("inventory") or {}
    slots = list(inv.get("hotbar") or []) + list(inv.get("main") or [])
    slots += list(inv.get("armor") or [])
    off = inv.get("hand_off")
    if off:
        slots.append(off)
    return _tally(slots)


def _tally(slots: List[Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for slot in slots:
        name = _item_name(slot)
        if name:
            counts[name] = counts.get(name, 0) + int((slot or {}).get("count", 0) or 0)
    return counts


def _inventory_line(inv: Dict[str, Any]) -> str:
    held = _item_name(inv.get("hand_main"))
    counts = _tally(list(inv.get("hotbar") or []) + list(inv.get("main") or []))

    if not counts:
        return f"- holding: {held or 'nothing'}; inventory empty"
    carried = ", ".join(f"{n}×{c}" for n, c in sorted(counts.items(), key=lambda kv: -kv[1]))
    return f"- holding: {held or 'nothing'}; carrying: {carried}"


def _worn_line(inv: Dict[str, Any]) -> str:
    worn = [n for n in (_item_name(s) for s in (inv.get("armor") or [])) if n]
    off = _item_name(inv.get("hand_off"))
    parts = []
    if worn:
        parts.append("wearing: " + ", ".join(worn))
    if off:
        parts.append(f"off hand: {off}")
    return "- " + "; ".join(parts) if parts else ""


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


def _lidar_lines(lidar: Dict[str, Any]) -> List[str]:
    """What is around her, in the terms the tools take.

    Every block the mod names arrives with a coordinate, and `mine_block`,
    `place_block` and `use_block` all require one. Tallying them by name threw
    away the only part the model could act on, and left it to guess a number.
    """
    lines: List[str] = []

    shown: List[str] = []
    per_kind: Dict[str, int] = {}
    leftover: Dict[str, int] = {}
    for b in sorted(lidar.get("blocks") or [], key=_distance):
        name = _short(str(b.get("name", "")))
        if not name:
            continue
        if len(shown) < MAX_BLOCKS and per_kind.get(name, 0) < MAX_PER_KIND:
            per_kind[name] = per_kind.get(name, 0) + 1
            shown.append(_block_at(name, b))
        else:
            leftover[name] = leftover.get(name, 0) + 1
    if shown:
        lines.append("- nearby: " + ", ".join(shown))
    if leftover:
        more = sorted(leftover.items(), key=lambda kv: -kv[1])[:MAX_BLOCK_KINDS]
        lines.append("- more of the same: " + ", ".join(f"{n}×{c}" for n, c in more))

    # the two blocks that decide whether she can walk and whether she can jump;
    # standing on air means she is already falling
    ground, ceiling = lidar.get("standing_on"), lidar.get("above_head")
    if ground or ceiling:
        lines.append(f"- standing on {ground or 'nothing'}, "
                     f"{ceiling or 'nothing'} above your head")

    bulk = lidar.get("surrounded_by") or {}
    if bulk:
        top = sorted(bulk.items(), key=lambda kv: -_int(kv[1]))[:MAX_BLOCK_KINDS]
        lines.append("- surrounded by: " + ", ".join(f"{n}×{c}" for n, c in top))
    return lines


def _block_at(name: str, b: Dict[str, Any]) -> str:
    where = f"({_int(b.get('x'))}, {_int(b.get('y'))}, {_int(b.get('z'))})"
    distance = b.get("distance")
    if distance is None:
        return f"{name} {where}"
    return f"{name} {where} {float(distance):.1f}m"


def _distance(b: Dict[str, Any]) -> float:
    try:
        return float(b.get("distance", 999) or 999)
    except (TypeError, ValueError):
        return 999.0


def _int(value: Any) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return 0


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
