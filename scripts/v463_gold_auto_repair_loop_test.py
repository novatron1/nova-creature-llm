#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v463_auto_repair_loop import run_auto_repair
import json
def main():
    r = run_auto_repair()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v463_auto_repair_loop_gold_test_status.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
