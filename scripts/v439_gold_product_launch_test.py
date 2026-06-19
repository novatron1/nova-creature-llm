#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v439_product_launch import simulate_product_launch
import json
def main():
    r = simulate_product_launch()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v439_gold_product_launch_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
