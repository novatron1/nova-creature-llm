#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v436_sponsorship_pitch import simulate_sponsorship_pitch
import json
def main():
    r = simulate_sponsorship_pitch()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v436_gold_sponsorship_pitch_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
