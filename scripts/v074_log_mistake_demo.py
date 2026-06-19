#!/usr/bin/env python3
"""v074 — Log mistake demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v074_mistake_memory import log_mistake, log_fix, get_mistakes, get_fixes

def main():
    print("Nova v074 -- Log Mistake Demo\n")
    m1 = log_mistake("import_error", "v069_self_scripting",
                     "ModuleNotFoundError: no module named 'fake_module'",
                     "ImportError: No module named fake_module",
                     "Traceback (most recent call last):...",
                     "Missing dependency in sandbox script",
                     True, "Added import statement", "test passed", False, True)
    print(f"Mistake 1: {m1['id']}")
    print(f"  Type: {m1['error_type']}")
    print(f"  Source: {m1['source_system']}")
    print(f"  Training candidate: {m1['should_become_training_candidate']}")
    print(f"  Approval required: {m1['approval_required']}")
    m2 = log_mistake("router_error", "v052_router",
                     "Unknown route for ambiguous query 'do that'",
                     "Router returned unknown_fallback",
                     "No matching keywords found in query",
                     "Query too short for reliable routing",
                     False, "", "", True, True)
    print(f"Mistake 2: {m2['id']}")
    print(f"  Type: {m2['error_type']}")
    fix = log_fix(m1["id"], "Added import statement to sandbox script", True, "Script now runs successfully")
    print(f"Fix logged for: {fix['mistake_id']}")
    mistakes = get_mistakes()
    fixes = get_fixes()
    print(f"\nMistakes: {len(mistakes)}, Fixes: {len(fixes)}")
    (ROOT/"reports"/"v074_mistake_memory_status.json").write_text(json.dumps({
        "version": "v074_mistake_memory_demo", "created_at": datetime.now().isoformat(),
        "mistakes_logged": len(mistakes), "fixes_logged": len(fixes)}, indent=2))
    print(f"Report: reports/v074_mistake_memory_status.json")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
