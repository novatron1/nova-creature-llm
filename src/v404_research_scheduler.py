"""v404 — Autonomous Research Scheduler"""
from __future__ import annotations
from pathlib import Path

from nova_runtime.research_scheduler import ResearchScheduler


STORE_PATH = Path("data") / "research_tasks.jsonl"


def schedule_research(objective: str = "simulation research") -> dict:
    scheduler = ResearchScheduler(STORE_PATH)
    task = scheduler.create_task(
        objective=objective,
        tool_budget=3,
        time_budget_seconds=120,
        cost_budget=0.0,
    )
    return {
        "version":"v404_research_scheduler",
        "created_at":task.created_at,
        "sim_only":False,
        "real_hardware_enabled":False,
        "durable_task_record": task.to_dict(),
        "recoverable_tasks": len(scheduler.recover_pending_tasks()),
        "note":"Autonomous Research Scheduler module — durable task records enabled."
    }

def main():
    print(f"Nova v404_research_scheduler\n")
    r = schedule_research()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
