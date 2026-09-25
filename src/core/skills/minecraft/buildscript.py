"""Building by writing a little program instead of listing every block.

The body writes a short Python script against a handful of drawing functions
(set, fill, walls, line, circle); the script runs in a separate process with
no imports, no attribute access and a time limit, and all that comes back is
a map of cells. Those become ordinary `build` arguments (layers + palette), so
the mod never sees code and never needs to change for it.
"""

import ast
import json
import re
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Tuple

import psutil

from src.core.skills.minecraft.blueprint import MAX_CELLS, Blueprint, expand, rotate, shortfall

TIMEOUT_S = 3.0
MAX_MEMORY = 512 * 2**20   # bytes the script's process may hold
POLL_S = 0.01              # how often its memory is looked at
MAX_SOURCE = 4000          # characters: a build script is a sketch, not a program
MAX_BLOCK_KINDS = 60       # one palette character each
BLOCK = re.compile(r"^[a-z0-9_]+(\[[a-z0-9_]+=[a-z0-9_]+(,[a-z0-9_]+=[a-z0-9_]+)*\])?$")
PALETTE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@%&*+=?!"

ALLOWED = (
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.For, ast.While, ast.If, ast.Break,
    ast.Continue, ast.Pass, ast.FunctionDef, ast.Return, ast.Call, ast.Name, ast.Constant,
    ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp, ast.List, ast.Tuple, ast.Dict,
    ast.Set, ast.Subscript, ast.Slice, ast.ListComp, ast.SetComp, ast.DictComp,
    ast.GeneratorExp, ast.comprehension, ast.keyword, ast.arguments, ast.arg, ast.Load,
    ast.Store, ast.Del, ast.JoinedStr, ast.FormattedValue,
    ast.operator, ast.unaryop, ast.boolop, ast.cmpop, ast.expr_context,
)


class ScriptError(ValueError):
    pass


def check(source: str) -> None:
    """Refuse anything that is not plain arithmetic, loops and the drawing functions."""
    if len(source) > MAX_SOURCE:
        raise ScriptError(f"script is {len(source)} characters; keep it under {MAX_SOURCE}")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ScriptError(f"line {e.lineno}: {e.msg}") from None
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        if not isinstance(node, ALLOWED):
            raise ScriptError(f"line {line}: {type(node).__name__} is not allowed in a build script")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ScriptError(f"line {line}: names starting with _ are not allowed")
        if isinstance(node, (ast.FunctionDef, ast.arg)):
            name = node.name if isinstance(node, ast.FunctionDef) else node.arg
            if name.startswith("_"):
                raise ScriptError(f"line {line}: names starting with _ are not allowed")
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            raise ScriptError(f"line {line}: decorators are not allowed")


# The child process: gets the script on stdin, prints one JSON line.
RUNNER = r'''
import json, math, sys
MAX = int(sys.argv[1])
cells = {}
notes = []

class Stop(Exception):
    pass

def _put(x, y, z, block):
    if not isinstance(block, str):
        raise Stop("block must be a name like 'oak_planks'")
    key = (int(round(x)), int(round(y)), int(round(z)))
    cells[key] = block
    if len(cells) > MAX:
        raise Stop(f"more than {MAX} cells")

def _box(a, b):
    lo, hi = sorted((int(round(a)), int(round(b))))
    return range(lo, hi + 1)

def set(x, y, z, block):
    _put(x, y, z, block)

def fill(x1, y1, z1, x2, y2, z2, block, hollow=False):
    xs, ys, zs = _box(x1, x2), _box(y1, y2), _box(z1, z2)
    for x in xs:
        for y in ys:
            for z in zs:
                shell = x in (xs[0], xs[-1]) or y in (ys[0], ys[-1]) or z in (zs[0], zs[-1])
                _put(x, y, z, block if shell or not hollow else "air")

def walls(x1, y1, z1, x2, y2, z2, block):
    xs, ys, zs = _box(x1, x2), _box(y1, y2), _box(z1, z2)
    for x in xs:
        for y in ys:
            for z in zs:
                if x in (xs[0], xs[-1]) or z in (zs[0], zs[-1]):
                    _put(x, y, z, block)

def line(x1, y1, z1, x2, y2, z2, block):
    n = max(abs(x2 - x1), abs(y2 - y1), abs(z2 - z1))
    n = int(round(n))
    for i in range(n + 1):
        t = i / n if n else 0
        _put(x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, z1 + (z2 - z1) * t, block)

def circle(cx, y, cz, r, block, filled=False):
    r = float(r)
    for x in range(int(cx - r) - 1, int(cx + r) + 2):
        for z in range(int(cz - r) - 1, int(cz + r) + 2):
            d = math.hypot(x - cx, z - cz)
            if d <= r + 0.5 and (filled or d >= r - 0.5):
                _put(x, y, z, block)

def get(x, y, z):
    return cells.get((int(round(x)), int(round(y)), int(round(z))))

def note(*parts):
    if len(notes) < 20:
        notes.append(" ".join(str(p) for p in parts)[:200])

env = {"__builtins__": {
    "range": range, "len": len, "abs": abs, "min": min, "max": max, "round": round,
    "int": int, "float": float, "str": str, "enumerate": enumerate, "zip": zip,
    "list": list, "reversed": reversed, "sorted": sorted, "sum": sum, "bool": bool,
    "True": True, "False": False, "None": None,
}}
env.update(set=set, fill=fill, walls=walls, line=line, circle=circle, get=get, note=note,
           sin=math.sin, cos=math.cos, tan=math.tan, atan2=math.atan2, sqrt=math.sqrt,
           floor=math.floor, ceil=math.ceil, radians=math.radians, hypot=math.hypot, pi=math.pi)
source = sys.stdin.read()
try:
    exec(compile(source, "<build>", "exec"), env)
    out = {"cells": [[x, y, z, b] for (x, y, z), b in cells.items()], "notes": notes}
except Stop as e:
    out = {"error": str(e)}
except Exception as e:
    tb = e.__traceback__
    line = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == "<build>":
            line = tb.tb_lineno
        tb = tb.tb_next
    out = {"error": (f"line {line}: " if line else "") + f"{type(e).__name__}: {e}"}
sys.stdout.write(json.dumps(out))
'''


def _limits() -> None:  # pragma: no cover - runs in the child, POSIX only
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (int(TIMEOUT_S) + 1, int(TIMEOUT_S) + 1))
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MAX_MEMORY, MAX_MEMORY))
    except (ValueError, OSError):
        pass  # macos refuses any address-space cap: the watch in _supervise covers it


def _supervise(proc: "subprocess.Popen[str]", source: str) -> str:
    """Feed the script in and wait for its answer, killing it if it runs long or grows fat.

    The memory watch is what holds on macOS and Windows, where no rlimit caps
    a process: a three-second list comprehension reached 6.6 GB there.
    """
    out: List[str] = []
    feeder = threading.Thread(target=lambda: out.append(proc.communicate(source)[0]), daemon=True)
    feeder.start()
    watched = psutil.Process(proc.pid)
    deadline = time.monotonic() + TIMEOUT_S
    while feeder.is_alive():
        try:
            too_big = watched.memory_info().rss > MAX_MEMORY
        except psutil.Error:
            too_big = False  # already gone: the feeder is about to return
        if too_big or time.monotonic() > deadline:
            proc.kill()
            feeder.join()
            if too_big:
                raise ScriptError(f"the script used more than {MAX_MEMORY // 2**20} MB")
            raise ScriptError(f"the script ran longer than {TIMEOUT_S:g} s")
        feeder.join(POLL_S)
    return out[0] if out else ""


def run(source: str) -> Tuple[Dict[Tuple[int, int, int], str], List[str]]:
    """The cells a script draws, relative to its own (0, 0, 0)."""
    check(source)
    proc = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", RUNNER, str(MAX_CELLS)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        preexec_fn=_limits if sys.platform != "win32" else None,
    )
    stdout = _supervise(proc, source)
    try:
        out = json.loads(stdout)
    except ValueError:
        raise ScriptError("the script crashed (too much memory?)") from None
    if "error" in out:
        raise ScriptError(out["error"])
    cells: Dict[Tuple[int, int, int], str] = {}
    for x, y, z, block in out["cells"]:
        block = block.removeprefix("minecraft:")
        if not BLOCK.match(block):
            raise ScriptError(f"'{block}' is not a block name")
        cells[(x, y, z)] = block
    if not cells:
        raise ScriptError("the script drew nothing")
    return cells, out["notes"]


def to_build_args(cells: Dict[Tuple[int, int, int], str], x: int, y: int, z: int,
                  rotation: int = 0) -> Dict[str, Any]:
    """Cells -> `build` arguments: one layer per y, the box shifted to start at 0."""
    kinds = sorted(set(cells.values()))
    if len(kinds) > MAX_BLOCK_KINDS:
        raise ScriptError(f"{len(kinds)} different blocks; the most is {MAX_BLOCK_KINDS}")
    char = dict(zip(kinds, PALETTE_CHARS[: len(kinds)], strict=True))
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    zs = [c[2] for c in cells]
    x0, y0, z0 = min(xs), min(ys), min(zs)
    width, height, depth = max(xs) - x0 + 1, max(ys) - y0 + 1, max(zs) - z0 + 1
    grid = [[[" "] * width for _ in range(depth)] for _ in range(height)]
    for (cx, cy, cz), block in cells.items():
        grid[cy - y0][cz - z0][cx - x0] = char[block]
    # the script's (0,0,0) stays at (x, y, z): the offset of the box moves with the rotation
    ox, oy, oz = rotate(x0, y0, z0, rotation)
    return {
        "origin": {"x": x + ox, "y": y + oy, "z": z + oz},
        "rotation": rotation,
        "palette": {c: b for b, c in char.items()},
        "layers": [["".join(row).rstrip() for row in layer] for layer in grid],
    }


def preview(source: str, x: int, y: int, z: int, rotation: int,
            inventory: Dict[str, int]) -> Tuple[Dict[str, Any], Blueprint, str]:
    """Run, convert, expand, and say what it is before anything is placed."""
    cells, notes = run(source)
    args = to_build_args(cells, x, y, z, rotation)
    bp = expand(args)
    xs, ys, zs = zip(*bp.cells, strict=True)
    size = f"{max(xs) - min(xs) + 1}x{max(ys) - min(ys) + 1}x{max(zs) - min(zs) + 1}"
    lines = [f"{len(bp.cells)} cells in a {size} box (x by y by z), "
             f"from ({min(xs)}, {min(ys)}, {min(zs)}) to ({max(xs)}, {max(ys)}, {max(zs)})"]
    lines.append("blocks: " + ", ".join(f"{b} x{n}" for b, n in sorted(bp.items.items())))
    missing = shortfall(bp.items, inventory)
    if missing:
        lines.append("missing: " + ", ".join(f"{b} x{n}" for b, n in sorted(missing.items())))
    else:
        lines.append("you carry everything it needs")
    lines += [f"note: {n}" for n in notes]
    return args, bp, "\n".join(lines)
