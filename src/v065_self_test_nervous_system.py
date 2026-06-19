"""v065 — Self-Test Nervous System

Runs all system tests: v057 dictionary, v059 router, v060 smart memory,
v061 learning loop, v062 benchmark, v063 dream, v064 memory law.
"""

from __future__ import annotations

import json, subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SELF_TESTS = [
    {"id": "st_001", "name": "Router baseline", "script": "src/v052_role_brain_router.py",
     "args": ["--prompt", "What is 12 times 12"], "check_stdout": "144"},
    {"id": "st_002", "name": "Dictionary lookup", "script": "src/v057_dictionary_conversation_router.py",
     "args": ["--message", "Who created you?"], "check_stdout": "Mr. Novotron"},
    {"id": "st_003", "name": "Benchmark gate", "script": "src/v062_benchmark_gate.py",
     "args": [], "check_returncode": 0},
    {"id": "st_004", "name": "Memory law", "script": "src/v064_memory_law.py",
     "args": [], "check_returncode": 0},
    {"id": "st_005", "name": "Approval constitution", "script": "src/v064_approval_constitution.py",
     "args": [], "check_returncode": 0},
    {"id": "st_006", "name": "Skill hands", "script": "src/v065_skill_hands.py",
     "args": [], "check_returncode": 0},
    {"id": "st_007", "name": "Capability self-map", "script": "src/v066_capability_self_map.py",
     "args": [], "check_returncode": 0},
    {"id": "st_008", "name": "v061 learning loop dry-run", "script": "scripts/v061_run_learning_loop.py",
     "args": ["--dry-run"], "check_returncode": 0},
    {"id": "st_009", "name": "v059 router uses v055", "script": "scripts/check_v059_router_uses_finetuned_brains.py",
     "args": [], "check_returncode": 0},
    {"id": "st_010", "name": "Smart memory capture available", "script": "src/v060_smart_memory_capture.py",
     "check_exists": True},
]


def root() -> Path:
    return ROOT


def run_self_test(test: dict[str, Any]) -> dict[str, Any]:
    test_id = test["id"]
    name = test["name"]
    script = test["script"]
    script_path = ROOT / script

    if test.get("check_exists"):
        return {
            "id": test_id, "name": name, "passed": script_path.exists(),
            "detail": f"exists={script_path.exists()}", "error": None,
        }

    args = [sys.executable, str(script_path)] + test.get("args", [])
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=30, cwd=ROOT)
        stdout = result.stdout
        stderr = result.stderr
        rc_ok = result.returncode == 0

        check_stdout = test.get("check_stdout")
        stdout_ok = check_stdout in stdout if check_stdout else True

        check_rc = test.get("check_returncode")
        rc_ok2 = result.returncode == check_rc if check_rc is not None else rc_ok

        passed = stdout_ok and rc_ok2
        return {
            "id": test_id, "name": name, "passed": passed,
            "returncode": result.returncode,
            "detail": stdout[:100] if passed else f"rc={result.returncode} {stderr[:100]}",
            "error": None if passed else stderr[:200],
        }
    except subprocess.TimeoutExpired:
        return {"id": test_id, "name": name, "passed": False, "detail": "timeout", "error": "timeout"}
    except Exception as e:
        return {"id": test_id, "name": name, "passed": False, "detail": "exception", "error": repr(e)}


def run_all_tests() -> dict[str, Any]:
    results = []
    for test in SELF_TESTS:
        r = run_self_test(test)
        results.append(r)

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    return {
        "version": "v065_self_test_nervous_system",
        "created_at": datetime.now().isoformat(),
        "total_tests": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "health": "healthy" if passed_count == total else "degraded",
        "results": results,
    }


def save_report(report: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / "v065_self_test_nervous_system_report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main() -> int:
    print("Nova Creature v065 — Self-Test Nervous System\n")
    report = run_all_tests()
    save_report(report)

    for r in report["results"]:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} {r['id']} {r['name']}")

    print(f"\n{'='*60}")
    print(f"  Health: {report['health']}")
    print(f"  Tests: {report['passed']}/{report['total_tests']} passed")
    print(f"  Report: reports/v065_self_test_nervous_system_report.json")
    return 0 if report["health"] == "healthy" else 1

if __name__ == "__main__":
    raise SystemExit(main())
