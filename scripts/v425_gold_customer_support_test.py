#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v425_customer_support import simulate_customer_support
import json
def main():
    r = simulate_customer_support()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v425_gold_customer_support_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
