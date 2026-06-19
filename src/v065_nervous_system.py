from __future__ import annotations

import json, sys, subprocess
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SELF_TESTS: list[dict[str, Any]] = [
    {"id": "st_001", "name": "Router baseline", "script": "src/v052_role_brain_router.py",
     "args": ["--prompt", "What is 12 times 12"], "check_stdout": "144"},
    {"id": "st_002", "name": "Dictionary lookup", "script": "src/v057_dictionary_conversation_router.py",
     "args": ["--message", "Who created you?"], "check_stdout": "Mr. Novotron"},
    {"id": "st_003", "name": "Benchmark gate", "script": "src/v062_benchmark_gate.py", "args": [],
     "check_returncode": 0},
    {"id": "st_004", "name": "Checkpoint resolver", "script": "src/v059_checkpoint_resolver.py", "args": [],
     "check_returncode": 0},
    {"id": "st_005", "name": "Inner voice", "script": "src/v063_inner_voice.py",
     "args": ["--prompt", "Who created you?"], "check_stdout": "INNER VOICE"},
    {"id": "st_006", "name": "Smart memory classify", "script": "src/v060_smart_memory_capture.py",
     "check_exists": True},
    {"id": "st_007", "name": "Memory constitution", "script": "src/v064_memory_constitution.py", "args": [],
     "check_returncode": 0},
    {"id": "st_008", "name": "Multi-source growth", "script": "src/v062_multi_source_growth.py", "args": [],
     "check_returncode": 0},
    {"id": "st_009", "name": "v054 builder available", "script": "scripts/v054_role_checkpoint_builder.py",
     "check_exists": True},
    {"id": "st_010", "name": "v055 finetune available", "script": "scripts/v055_finetune_role_brains.py",
     "check_exists": True},
]


def root() -> Path:
    return ROOT


def run_self_test(test: dict[str, Any]) -> dict[str, Any]:
    """Run a single self-test and return pass/fail."""
    test_id = test["id"]
    name = test["name"]
    script = test["script"]

    # Check file exists
    script_path = root() / script
    if test.get("check_exists"):
        return {
            "id": test_id, "name": name, "passed": script_path.exists(),
            "detail": f"exists={script_path.exists()}", "error": None,
        }

    # Module check
    if test.get("check_module"):
        try:
            __import__(test["check_module"], fromlist=["dummy"])
            return {"id": test_id, "name": name, "passed": True, "detail": "module imported", "error": None}
        except Exception as e:
            return {"id": test_id, "name": name, "passed": False, "detail": "import failed", "error": repr(e)}

    # Script execution
    args = [sys.executable, str(script_path)] + test.get("args", [])
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=30, cwd=root())
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
            "stdout_match": check_stdout in stdout if check_stdout else "N/A",
            "detail": stdout[:100] if passed else f"rc={result.returncode} {stderr[:100]}",
            "error": None if passed else stderr[:200],
        }
    except subprocess.TimeoutExpired:
        return {"id": test_id, "name": name, "passed": False, "detail": "timeout", "error": "timeout"}
    except Exception as e:
        return {"id": test_id, "name": name, "passed": False, "detail": "exception", "error": repr(e)}


def run_all_tests() -> dict[str, Any]:
    """Run the full self-test nervous system."""
    results = []
    for test in SELF_TESTS:
        r = run_self_test(test)
        results.append(r)

    passed_count = sum(1 for r in results if r["passed"])
    total = len(results)

    return {
        "version": "v065_nervous_system",
        "created_at": datetime.now().isoformat(),
        "total_tests": total,
        "passed": passed_count,
        "failed": total - passed_count,
        "health": "healthy" if passed_count == total else "degraded",
        "results": results,
    }


def save_report(report: dict[str, Any]) -> Path:
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / "v065_nervous_system_report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main() -> int:
    print("Nova Creature v065 — Self-Test Nervous System\n")
    report = run_all_tests()
    save_report(report)

    for r in report["results"]:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} {r['id']} {r['name']}")
        if r.get("detail"):
            print(f"     {r['detail'][:80]}")

    print(f"\n{'='*60}")
    print(f"  Health: {report['health']}")
    print(f"  Tests: {report['passed']}/{report['total_tests']} passed")
    print(f"  Report: reports/v065_nervous_system_report.json")
    return 0 if report["health"] == "healthy" else 1


if __name__ == "__main__":
    raise SystemExit(main())
