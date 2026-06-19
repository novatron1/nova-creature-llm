#!/usr/bin/env python3
"""v065 — Gold self-test: runs skill hands checks + nervous system tests."""

import json, sys
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v065_skill_hands import is_allowed, is_blocked, check_action
from v065_self_test_nervous_system import run_all_tests, SELF_TESTS

ERRORS = []
PASSES = []

def main():
    print("Nova Creature v065 — Gold Self-Test\n")

    # Phase 1: Skill hands checks
    print("Phase 1: Skill hands verification\n")
    allowed_actions = ["read_text_files", "list_project_files", "write_reports",
                       "create_sandbox_files", "run_allowed_scripts", "verify_checkpoints",
                       "create_backups_before_edits"]
    blocked_actions = ["delete_checkpoints", "delete_memory", "run_destructive_shell",
                       "run_real_robot_hardware"]

    for action in allowed_actions:
        if is_allowed(action):
            PASSES.append(f"Allowed action: {action}")
        else:
            ERRORS.append(f"Should be allowed: {action}")

    for action in blocked_actions:
        if is_blocked(action):
            PASSES.append(f"Blocked action: {action}")
        else:
            ERRORS.append(f"Should be blocked: {action}")

    # Phase 2: Nervous system tests
    print("Phase 2: Self-test nervous system\n")
    report = run_all_tests()
    health = report["health"]
    print(f"  Health: {health}")
    print(f"  Passed: {report['passed']}/{report['total_tests']}")

    if health == "healthy":
        PASSES.append("Self-test nervous system healthy")
    elif report["passed"] >= 7:
        PASSES.append(f"Self-test nervous system mostly healthy ({report['passed']}/{report['total_tests']})")
    else:
        ERRORS.append(f"Self-test nervous system degraded ({report['passed']}/{report['total_tests']})")

    for r in report["results"]:
        if not r["passed"]:
            ERRORS.append(f"  Failed: {r['id']} {r['name']}: {r.get('detail','')[:60]}")

    # Save report
    summary = {
        "version": "v065_gold_self_test",
        "created_at": datetime.now().isoformat(),
        "skill_hands_allowed": len(allowed_actions),
        "skill_hands_blocked": len(blocked_actions),
        "nervous_system_health": health,
        "nervous_system_passed": report["passed"],
        "nervous_system_total": report["total_tests"],
        "errors": len(ERRORS),
        "passes": len(PASSES),
    }
    (ROOT / "reports" / "v065_gold_self_test.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")
    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
