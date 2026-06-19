#!/usr/bin/env python3
"""v064 — Gold memory law test."""

import json, sys
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v064_memory_law import evaluate_memory_policy, MEMORY_LAWS
from v064_approval_constitution import needs_approval, can_train, check_constitution

ERRORS = []
PASSES = []

TEST_CASES = [
    {"name": "auto_project", "event": {"memory_type": "auto_project_memory"},
     "checks": {"allowed_to_store": True, "allowed_to_train": False, "blocked": False}},
    {"name": "explicit_user", "event": {"memory_type": "explicit_user_memory"},
     "checks": {"allowed_to_store": True, "allowed_to_train": True, "blocked": False}},
    {"name": "training_candidate", "event": {"memory_type": "training_candidate_memory"},
     "checks": {"allowed_to_store": True, "allowed_to_train": True, "blocked": False}},
    {"name": "pending_approval", "event": {"memory_type": "pending_approval_memory"},
     "checks": {"allowed_to_store": False, "allowed_to_train": False, "blocked": False,
                "requires_owner_approval": True}},
    {"name": "temporary_context", "event": {"memory_type": "temporary_conversation_context"},
     "checks": {"allowed_to_store": True, "allowed_to_train": False, "blocked": False}},
    {"name": "rejected", "event": {"memory_type": "any", "status": "rejected"},
     "checks": {"blocked": True}},
]

def main():
    print("Nova Creature v064 — Gold Memory Law Test\n")

    for tc in TEST_CASES:
        result = evaluate_memory_policy(tc["event"])
        all_ok = True
        for key, expected in tc["checks"].items():
            actual = result.get(key)
            if actual != expected:
                all_ok = False
                ERRORS.append(f"{tc['name']}: {key} expected {expected} got {actual}")
        if all_ok:
            PASSES.append(f"{tc['name']}: all checks passed")
        print(f"  {'✅' if all_ok else '❌'} {tc['name']} -> allowed_to_store={result['allowed_to_store']}, "
              f"allowed_to_train={result['allowed_to_train']}, blocked={result['blocked']}")

    # Constitution checks
    print("\nConstitution type checks:")
    for mt in ["auto_project_memory", "explicit_user_memory", "training_candidate_memory",
               "pending_approval_memory", "temporary_conversation_context"]:
        na = needs_approval(mt)
        ct = can_train(mt)
        print(f"  {mt}: needs_approval={na}, can_train={ct}")

    report = {
        "version": "v064_gold_memory_law_test",
        "created_at": datetime.now().isoformat(),
        "cases": len(TEST_CASES),
        "passed": len(PASSES),
        "errors": len(ERRORS),
        "all_approved": len(ERRORS) == 0,
    }
    (ROOT / "reports" / "v064_gold_memory_law_test.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")
    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
