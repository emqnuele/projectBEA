import sys
from pathlib import Path

# tests import `src.*` directly; keep them runnable without an editable install
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
