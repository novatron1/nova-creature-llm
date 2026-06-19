#!/usr/bin/env python3
"""Print Defense Brain Report (v540)"""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v540_generate_defense_report import generate_defense_report
def main():
    r = generate_defense_report()
    print("=== Defense Brain Report ===")
    for k, v in r.items():
        print(f"  {k}: {v}")
if __name__ == "__main__":
    raise SystemExit(main())
