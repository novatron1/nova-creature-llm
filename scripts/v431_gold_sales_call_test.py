#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v431_sales_call import simulate_sales_call
import json
def main():
    r = simulate_sales_call()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v431_gold_sales_call_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
