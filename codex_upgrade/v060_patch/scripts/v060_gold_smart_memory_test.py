from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v060_smart_memory_capture import classify_memory_event
from v060_memory_manager import process_message, get_counts

ERRORS = []
PASSES = []
INFO = []

TEST_MESSAGES = [
    {
        "message": "v059 passed and all live routes select v055",
        "expected_type": "auto_project_memory",
        "check_save": True,
    },
    {
        "message": "Remember my favorite color is blue",
        "expected_type": "explicit_user_memory",
        "check_save": True,
    },
    {
        "message": "Maybe this is the right checkpoint",
        "expected_type": "pending_approval_memory",
        "check_save": False,
        "check_approval": True,
    },
    {
        "message": "Do that",
        "expected_type": "temporary_conversation_context",
        "check_save": False,
    },
    {
        "message": "The correct answer to who created you is Mr. Novotron",
        "expected_type": "training_candidate_memory",
        "check_save": True,
        "check_export": True,
    },
]

def main():
    print("Nova Creature v060 — Gold Smart Memory Test\n")

    # Phase 1: Classify
    print("Phase 1: Classification tests\n")
    for t in TEST_MESSAGES:
        msg = t["message"]
        result = classify_memory_event(msg)
        mem_type = result["memory_type"]
        passed = mem_type == t["expected_type"]
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] message: {msg}")
        print(f"         memory_type: {mem_type} (expected {t['expected_type']})")
        print(f"         confidence: {result['confidence']}")
        print(f"         reason: {result['reason']}")
        print(f"         auto_save: {result['should_auto_save']}")
        print(f"         require_approval: {result['should_require_approval']}")
        print(f"         export_to_training: {result['should_export_to_training']}")
        print(f"         storage: {result['suggested_storage_path']}")
        print()
        if passed:
            PASSES.append(msg)
        else:
            ERRORS.append(msg)

    # Phase 2: Process through memory manager
    print("Phase 2: Memory manager storage tests\n")
    for t in TEST_MESSAGES:
        msg = t["message"]
        result = process_message(msg, answer="test answer", route="test_route")
        event = result["event"]
        print(f"  [STORED] {event['id']}")
        print(f"           type: {event['memory_type']}")
        print(f"           status: {event['status']}")
        print(f"           file: {result['stored_in']}")
        print()

    # Phase 3: Show counts
    print("Phase 3: Storage counts\n")
    counts = get_counts()
    for mt, count in counts.items():
        print(f"  {mt}: {count} items")

    # Approve any pending items
    from v060_memory_manager import list_pending, approve_pending
    pending = list_pending()
    if pending:
        print(f"\n  Approving {len(pending)} pending items…")
        for ev in pending:
            approve_pending(ev["id"])
            print(f"    approved: {ev['id']}")

    counts = get_counts()
    print()
    for mt, count in counts.items():
        print(f"  {mt}: {count} items (after approval)")

    # ── Final report ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")

    report = {
        "version": "v060_smart_memory_capture",
        "created_at": __import__("datetime").datetime.now().isoformat(),
        "tests_run": len(TEST_MESSAGES),
        "tests_passed": len(PASSES),
        "tests_failed": len(ERRORS),
        "classifier_test_results": [
            {"message": t["message"], "expected": t["expected_type"],
             "actual": classify_memory_event(t["message"])["memory_type"],
             "passed": classify_memory_event(t["message"])["memory_type"] == t["expected_type"]}
            for t in TEST_MESSAGES
        ],
        "storage_counts": get_counts(),
    }
    (ROOT / "reports" / "v060_smart_memory_capture_status.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
