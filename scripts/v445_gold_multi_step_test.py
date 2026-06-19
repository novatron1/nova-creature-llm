#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v445_multi_step_mission import simulate_multi_step_mission
import json
def main():
    r = simulate_multi_step_mission()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v445_gold_multi_step_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
