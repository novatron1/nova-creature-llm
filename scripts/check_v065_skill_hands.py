#!/usr/bin/env python3
"""Check v065 skill hands and self-test nervous system."""

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v065_skill_hands import is_allowed, is_blocked, check_action, list_allowed_actions, list_blocked_actions

ERRORS = []
PASSES = []

def check(cond, msg):
    if cond:
        PASSES.append(f"  ✅ {msg}")
    else:
        ERRORS.append(f"  ❌ {msg}")

def main():
    print("Nova Creature v065 — Skill Hands Checker\n")

    # 1. Files exist
    print("1. Checking source files…")
    for f in [ROOT/"src"/"v065_skill_hands.py", ROOT/"src"/"v065_self_test_nervous_system.py"]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Allowed actions
    print("2. Checking allowed actions…")
    allowed = list_allowed_actions()
    check(len(allowed) == 10, f"10 allowed actions ({len(allowed)})")
    for a in allowed:
        check(not a["blocked"], f"  {a['action']} is allowed")

    # 3. Blocked actions
    print("3. Checking blocked actions…")
    blocked = list_blocked_actions()
    check(len(blocked) == 7, f"7 blocked actions ({len(blocked)})")
    for a in blocked:
        check(a["blocked"], f"  {a['action']} is blocked")

    # 4. Individual checks
    print("4. Testing action checks…")
    check(is_allowed("read_text_files"), "read_text_files allowed")
    check(is_allowed("write_reports"), "write_reports allowed")
    check(not is_allowed("delete_checkpoints"), "delete_checkpoints blocked")
    check(is_blocked("delete_checkpoints"), "delete_checkpoints reported as blocked")
    check(is_blocked("run_real_robot_hardware"), "run_real_robot_hardware blocked")
    check(is_blocked("delete_memory"), "delete_memory blocked")

    # 5. Check action detail
    print("5. Testing check_action…")
    r1 = check_action("read_text_files")
    check(r1["allowed"], "check_action read_text_files allowed")
    r2 = check_action("run_real_robot_hardware")
    check(r2["blocked"], "check_action real_robot blocked")
    check("reason" in r2, "blocked action has reason")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(e)

    if ERRORS:
        print("\nFAIL: v065 check did not pass")
        return 1
    print("\nPASS: v065 skill hands + self-test nervous system installed")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
