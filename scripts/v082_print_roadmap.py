#!/usr/bin/env python3
"""Print roadmap summary."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v082_long_term_roadmap_planner import build_roadmap

def main():
    print("Nova v082 -- Master Roadmap\n")
    r = build_roadmap()
    print(f"Completed versions: {len(r['completed_versions'])}")
    print(f"Active: {r['current_active_version']}")
    print(f"\nActive versions:")
    for v, d in sorted(r['active_versions'].items()):
        print(f"  {v}: {d}")
    print(f"\nFuture blocks:")
    for b in r['blocked_upgrades']:
        print(f"  BLOCKED: {b}")
    print(f"\nRobot prereqs:")
    for p in r['robot_prerequisites']:
        print(f"  - {p}")
    print(f"\nBenchmark requirements:")
    for step, req in r['benchmark_required_for_future_steps'].items():
        print(f"  {step}: {req}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
