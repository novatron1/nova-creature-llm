#!/usr/bin/env python3
"""Check v064 memory law and approval constitution."""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v064_memory_law import evaluate_memory_policy, MEMORY_LAWS
from v064_approval_constitution import get_approval_rule, needs_approval, can_train, can_export_dictionary

ERRORS = []
PASSES = []

def check(cond, msg):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v064 — Memory Law Checker\n")

    # 1. Files
    print("1. Checking source files…")
    for f in [ROOT/"src"/"v064_memory_law.py", ROOT/"src"/"v064_approval_constitution.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Memory laws
    print("2. Verifying memory laws…")
    check(len(MEMORY_LAWS) == 10, f"10 memory laws ({len(MEMORY_LAWS)})")

    # 3. Evaluate policies
    print("3. Testing memory policy evaluation…")
    p1 = evaluate_memory_policy({"memory_type": "auto_project_memory"})
    check(p1["allowed_to_store"], "auto_project allowed_to_store")
    check(not p1["requires_owner_approval"], "auto_project no approval")

    p2 = evaluate_memory_policy({"memory_type": "temporary_conversation_context"})
    check(not p2["allowed_to_train"], "temporary not trainable")

    p3 = evaluate_memory_policy({"memory_type": "pending_approval_memory"})
    check(p3["requires_owner_approval"], "pending requires approval")

    p4 = evaluate_memory_policy({"memory_type": "any", "status": "rejected"})
    check(p4["blocked"], "rejected is blocked")
    check(p4["block_reason"] is not None, "rejected has block_reason")

    # 4. Approval constitution
    print("4. Testing approval constitution…")
    check(not needs_approval("auto_project_memory"), "auto_project no approval via constitution")
    check(needs_approval("pending_approval_memory"), "pending approval via constitution")
    check(not can_train("temporary_conversation_context"), "temporary not trainable via constitution")
    check(can_train("explicit_user_memory"), "explicit_user trainable")
    check(not can_export_dictionary("pending_approval_memory"), "pending not exportable")
    check(can_export_dictionary("training_candidate_memory"), "training_candidate exportable")

    # 5. All memory types covered
    print("5. Checking all memory types covered…")
    c = __import__("v064_approval_constitution", fromlist=["dummy"]).check_constitution()
    tested = c["memory_types_tested"]
    check(len(tested) == 6, f"6 memory types tested ({len(tested)})")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v064 check did not pass")
        return 1
    print("\nPASS: v064 memory law + approval constitution installed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
