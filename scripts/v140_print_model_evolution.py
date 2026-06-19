#!/usr/bin/env python3
"""Print model evolution report."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v140_model_evolution_report import generate_evolution_report

def main():
    r = generate_evolution_report()
    print(f"Nova v140 -- Model Evolution Report\n")
    print(f"Total versions tracked: {r['total_versions']}")
    print(f"Active brains: {r['active_brains']}")
    print(f"Real hardware enabled: {r['real_hardware_enabled']}")
    print(f"Real robot movement allowed: {r['real_robot_movement_allowed']}")
    print(f"Next evolution step: {r['next_evolution_step']}")
    print(f"\nTimeline (first 5 and last 5):")
    for t in r['timeline'][:5]:
        print(f"  {t['version']}: {t['description']}")
    print(f"  ...")
    for t in r['timeline'][-5:]:
        print(f"  {t['version']}: {t['description']}")
    (ROOT / "reports" / "v140_model_evolution_report.json").write_text(
        __import__('json').dumps(r, indent=2))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
