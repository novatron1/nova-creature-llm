#!/usr/bin/env python3
"""Print Worker Crew Report v600."""
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v600_worker_crew_report import generate_worker_crew_report
def main():
    r = generate_worker_crew_report()
    print(f"=== Worker Crew Report ===")
    for k, v in r.items():
        print(f"  {k}: {v}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
