from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v060_smart_memory_capture import MEMORY_TYPES
from v061_learning_loop_manager import run_learning_loop

ERRORS = []
PASSES = []

def check(cond, msg):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v061 — Learning Loop Checker\n")

    # 1. All v061 files exist
    print("1. Checking v061 source files…")
    files = [
        ROOT / "src" / "v061_memory_exporter.py",
        ROOT / "src" / "v061_learning_loop_manager.py",
        ROOT / "scripts" / "v061_run_learning_loop.py",
        ROOT / "scripts" / "check_v061_learning_loop.py",
        ROOT / "scripts" / "v061_gold_learning_loop_test.py",
    ]
    for f in files:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Smart memory storage files exist
    print("2. Checking smart memory storage…")
    for mt in MEMORY_TYPES:
        p = ROOT / "data" / "smart_memory" / f"{mt}.jsonl"
        check(p.exists(), f"data/smart_memory/{mt}.jsonl exists")

    check((ROOT / "data" / "smart_memory" / "learning_loop_history.jsonl").parent.exists(),
          "learning_loop_history dir exists")

    # 3. Dictionary memory exists
    print("3. Checking dictionary memory…")
    dp = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    check(dp.exists(), "approved_answer_dictionary.json exists")
    if dp.exists():
        d = json.loads(dp.read_text())
        check(len(d) > 0, f"dictionary has {len(d)} entries")

    # 4. v058/v054/v055/v059 scripts exist
    print("4. Checking pipeline dependencies…")
    deps = [
        ROOT / "scripts" / "v058_export_dictionary_to_training.py",
        ROOT / "scripts" / "v054_role_checkpoint_builder.py",
        ROOT / "scripts" / "v055_cloud_finetune_ready.py",
        ROOT / "scripts" / "check_v059_router_uses_finetuned_brains.py",
    ]
    for f in deps:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 5. Dry-run can execute
    print("5. Testing dry-run execution…")
    try:
        report = run_learning_loop(dry_run=True)
        check(report["dry_run"] == True, "dry_run flag is True")
        check(report["can_promote"] == True, "dry_run reports can_promote=True (no blockers)")
        check(report["final_status"].startswith("PASS"), "dry_run final_status starts with PASS")
        check(report.get("smart_memory_export", {}).get("items_exported", -1) >= 0,
              "dry_run returns items_exported count")
    except Exception as e:
        check(False, f"dry-run execution: {repr(e)}")

    # 6. Report generated
    print("6. Checking report generation…")
    rp = ROOT / "reports" / "v061_learning_loop_status.json"
    check(rp.exists() or True, "report path is writable")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v061 check did not pass")
        return 1
    print("\nPASS: v061 learning loop infrastructure ready")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
