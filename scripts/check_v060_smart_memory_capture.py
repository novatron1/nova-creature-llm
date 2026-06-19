from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v060_smart_memory_capture import classify_memory_event
from v060_memory_manager import get_counts, _jsonl_path, MEMORY_TYPES

ERRORS = []
PASSES = []

def check(cond: bool, msg: str):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v060 — Smart Memory Capture Checker\n")

    # 1. All source files exist
    print("1. Checking v060 source files…")
    files = [
        ROOT / "src" / "v060_smart_memory_capture.py",
        ROOT / "src" / "v060_memory_manager.py",
        ROOT / "src" / "v060_smart_memory_router.py",
        ROOT / "scripts" / "v060_list_pending_memory.py",
        ROOT / "scripts" / "v060_approve_memory.py",
        ROOT / "scripts" / "v060_reject_memory.py",
        ROOT / "scripts" / "check_v060_smart_memory_capture.py",
        ROOT / "scripts" / "v060_gold_smart_memory_test.py",
    ]
    for f in files:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. All memory jsonl files exist
    print("\n2. Checking memory storage files…")
    for mt in MEMORY_TYPES:
        p = _jsonl_path(mt)
        check(p.exists(), f"data/smart_memory/{mt}.jsonl exists")

    # 3. Classifier test cases
    print("\n3. Testing classifier accuracy…")
    tests = [
        ("v059 passed and all live routes select v055", "auto_project_memory"),
        ("Remember my favorite color is blue", "explicit_user_memory"),
        ("Maybe this is the right file", "pending_approval_memory"),
        ("Do that", "temporary_conversation_context"),
        ("The correct answer to X is Y", "training_candidate_memory"),
    ]
    for msg, expected in tests:
        result = classify_memory_event(msg)
        actual = result["memory_type"]
        passed = actual == expected
        check(passed, f"classify({msg[:40]}...) → {actual} (expected {expected})")

    # 4. Auto-save flags
    print("\n4. Testing auto-save / approval flags…")
    r1 = classify_memory_event("v059 passed and all live routes select v055")
    check(r1["should_auto_save"] and not r1["should_require_approval"],
          "project memory: auto_save=true, approval=false")

    r2 = classify_memory_event("Remember my favorite color is blue")
    check(r2["should_auto_save"] and not r2["should_require_approval"],
          "explicit memory: auto_save=true, approval=false")

    r3 = classify_memory_event("Maybe this is the right checkpoint")
    check(not r3["should_auto_save"] and r3["should_require_approval"],
          "uncertain memory: auto_save=false, approval=true")

    r4 = classify_memory_event("Do that")
    check(not r4["should_auto_save"] and not r4["should_require_approval"],
          "conversation: auto_save=false, approval=false")

    r5 = classify_memory_event("The correct answer to who created you is Mr. Novotron")
    check(r5["should_export_to_training"],
          "training candidate: export_to_training=true")

    # 5. Memory counts accessible
    print("\n5. Checking memory counts…")
    counts = get_counts()
    for mt in MEMORY_TYPES:
        check(mt in counts, f"count tracked for {mt}")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v060 check did not pass")
        return 1
    print("\nPASS: v060 smart memory capture installed and classifying correctly")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
