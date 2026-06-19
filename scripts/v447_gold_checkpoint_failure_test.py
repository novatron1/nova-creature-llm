#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v447_checkpoint_failure import simulate_checkpoint_failure
import json
def main():
    r = simulate_checkpoint_failure()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v447_gold_checkpoint_failure_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
