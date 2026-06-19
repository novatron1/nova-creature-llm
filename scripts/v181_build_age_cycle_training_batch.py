#!/usr/bin/env python3
"""Build v181 age-cycle training batch."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v181_age_cycle_training_batch_builder import build_training_batch
def main():
    r = build_training_batch()
    print(f"Approved: {r['approved']}, Rejected: {r['rejected']}, Pending: {r['pending']}")
    for role, count in r.get("approved_role_breakdown",{}).items():
        print(f"  {role}: {count} lessons")
    print(f"Target weaknesses: {', '.join(r['weaknesses_targeted'])}")
    (ROOT/"reports"/"v181_age_cycle_training_batch_status.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
