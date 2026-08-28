"""v405 — Research Priority Ranker"""
from __future__ import annotations
from pathlib import Path

from nova_runtime.research_scheduler import ResearchScheduler


STORE_PATH = Path("data") / "research_tasks.jsonl"


def _priority_ranker(objective: str) -> dict[str, float | str]:
    words = [token for token in objective.lower().split() if token]
    score = 0.35
    if any(token in objective.lower() for token in ("urgent", "priority", "blocked")):
        score += 0.25
    if len(words) >= 8:
        score += 0.15
    if any(token in objective.lower() for token in ("research", "verify", "resume", "checkpoint")):
        score += 0.15
    return {
        "priority_score": round(min(1.0, score), 3),
        "objective": objective,
    }


def rank_research_priority(objective: str = "research objective") -> dict:
    scheduler = ResearchScheduler(STORE_PATH, priority_ranker=_priority_ranker)
    task = scheduler.create_task(
        objective=objective,
        tool_budget=1,
        time_budget_seconds=30,
        cost_budget=0.0,
    )
    return {
        "version": "v405_research_priority_ranker",
        "created_at": task.created_at,
        "sim_only": False,
        "real_hardware_enabled": False,
        "priority_score": task.priority_score,
        "objective": task.objective,
        "durable_task_record": task.to_dict(),
        "note": "Research Priority Ranker now scores durable research tasks.",
    }

def main():
    print(f"Nova v405_research_priority_ranker\n")
    r = rank_research_priority()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
