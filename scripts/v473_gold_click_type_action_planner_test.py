#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v473_click_type_action_planner import plan_click_type
import json
def main():
    r = plan_click_type()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v473_click_type_action_planner_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
