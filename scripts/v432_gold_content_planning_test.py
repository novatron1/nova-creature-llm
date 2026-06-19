#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v432_content_planning import simulate_content_planning
import json
def main():
    r = simulate_content_planning()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v432_gold_content_planning_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
