#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v450_skill_simulation_report import generate_skill_simulation_report
import json
def main():
    r = generate_skill_simulation_report()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v450_gold_skill_simulation_report_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
