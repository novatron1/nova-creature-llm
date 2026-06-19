"""v087 — Multi-Step Thought Planner. Plans long goals through steps."""
from __future__ import annotations
from datetime import datetime
from typing import Any

GOAL_TYPES = [
    "app_upgrade", "learning_loop", "benchmark", "robot_simulation",
    "debugging", "training", "self_improvement",
]


def plan_goal(goal: str, context: dict | None = None) -> dict[str, Any]:
    g = goal.lower()
    goal_type = "self_improvement"
    for gt in GOAL_TYPES:
        if gt.replace("_", " ") in g:
            goal_type = gt
            break
    if "reasoning" in g or "smart" in g or "intelligence" in g:
        goal_type = "self_improvement"

    steps = [
        "1. Analyze current state and define target",
        "2. Design the improvement or feature",
        "3. Build the core implementation",
        "4. Create tests (checker + gold test)",
        "5. Run tests and verify pass rate",
        "6. Run regression against v059/v061/v066",
        "7. Generate report and promote if benchmarks pass",
    ]
    if goal_type == "benchmark":
        steps.insert(2, "Define benchmark criteria and passing threshold")
    elif goal_type == "debugging":
        steps = ["1. Reproduce the error", "2. Isolate root cause", "3. Design fix", "4. Test fix", "5. Verify regression", "6. Report"]

    return {
        "version": "v087_multistep_planner",
        "created_at": datetime.now().isoformat(),
        "goal": goal,
        "goal_type": goal_type,
        "steps": steps,
        "dependencies": ["v062 benchmark gate must pass", "v059 router must stay on v055"],
        "blockers": [],
        "required_files": ["src/", "scripts/check_*.py", "scripts/*_gold_*_test.py"],
        "required_tests": ["checker test", "gold test", "regression test"],
        "risks": ["May cause regression if not careful", "Must preserve existing behavior"],
        "safety_rules": ["No real robot movement", "No overwrite without backup", "No training uncertain memory"],
        "benchmark_required": True,
        "next_action": "design and build the first iteration",
        "done_definition": "All tests pass, regression clean, report generated, benchmarks stable or improved",
    }


def main() -> int:
    print("Nova v087 -- Multi-Step Planner\n")
    p = plan_goal("Make Nova smarter by improving reasoning, self-checking, and benchmarks.")
    print(f"Goal: {p['goal'][:60]}...")
    print(f"Type: {p['goal_type']}")
    print(f"Steps ({len(p['steps'])}):")
    for s in p['steps']:
        print(f"  {s}")
    print(f"\nDeps: {', '.join(p['dependencies'])}")
    print(f"Next: {p['next_action']}")
    print(f"Done when: {p['done_definition'][:60]}...")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
