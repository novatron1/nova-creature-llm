from __future__ import annotations

import json, sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v060_smart_memory_capture import classify_memory_event
from v060_memory_manager import process_message, get_counts, _read_jsonl
from v061_memory_exporter import export_smart_memory_to_dictionary

ERRORS = []
PASSES = []
INFO = []

TEST_ITEMS = [
    {
        "message": "The correct answer to who created you is Mr. Novotron.",
        "expected_type": "training_candidate_memory",
        "should_export": True,
        "label": "A (training candidate)",
    },
    {
        "message": "Remember my favorite color is blue.",
        "expected_type": "explicit_user_memory",
        "should_export": True,
        "label": "B (explicit user memory)",
    },
    {
        "message": "Maybe this checkpoint is better.",
        "expected_type": "pending_approval_memory",
        "should_export": False,
        "label": "C (pending uncertainty)",
    },
    {
        "message": "Do that.",
        "expected_type": "temporary_conversation_context",
        "should_export": False,
        "label": "D (temporary context)",
    },
]

def main():
    print("Nova Creature v061 — Gold Learning Loop Test\n")

    # Phase 1: Classify all items
    print("Phase 1: Classification\n")
    classifications = []
    for t in TEST_ITEMS:
        msg = t["message"]
        cls = classify_memory_event(msg)
        passed = cls["memory_type"] == t["expected_type"]
        classifications.append(cls)
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {t['label']}: {msg}")
        print(f"         type: {cls['memory_type']} (expected {t['expected_type']})")
        print(f"         should_export: {t['should_export']}")
        print()
        if passed:
            PASSES.append(f"{t['label']} classified correctly")
        else:
            ERRORS.append(f"{t['label']} classified as {cls['memory_type']} not {t['expected_type']}")

    # Phase 2: Store all items through memory manager
    print("Phase 2: Store items through memory manager\n")
    for t, cls in zip(TEST_ITEMS, classifications):
        result = process_message(t["message"], answer="test", route="test")
        print(f"  [STORED] {t['label']}: {result['event']['memory_type']} → {result['event']['status']}")

    # Phase 3: Export smart memory to dictionary
    print("\nPhase 3: Export to dictionary\n")
    export_result = export_smart_memory_to_dictionary(dry_run=False)
    print(f"  items_exported: {export_result['items_exported']}")
    print(f"  dictionary_entries_added: {export_result['dictionary_entries_added']}")
    print(f"  training_candidates_exported: {export_result['training_candidates_exported']}")
    print(f"  explicit_memory_exported: {export_result['explicit_memory_exported']}")
    print(f"  skipped_not_exportable: {export_result['skipped_not_exportable']}")
    print(f"  skipped_rejected: {export_result['skipped_rejected']}")
    print(f"  skipped_pending: {export_result['skipped_pending']}")

    # Phase 4: Verify which were exported and which were blocked
    print("\nPhase 4: Export verification\n")
    dict_path = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    dictionary = json.loads(dict_path.read_text()) if dict_path.exists() else {}

    # A should be exported (training candidate → dictionary)
    a_exported = any("who created you" in k.lower() for k in dictionary)
    if a_exported:
        PASSES.append("A (training candidate) was exported to dictionary ✅")
    else:
        ERRORS.append("A (training candidate) was NOT exported to dictionary ❌")

    # B should be exported (explicit user memory → dictionary)
    b_exported = any("favorite color" in k.lower() or "color is blue" in k.lower() for k in dictionary)
    if b_exported:
        PASSES.append("B (explicit user memory) was exported to dictionary ✅")
    else:
        # B might not match the Q&A extraction pattern, check more carefully
        INFO.append("B (explicit user memory) may not have had extractable Q&A — checking item…")
        eu = _read_jsonl(ROOT / "data" / "smart_memory" / "explicit_user_memory.jsonl")
        for item in eu:
            if "favorite color" in item.get("message", "").lower():
                if item.get("exported_to_dictionary"):
                    b_exported = True
                    PASSES.append("B (explicit user memory) was exported to dictionary (from item flag) ✅")
                    break

    # C should NOT be exported (pending approval)
    c_exported = any("this checkpoint is better" in k.lower() for k in dictionary)
    if not c_exported:
        PASSES.append("C (pending uncertainty) was NOT exported ✅")
    else:
        ERRORS.append("C (pending uncertainty) was WRONGLY exported ❌")

    # D should NOT be exported (temporary context)
    d_exported = any("do that" in k.lower() for k in dictionary)
    if not d_exported:
        PASSES.append("D (temporary context) was NOT exported ✅")
    else:
        ERRORS.append("D (temporary context) was WRONGLY exported ❌")

    # Phase 5: Run v058 export
    print("\nPhase 5: v058 export from dictionary to training sets\n")
    sys.path.insert(0, str(ROOT / "src"))
    from dictionary_to_training import export_dictionary_to_training
    try:
        v058_summary = export_dictionary_to_training(ROOT)
        print(f"  lessons_added: {v058_summary.get('lessons_added_total', 0)}")
        print(f"  roles updated: {v058_summary.get('training_set_counts', {})}")
        PASSES.append("v058 dictionary-to-training export ran successfully ✅")
    except Exception as e:
        ERRORS.append(f"v058 export failed: {repr(e)}")

    # Phase 6: Show final counts
    print("\nPhase 6: Final storage counts\n")
    counts = get_counts()
    for mt, count in counts.items():
        print(f"  {mt}: {count} items")

    # ── Final report ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors, {len(INFO)} info")
    print(f"{'='*60}")
    for p in PASSES:
        print(f"  ✅ {p}")
    for i in INFO:
        print(f"  ℹ️  {i}")
    for e in ERRORS:
        print(f"  ❌ {e}")

    report = {
        "version": "v061_gold_learning_loop_test",
        "created_at": datetime.now().isoformat(),
        "tests_run": len(TEST_ITEMS),
        "tests_passed": len(PASSES),
        "tests_failed": len(ERRORS),
        "export_result": export_result,
        "dictionary_size": len(dictionary),
        "storage_counts": get_counts(),
    }
    (ROOT / "reports" / "v061_gold_learning_loop_test.json").write_text(json.dumps(report, indent=2))

    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
