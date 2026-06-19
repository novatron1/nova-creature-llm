#!/usr/bin/env python3
"""v080 — App builder demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v080_app_builder_mode import plan_app, write_starter_files, create_test_plan, static_check

def main():
    print("Nova v080 -- App Builder Demo\n")
    plan = plan_app("Make a tiny task tracker web app")
    print(f"App idea: {plan['app_idea']}")
    print(f"Project: {plan['project_path']}")
    print(f"Suggested files: {plan['suggested_files']}")
    write_starter_files(plan)
    create_test_plan(plan)
    check = static_check(plan["project_path"])
    print(f"\nCreated files:")
    for f in check['files']:
        print(f"  {f}")
    print(f"\nSandbox used: {plan['use_sandbox']}")
    (ROOT / "reports" / "v080_app_builder_status.json").write_text(json.dumps({
        "version": "v080_app_builder_demo", "created_at": datetime.now().isoformat(),
        "plan": plan, "files": check['files']}, indent=2))
    print(f"Report: reports/v080_app_builder_status.json\nPASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
