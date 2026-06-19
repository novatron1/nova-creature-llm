from __future__ import annotations

import json, sys, re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v052_role_brain_router import run as router_run
from v060_smart_memory_capture import classify_memory_event

ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]

BENCHMARK_SUITE: list[dict[str, Any]] = [
    {"id": "router_math",      "prompt": "What is 12 times 12?",       "expected_route": "left_hemisphere",           "expected_answer_substr": "144"},
    {"id": "router_identity",  "prompt": "Who created you?",           "expected_route": "memory_transformer",        "expected_answer_substr": "Mr. Novotron"},
    {"id": "router_planning",  "prompt": "Give me the next build plan","expected_route": "planner_transformer",        "expected_answer_substr": "Planner"},
    {"id": "router_imagination", "prompt": "Imagine the brain architecture","expected_route": "right_hemisphere",      "expected_answer_substr": "Right brain"},
    {"id": "router_critic",    "prompt": "What is my favorite color?", "expected_route": "critic_conscience_transformer", "expected_answer_substr": "do not know"},
    {"id": "memory_classify_project",  "prompt": "v059 passed all routes",  "expected_memory_type": "auto_project_memory"},
    {"id": "memory_classify_explicit", "prompt": "Remember this fact",       "expected_memory_type": "explicit_user_memory"},
    {"id": "memory_classify_uncertain", "prompt": "Maybe this is right",     "expected_memory_type": "pending_approval_memory"},
    {"id": "memory_classify_temp",      "prompt": "Do that",                 "expected_memory_type": "temporary_conversation_context"},
    {"id": "memory_classify_training",  "prompt": "The correct answer is X", "expected_memory_type": "training_candidate_memory"},
]


def root() -> Path:
    return ROOT


def run_benchmarks(suite: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run benchmark suite and return pass/fail per test."""
    if suite is None:
        suite = BENCHMARK_SUITE

    results = []
    passes = 0
    failures = 0

    for test in suite:
        test_id = test["id"]
        prompt = test["prompt"]

        if test_id.startswith("router_"):
            report = router_run(prompt)
            r = report.get("results", [{}])[0]
            actual_route = r.get("selected_route", "")
            actual_answer = r.get("final_answer", "")
            route_ok = actual_route == test.get("expected_route", "")
            answer_ok = test.get("expected_answer_substr", "") in actual_answer
            passed = route_ok and answer_ok
            results.append({
                "id": test_id, "passed": passed,
                "actual_route": actual_route, "actual_answer": actual_answer[:80],
                "route_ok": route_ok, "answer_ok": answer_ok,
            })

        elif test_id.startswith("memory_classify_"):
            cls = classify_memory_event(prompt)
            actual_type = cls["memory_type"]
            expected = test.get("expected_memory_type", "")
            passed = actual_type == expected
            results.append({
                "id": test_id, "passed": passed,
                "actual_memory_type": actual_type,
            })

        if passed:
            passes += 1
        else:
            failures += 1

    passed_pct = (passes / len(suite) * 100) if suite else 0

    return {
        "version": "v062_benchmark_gate",
        "created_at": datetime.now().isoformat(),
        "total": len(suite),
        "passed": passes,
        "failed": failures,
        "pass_rate_pct": round(passed_pct, 1),
        "gate_passed": failures == 0,
        "results": results,
    }


def check_gate(benchmark_result: dict[str, Any], label: str = "default") -> dict[str, Any]:
    """Check if benchmark gate passes. Returns decision dict."""
    gate_passed = benchmark_result["gate_passed"]
    result = {
        "label": label,
        "gate_passed": gate_passed,
        "pass_rate": benchmark_result["pass_rate_pct"],
        "total": benchmark_result["total"],
        "passed": benchmark_result["passed"],
        "failed": benchmark_result["failed"],
        "action": "promote" if gate_passed else "block",
        "summary": f"Gate {'PASSED ✅' if gate_passed else 'BLOCKED ❌'} "
                   f"({benchmark_result['passed']}/{benchmark_result['total']} passed, "
                   f"{benchmark_result['pass_rate_pct']}%)",
    }
    return result


def save_report(benchmark_result: dict[str, Any], gate_result: dict[str, Any] | None = None) -> Path:
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    report = {**benchmark_result, "gate": gate_result}
    path = reports_dir / "v062_benchmark_report.json"
    path.write_text(json.dumps(report, indent=2))
    return path


def main() -> int:
    print("Nova Creature v062 — Benchmark Gate\n")
    result = run_benchmarks()
    gate = check_gate(result)
    save_report(result, gate)

    for r in result["results"]:
        status = "✅" if r["passed"] else "❌"
        print(f"  {status} {r['id']}")
        if "actual_route" in r:
            print(f"     route: {r.get('actual_route','')} (ok={r.get('route_ok')})")
            print(f"     answer: {r.get('actual_answer','')[:60]} (ok={r.get('answer_ok')})")
        if "actual_memory_type" in r:
            print(f"     type: {r.get('actual_memory_type')}")

    print(f"\n{'='*60}")
    print(f"  Total: {result['total']}  Passed: {result['passed']}  Failed: {result['failed']}")
    print(f"  Rate:  {result['pass_rate_pct']}%")
    print(f"  Gate:  {gate['summary']}")
    print(f"  Report: reports/v062_benchmark_report.json")
    return 0 if gate["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
