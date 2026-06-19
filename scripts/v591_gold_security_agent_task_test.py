#!/usr/bin/env python3
"""Gold test for v591_security_agent."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v591_security_agent import security_agent_task
import json
def main():
    r = security_agent_task()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v591_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
