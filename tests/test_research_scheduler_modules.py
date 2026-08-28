from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import v404_research_scheduler as v404  # noqa: E402
import v405_research_priority_ranker as v405  # noqa: E402
import v406_research_safety_gate as v406  # noqa: E402
import v498_research_audit_log as v498  # noqa: E402


def test_v404_returns_durable_task_record(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v404, "STORE_PATH", tmp_path / "research_tasks.jsonl")

    result = v404.schedule_research("resume durable research")

    assert result["sim_only"] is False
    assert result["durable_task_record"]["objective"] == "resume durable research"
    assert result["recoverable_tasks"] == 1


def test_v405_scores_priority_and_persists_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v405, "STORE_PATH", tmp_path / "research_tasks.jsonl")

    result = v405.rank_research_priority("urgent research checkpoint")

    assert result["sim_only"] is False
    assert result["priority_score"] >= 0.5
    assert result["durable_task_record"]["objective"] == "urgent research checkpoint"


def test_v406_scores_safety_and_persists_task(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v406, "STORE_PATH", tmp_path / "research_tasks.jsonl")

    result = v406.gate_research_safety("dangerous research")

    assert result["sim_only"] is False
    assert result["allowed"] is False
    assert result["safety_score"] < 0.5
    assert result["durable_task_record"]["objective"] == "dangerous research"


def test_v498_reads_durable_audit_state(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(v498, "STORE_PATH", tmp_path / "research_tasks.jsonl")
    monkeypatch.setattr(v404, "STORE_PATH", tmp_path / "research_tasks.jsonl")

    v404.schedule_research("audit state")
    result = v498.log_research_audit()

    assert result["sim_only"] is False
    assert result["durable_task_records"] == 1
    assert result["ledger_entries"] >= 1
    assert result["open_tasks"] == 1
