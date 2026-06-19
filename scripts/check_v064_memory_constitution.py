from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v064_memory_constitution import (
    get_constitution, check_law, can_train,
    requires_approval, auto_approve, evaluate_pending_items,
)

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v064 — Memory Constitution Checker\n")

    # 1. Files exist
    print("1. Checking v064 source files…")
    for f in [ROOT/"src"/"v064_memory_constitution.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Constitution has 10 laws
    print("2. Verifying constitution…")
    c = get_constitution()
    check(len(c["laws"]) == 10, f"Constitution has {len(c['laws'])} laws")
    for law in c["laws"]:
        check("id" in law and "title" in law and "rule" in law, f"Law {law.get('id','?')} has required fields")

    # 3. Law checks
    print("3. Testing law logic…")
    check(can_train("training_candidate_memory"), "training_candidate can train")
    check(not can_train("temporary_conversation_context"), "temporary_context cannot train")
    check(not can_train("any", "rejected"), "rejected items cannot train")
    check(auto_approve("explicit_user_memory"), "explicit_user auto-approves")
    check(not auto_approve("pending_approval_memory"), "pending_approval not auto-approved")
    check(requires_approval("pending_approval_memory"), "pending_approval requires approval")
    check(not requires_approval("auto_project_memory"), "auto_project does not require approval")

    # 4. Evaluate pending items
    print("4. Evaluating pending items…")
    eval_result = evaluate_pending_items()
    check("pending_count" in eval_result, "pending count available")
    check("evaluations" in eval_result, "evaluations list available")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
