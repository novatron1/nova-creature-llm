#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v444_capability_honesty import simulate_capability_honesty
import json
def main():
    r = simulate_capability_honesty()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v444_gold_capability_honesty_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
