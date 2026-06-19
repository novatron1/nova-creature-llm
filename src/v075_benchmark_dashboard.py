"""v075 — Central benchmark dashboard."""
from __future__ import annotations
import json, subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

BENCHMARK_TESTS = [
    ("v052_router", "src/v052_role_brain_router.py", ["--prompt", "What is 12 times 12"]),
    ("v057_dictionary", "src/v057_dictionary_conversation_router.py", ["--message", "Who created you?"]),
    ("v062_benchmark_gate", "src/v062_benchmark_gate.py", []),
    ("v064_memory_law", "src/v064_memory_law.py", []),
    ("v064_approval_constitution", "src/v064_approval_constitution.py", []),
    ("v065_self_test", "src/v065_self_test_nervous_system.py", []),
    ("v066_self_map", "src/v066_capability_self_map.py", []),
    ("v069_self_scripting", "src/v069_self_scripting_brain.py", []),
    ("v070_robot_sim", "src/v070_robot_sim_bridge.py", []),
    ("v071_safety_spine", "src/v071_robot_safety_spine.py", []),
    ("v072_sensor_registry", "src/v072_body_sensor_registry.py", []),
    ("v073_deployment_gate", "src/v073_robot_deployment_gate.py", []),
    ("v074_mistake_memory", "src/v074_mistake_memory.py", []),
]

def run_benchmark(name: str, script_path: str, args: list[str]) -> dict[str, Any]:
    full = ROOT / script_path
    if not full.exists():
        return {"name": name, "passed": False, "total": 1, "failed": 1,
                "percentage": 0.0, "status": "FILE_NOT_FOUND", "blockers": ["File not found"]}
    try:
        result = subprocess.run([sys.executable, str(full)] + args,
                                text=True, capture_output=True, timeout=30, cwd=ROOT)
        passed = result.returncode == 0
        return {"name": name, "passed": passed, "total": 1, "failed": 0 if passed else 1,
                "percentage": 100.0 if passed else 0.0,
                "status": "PASS" if passed else "FAIL",
                "returncode": result.returncode, "blockers": [] if passed else [result.stderr[:100]]}
    except Exception as e:
        return {"name": name, "passed": False, "total": 1, "failed": 1,
                "percentage": 0.0, "status": "ERROR", "blockers": [repr(e)]}

def run_all_benchmarks() -> dict[str, Any]:
    results = []
    total_pass = 0
    total_tests = len(BENCHMARK_TESTS)
    for name, script, args in BENCHMARK_TESTS:
        r = run_benchmark(name, script, args)
        results.append(r)
        if r["passed"]:
            total_pass += 1
    overall_pct = round((total_pass / total_tests) * 100, 1) if total_tests > 0 else 0
    return {
        "version": "v075_benchmark_dashboard",
        "created_at": datetime.now().isoformat(),
        "total_tests": total_tests,
        "total_passed": total_pass,
        "total_failed": total_tests - total_pass,
        "overall_percentage": overall_pct,
        "results": results,
        "all_passed": total_pass == total_tests,
    }

def main():
    print("Nova v075 -- Benchmark Dashboard\n")
    r = run_all_benchmarks()
    print(f"Tests: {r['total_passed']}/{r['total_tests']} passed ({r['overall_percentage']}%)")
    for res in r['results']:
        icon = "\u2705" if res['passed'] else "\u274c"
        print(f"  {icon} {res['name']}: {res['status']}")
    print(f"\nAll passed: {r['all_passed']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
