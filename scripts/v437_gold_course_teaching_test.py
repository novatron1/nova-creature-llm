#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v437_course_teaching import simulate_course_teaching
import json
def main():
    r = simulate_course_teaching()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v437_gold_course_teaching_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
