#!/usr/bin/env python3
"""Print brain age / maturity index."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v153_brain_maturity_index import calculate_brain_age, record_age_snapshot
def main():
    r = record_age_snapshot()
    print(f"Nova Brain Maturity Index\n")
    for k, v in r["components"].items(): print(f"  {k}: {v}")
    print(f"\nOverall Brain Maturity: {r['overall_brain_maturity']}/100")
    print(f"Category: {r['age_category']}")
    return 0
if __name__ == "__main__": raise SystemExit(main())
