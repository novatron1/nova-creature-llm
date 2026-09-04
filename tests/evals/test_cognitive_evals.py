from __future__ import annotations

import json
from pathlib import Path

from tests.evals.harness import write_eval_report
from tests.evals.harness import write_behavior_eval_report


def test_cognitive_eval_suite_is_machine_readable_and_all_tasks_pass(tmp_path: Path) -> None:
    destination = tmp_path / "nova_cognitive_evals.json"
    report = write_eval_report(destination)
    loaded = json.loads(destination.read_text(encoding="utf-8"))

    assert report["summary"]["total"] == 20
    assert report["summary"]["failed"] == 0
    assert loaded["summary"]["score"] == 1.0
    required_fields = {
        "task_name",
        "passed",
        "exact_score",
        "semantic_score",
        "latency_ms",
        "tool_call_count",
        "input_tokens",
        "output_tokens",
        "reasoning_mode",
        "memory_retrieved",
        "sources_retrieved",
        "verification_result",
        "failure_category",
    }
    assert all(required_fields.issubset(task) for task in loaded["tasks"])


def test_behavior_eval_harness_writes_bank_report(tmp_path: Path) -> None:
    destination = tmp_path / "nova_behavior_evals.json"
    bank_path = Path(__file__).resolve().parents[1] / "fixtures" / "nova_creature_behavior_eval_bank.json"
    report = write_behavior_eval_report(destination, bank_path)
    loaded = json.loads(destination.read_text(encoding="utf-8"))

    assert report["total"] == 8
    assert report["passed"] == 8
    assert loaded["bank_categories"]
