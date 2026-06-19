#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v440_conflict_handling import simulate_conflict_handling
import json
def main():
    r = simulate_conflict_handling()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v440_gold_conflict_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
