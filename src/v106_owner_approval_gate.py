"""v106 — Manual Owner Approval Gate."""
from __future__ import annotations
from datetime import datetime

APPROVAL_TYPES = ["robot_physical_movement","package_install","file_edit_outside_sandbox","deployment","training_personal_memory"]

def check_owner_approval(action_type, context=None):
    requires = action_type in APPROVAL_TYPES
    return {"version":"v106_owner_approval_gate","created_at":datetime.now().isoformat(),
            "action_type":action_type,"requires_approval":requires,"approved":not requires,
            "pending":requires,"note":"Manual owner approval required" if requires else "Auto-approved"}

def main():
    print("Nova v106 -- Approval Gate\n")
    r = check_owner_approval("robot_physical_movement")
    print(f"Robot movement requires approval: {r['requires_approval']}")
    r2 = check_owner_approval("read_report")
    print(f"Read report requires approval: {r2['requires_approval']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
