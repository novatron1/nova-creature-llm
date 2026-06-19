#!/usr/bin/env python3
"""Print Computer Hands Report v480."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v480_computer_hands_report import hands_report
def main():
    r = hands_report()
    print("\n" + "="*60)
    print("NOVA COMPUTER HANDS REPORT")
    print("="*60)
    if isinstance(r, dict):
        for k, v in r.items():
            print(f"  {k}: {v}")
    print("="*60)
if __name__ == "__main__":
    raise SystemExit(main())
