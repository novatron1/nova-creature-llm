#!/usr/bin/env python3
"""Print Personal OS Report v580."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v580_personal_os_report import generate_personal_os_report
def main():
    r = generate_personal_os_report()
    print(f"=== Personal OS Report ===")
    for k, v in r.items():
        print(f"  {k}: {v}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
