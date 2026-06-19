"""v822_gold_regression_test — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def gold_regression_test():
    """Regression test confirming no existing systems broke."""
    tests = []; passed = 0; failed = 0
    # v700 core
    try:
        from v700_real_intelligence_growth_final_report import generate_real_intelligence_growth_final_report
        r = generate_real_intelligence_growth_final_report()
        ok = r.get("growth_proven") == True
        tests.append({"test": "v700_core_intact", "passed": ok, "detail": f"growth: {r.get('growth_proven')}"})
        passed += ok; failed += not ok
    except: tests.append({"test": "v700_core_intact", "passed": False, "detail": "import failed"}); failed += 1
    # v750 sensory body
    try:
        from v750_readiness_report import readiness_report
        r = readiness_report()
        ok = r.get("all_checks_passed") == True
        tests.append({"test": "v750_sensory_body_intact", "passed": ok, "detail": f"pass: {r.get('all_checks_passed')}"})
        passed += ok; failed += not ok
    except: tests.append({"test": "v750_sensory_body_intact", "passed": False, "detail": "import failed"}); failed += 1
    # v775 people memory
    try:
        from v775_people_memory_report import people_memory_report
        r = people_memory_report()
        ok = r.get("all_checks_passed") == True
        tests.append({"test": "v775_people_memory_intact", "passed": ok, "detail": f"pass: {r.get('all_checks_passed')}"})
        passed += ok; failed += not ok
    except: tests.append({"test": "v775_people_memory_intact", "passed": False, "detail": "import failed"}); failed += 1
    # v800 rapid learning
    try:
        from v800_rapid_learning_final_report import rapid_learning_final_report
        r = rapid_learning_final_report()
        ok = r.get("all_checks_passed") == True
        tests.append({"test": "v800_rapid_learning_intact", "passed": ok, "detail": f"pass: {r.get('all_checks_passed')}"})
        passed += ok; failed += not ok
    except: tests.append({"test": "v800_rapid_learning_intact", "passed": False, "detail": "import failed"}); failed += 1
    return {"version": "v822_gold_regression_test", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    print(f"Nova v822_gold_regression_test")
    r = gold_regression_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
