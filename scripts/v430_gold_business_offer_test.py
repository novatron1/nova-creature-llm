#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v430_business_offer import simulate_business_offer
import json
def main():
    r = simulate_business_offer()
    print(r.get("version", "done"))
    (ROOT/"reports"/"v430_gold_business_offer_test.json").write_text(json.dumps(r if isinstance(r,dict) else {}, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
