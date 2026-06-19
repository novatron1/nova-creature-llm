#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v434_revenue_planning import simulate_revenue_planning
import json
def main():
    r = simulate_revenue_planning()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v434_gold_revenue_planning_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
