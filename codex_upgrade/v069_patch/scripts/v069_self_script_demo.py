"""v069 Self-Scripting Demo

Tests:
- Plan a report script
- Write it to sandbox
- Run it
- Verify output
- Save report
"""

from __future__ import annotations

import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v069_self_scripting_brain import plan_script, write_script, test_script

ERRORS = []
PASSES = []

def main():
    print("Nova Creature v069 — Self-Scripting Brain Demo\n")

    # Step 1: Plan
    print("Step 1: Planning a status report script…")
    goal = "Generate a consolidated status report from all reports"
    plan = plan_script(goal)
    assert plan["script_name"], "plan produced a script name"
    assert plan["safe"], "plan is safe"
    print(f"  Script: {plan['script_name']}")
    print(f"  Steps: {', '.join(plan['steps'])}")
    PASSES.append("Planned script successfully")

    # Step 2: Write
    print("\nStep 2: Writing script to sandbox…")
    write_result = write_script(plan)
    assert write_result["script_path"], "script was written"
    assert write_result["sandboxed"], "script is in sandbox"
    print(f"  Path: {write_result['script_path']}")
    print(f"  Sandboxed: {write_result['sandboxed']}")
    PASSES.append("Wrote script to sandbox")

    # Step 3: Test
    print("\nStep 3: Testing script…")
    script_path = ROOT / write_result["script_path"]
    test_result = test_script(script_path)
    status = "PASS" if test_result.get("ok") else "FAIL"
    print(f"  Result: {status}")
    print(f"  Returncode: {test_result.get('returncode')}")
    if test_result.get("stdout"):
        print(f"  Output: {test_result['stdout'][:100]}")
    if test_result.get("ok"):
        PASSES.append("Script ran successfully")
    else:
        ERRORS.append(f"Script test failed: {test_result.get('stderr', test_result.get('error', ''))[:100]}")

    # Step 4: Verify output
    print("\nStep 4: Verifying output…")
    output_path = ROOT / "reports" / f"{Path(plan['output']).stem}.json"
    output_path_final = ROOT / plan["output"]
    if output_path_final.exists():
        data = json.loads(output_path_final.read_text())
        print(f"  Output file: {plan['output']}")
        print(f"  Status: {data.get('status')}")
        PASSES.append("Script produced output file")
    else:
        # Try alternative naming
        import glob
        reports = list((ROOT / "reports").glob("*consolidated*"))
        if reports:
            print(f"  Output file: {reports[0].relative_to(ROOT)}")
            PASSES.append("Script produced output file (alternative name)")
        else:
            ERRORS.append("Output file not found")

    # Step 5: Save report
    report = {
        "version": "v069_self_scripting_demo",
        "created_at": __import__("datetime").datetime.now().isoformat(),
        "goal": goal,
        "plan": plan,
        "write": write_result,
        "test": test_result,
        "passed": len(PASSES),
        "failed": len(ERRORS),
    }
    report_path = ROOT / "reports" / "v069_self_scripting_status.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nDemo report: {report_path.relative_to(ROOT)}")

    # Final
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")

    return 0 if not ERRORS else 1


if __name__ == "__main__":
    raise SystemExit(main())
