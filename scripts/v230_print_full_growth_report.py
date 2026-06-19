#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from v230_full_capability_growth_report import generate_growth_report; import json
def main():
    r = generate_growth_report(); print(f"Full Capability Growth Report\n")
    print(f"Total versions: {r['total_modules']}")
    print(f"Active capabilities: {', '.join(r['active_capabilities'])}")
    print(f"Still blocked: {', '.join(r['still_blocked'])}")
    print(f"Weakest role: {r['weakest_role']}")
    print(f"Next role to train: {r['next_role_to_train']}")
    print(f"Growth trend: {r['growth_trend']}")
    print(f"Promote ready: {r['promote_ready']}")
    (ROOT/"reports"/"v230_growth_report.json").write_text(json.dumps(r,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
