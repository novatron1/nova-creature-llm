"""v074 — Mistake Memory / Error Bank."""
from __future__ import annotations
import json, traceback
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERROR_BANK_PATH = ROOT / "data" / "mistake_memory" / "error_bank.jsonl"
FIX_HISTORY_PATH = ROOT / "data" / "mistake_memory" / "fix_history.jsonl"

def log_mistake(error_type: str, source_system: str, what_failed: str,
                error_message: str = "", traceback_summary: str = "",
                suspected_cause: str = "", fix_attempted: bool = False,
                fix_result: str = "", test_that_proved_fix: str = "",
                should_become_training_candidate: bool = False,
                approval_required: bool = True) -> dict[str, Any]:
    record = {
        "id": f"err_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
        "error_type": error_type,
        "source_system": source_system,
        "what_failed": what_failed,
        "error_message": error_message[:500],
        "traceback_summary": traceback_summary[:300],
        "suspected_cause": suspected_cause,
        "fix_attempted": fix_attempted,
        "fix_result": fix_result,
        "test_that_proved_fix": test_that_proved_fix,
        "should_become_training_candidate": should_become_training_candidate,
        "approval_required": approval_required,
        "created_at": datetime.now().isoformat(),
    }
    ERROR_BANK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_BANK_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

def log_fix(mistake_id: str, fix_description: str, fix_success: bool, test_result: str = "") -> dict[str, Any]:
    record = {
        "mistake_id": mistake_id,
        "fix_description": fix_description,
        "fix_success": fix_success,
        "test_result": test_result,
        "fixed_at": datetime.now().isoformat(),
    }
    FIX_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FIX_HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record

def get_mistakes(limit: int = 20) -> list[dict]:
    if not ERROR_BANK_PATH.exists():
        return []
    lines = [l for l in ERROR_BANK_PATH.read_text().splitlines() if l.strip()]
    mistakes = []
    for line in lines[-limit:]:
        try:
            mistakes.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return mistakes

def get_fixes(limit: int = 20) -> list[dict]:
    if not FIX_HISTORY_PATH.exists():
        return []
    lines = [l for l in FIX_HISTORY_PATH.read_text().splitlines() if l.strip()]
    fixes = []
    for line in lines[-limit:]:
        try:
            fixes.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return fixes

def main():
    print("Nova v074 -- Mistake Memory / Error Bank\n")
    m1 = log_mistake("import_error", "v069_self_scripting", "ModuleNotFoundError: no module named 'fake_module'",
                     "ImportError: No module named fake_module", "Traceback: import failed",
                     "Missing dependency", True, "Added missing import", "test passed", False, True)
    print(f"Logged mistake: {m1['id']}")
    m2 = log_mistake("router_error", "v052_router", "Unknown route for ambiguous query",
                     "Route could not be determined", "No matching keywords found",
                     "Query too short", False, "", "", True, True)
    print(f"Logged mistake: {m2['id']}")
    fix = log_fix(m1["id"], "Added missing import statement", True, "test passed")
    print(f"Logged fix: {fix['mistake_id']}")
    mistakes = get_mistakes()
    fixes = get_fixes()
    print(f"\nTotal mistakes: {len(mistakes)}, Fixes: {len(fixes)}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
