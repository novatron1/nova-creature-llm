#!/usr/bin/env python3
"""Gold test for v561_daily_mission_planner."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v561_daily_mission_planner import plan_daily_missions
import json
def main():
    r = plan_daily_missions()
    print(r.get("version", "done"))
    (ROOT / "reports" / "v561_gold.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
