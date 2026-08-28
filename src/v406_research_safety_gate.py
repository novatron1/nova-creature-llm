"""v406 — Research Safety Gate"""
from __future__ import annotations
from pathlib import Path

from nova_runtime.research_scheduler import ResearchScheduler


STORE_PATH = Path("data") / "research_tasks.jsonl"


def _safety_gate(objective: str) -> dict[str, float | bool | str]:
    lowered = objective.lower()
    blocked = any(token in lowered for token in ("weapon", "explosive", "credential", "malware", "dangerous"))
    score = 0.15 if blocked else 1.0
    return {
        "allowed": not blocked,
        "safety_score": score,
        "objective": objective,
    }


def gate_research_safety(objective: str = "research objective") -> dict:
    scheduler = ResearchScheduler(STORE_PATH, safety_gate=_safety_gate)
    task = scheduler.create_task(
        objective=objective,
        tool_budget=1,
        time_budget_seconds=30,
        cost_budget=0.0,
    )
    return {
        "version": "v406_research_safety_gate",
        "created_at": task.created_at,
        "sim_only": False,
        "real_hardware_enabled": False,
        "allowed": task.safety_score >= 0.5,
        "safety_score": task.safety_score,
        "durable_task_record": task.to_dict(),
        "note": "Research Safety Gate now evaluates durable research tasks.",
    }

def main():
    print(f"Nova v406_research_safety_gate\n")
    r = gate_research_safety()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
