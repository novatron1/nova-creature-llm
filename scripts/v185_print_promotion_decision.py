#!/usr/bin/env python3
"""Print promotion decision."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v185_age_cycle_promotion_decision import decide_promotion
def main():
    r = decide_promotion()
    print(f"Nova v185 -- Age-Cycle Promotion Decision\n")
    print(f"Decision: {r['decision']}")
    print(f"Reason: {r['reason']}")
    print(f"Winner: {r['winner']}")
    print(f"Candidates exist: {r['candidates_exist']}")
    print(f"Candidate won tournament: {r['candidate_won_tournament']}")
    print(f"Owner approval: {r['owner_approval_present']}")
    print(f"Robot movement blocked: {r['robot_movement_still_blocked']}")
    print(f"Next action: {r['next_action']}")
    (ROOT/"reports"/"v185_age_cycle_promotion_decision.json").write_text(json.dumps(r, indent=2))
    return 0
if __name__ == "__main__": raise SystemExit(main())
