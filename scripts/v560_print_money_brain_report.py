#!/usr/bin/env python3
"""Print Money Brain Report (v560)"""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v560_generate_money_report import generate_money_report
def main():
    r = generate_money_report()
    print("=== Money Brain Report ===")
    for k, v in r.items():
        print(f"  {k}: {v}")
if __name__ == "__main__":
    raise SystemExit(main())
