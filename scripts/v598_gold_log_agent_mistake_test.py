#!/usr/bin/env python3
"""Gold test for v598_agent_mistake_memory."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v598_agent_mistake_memory import log_agent_mistake
import json
def main():
    r = log_agent_mistake()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v598_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
