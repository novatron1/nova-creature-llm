#!/usr/bin/env python3
"""Gold test for v581_manager_agent."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v581_manager_agent import manage_agents
import json
def main():
    r = manage_agents()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v581_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
