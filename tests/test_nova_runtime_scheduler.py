from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.research_scheduler import BudgetExceededError, ResearchScheduler  # noqa: E402


def test_scheduler_resumes_pending_task_after_restart(tmp_path) -> None:
    scheduler = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    task = scheduler.create_task(
        objective="collect evidence",
        tool_budget=3,
        time_budget_seconds=120,
        cost_budget=0.0,
    )
    scheduler.mark_running(task.task_id)

    scheduler2 = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    resumed = scheduler2.recover_pending_tasks()

    assert resumed
    assert resumed[0].task_id == task.task_id
    assert resumed[0].status == "running"


def test_scheduler_blocks_budget_overrun(tmp_path) -> None:
    scheduler = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    task = scheduler.create_task(
        objective="collect evidence",
        tool_budget=1,
        time_budget_seconds=10,
        cost_budget=0.0,
    )
    scheduler.record_tool_use(task.task_id, tool_name="web_search")
    with pytest.raises(BudgetExceededError):
        scheduler.record_tool_use(task.task_id, tool_name="web_search")


def test_scheduler_uses_pluggable_priority_and_safety_inputs(tmp_path) -> None:
    scheduler = ResearchScheduler(
        store_path=tmp_path / "research_tasks.jsonl",
        priority_ranker=lambda objective: {"priority_score": 0.9 if "evidence" in objective else 0.1},
        safety_gate=lambda objective: {"safety_score": 0.25 if "danger" in objective else 0.95},
    )
    safe = scheduler.create_task(
        objective="collect evidence",
        tool_budget=2,
        time_budget_seconds=20,
        cost_budget=0.0,
    )
    risky = scheduler.create_task(
        objective="dangerous research",
        tool_budget=2,
        time_budget_seconds=20,
        cost_budget=0.0,
    )

    assert safe.priority_score == 0.9
    assert safe.safety_score == 0.95
    assert risky.priority_score == 0.1
    assert risky.safety_score == 0.25
    risky_scheduler = ResearchScheduler(
        store_path=tmp_path / "risk_only.jsonl",
        priority_ranker=lambda objective: {"priority_score": 0.4},
        safety_gate=lambda objective: {"safety_score": 0.1},
    )
    risky_only = risky_scheduler.create_task(
        objective="dangerous research",
        tool_budget=2,
        time_budget_seconds=20,
        cost_budget=0.0,
    )
    assert risky_scheduler.dispatch_next().resume_reason == "safety_gate_blocked"
    assert risky_only.safety_score == 0.1
