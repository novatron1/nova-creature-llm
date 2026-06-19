#!/usr/bin/env python3
"""Check v080 app builder mode."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v080_app_builder_mode import plan_app, write_starter_files, create_test_plan, static_check, package_project
E, P = [], []
def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v080 -- App Builder Checker\n")
    c(Path(ROOT/"src"/"v080_app_builder_mode.py").exists(), "src exists")
    plan = plan_app("Tiny task tracker web app")
    c("project_name" in plan, "plan has name")
    create_test_plan(plan)
    wr = write_starter_files(plan)
    c(len(wr["files_written"]) >= 4, f"files written: {wr['files_written']}")
    check = static_check(plan["project_path"])
    c(check["success"], "static check passes")
    c(check["file_count"] >= 5, f"files: {check['file_count']}")
    pkg = package_project(plan["project_path"])
    c(pkg["success"], "package works")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
