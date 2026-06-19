#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v454_sandbox_execution_planner import plan_sandbox_execution
import json
def main():
    r = plan_sandbox_execution()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v454_sandbox_execution_planner_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
