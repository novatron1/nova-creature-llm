#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v443_memory_conflict import simulate_memory_conflict
import json
def main():
    r = simulate_memory_conflict()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v443_gold_memory_conflict_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
