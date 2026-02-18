import json
import re
from typing import Optional, Tuple, Dict

def parse_llm_json(reply: str) -> Tuple[str, str, Dict]:
    """parses the LLM JSON reply to extract mood and message."""
    def try_load(candidate: str) -> Optional[Dict[str, str]]:
        try:
            return json.loads(candidate)
        except Exception:
            return None

    # 1. markdown code blocks
    fenced = re.search(r"```(?:json)?\s*({.*?})\s*```", reply, flags=re.DOTALL | re.IGNORECASE)
    data: Optional[Dict[str, str]] = None
    if fenced:
        data = try_load(fenced.group(1))

    # 2. raw json start
    if data is None:
        stripped = reply.strip()
        if stripped.startswith("{"):
            data = try_load(stripped)

    # 3. find first balanced brace
    if data is None:
        start = reply.find("{")
        if start != -1:
            depth = 0
            for idx in range(start, len(reply)):
                ch = reply[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = reply[start : idx + 1]
                        data = try_load(candidate)
                        break
    
    if data is None:
        return "normal", reply, {}

    mood = data.get("mood", "normal") if isinstance(data, dict) else "normal"
    message = data.get("message", "") if isinstance(data, dict) else ""
    
    return str(mood), str(message), data
