#!/usr/bin/env python3
"""Gold test for v567_grocery_planner."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v567_grocery_planner import plan_grocery
import json
def main():
    r = plan_grocery()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v567_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
