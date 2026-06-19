#!/usr/bin/env python3
"""v073 — Readiness report."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v073_robot_deployment_gate import check_deployment_readiness

def main():
    print("Nova v073 -- Robot Readiness Report\n")
    r = check_deployment_readiness()
    print(f"Deployment ready: {r['deployment_ready']}")
    print(f"Real movement allowed: {r['real_robot_movement_allowed']}")
    print(f"Missing requirements:")
    for m in r['missing_requirements']:
        print(f"  - {m}")
    print()
    for name, info in r['requirements'].items():
        status = "MET" if info['met'] else "MISSING"
        print(f"  {status}: {name} - {info['reason']}")
    (ROOT/"reports"/"v073_robot_deployment_readiness_status.json").write_text(json.dumps(r, indent=2))
    print(f"\nReport: reports/v073_robot_deployment_readiness_status.json")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
