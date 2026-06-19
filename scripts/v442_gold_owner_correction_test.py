#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v442_owner_correction import simulate_owner_correction
import json
def main():
    r = simulate_owner_correction()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v442_gold_owner_correction_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
