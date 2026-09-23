from __future__ import annotations

import json
from pathlib import Path

from tools.nova_conversation_gate import load_cases, run_gate


def test_regression_fixture_expands_to_bounded_100_case_gate():
    fixture = Path(__file__).parent / "fixtures" / "nova_conversation_regression.json"
    seeds = json.loads(fixture.read_text(encoding="utf-8"))
    assert len(seeds) >= 10
    cases = load_cases(fixture, count=100)
    assert len(cases) == 100
    assert len({case["id"] for case in cases}) == 100


def test_regression_gate_keeps_answer_and_prompt_out_of_operational_metadata(tmp_path):
    fixture = Path(__file__).parent / "fixtures" / "nova_conversation_regression.json"
    report = run_gate(fixture, count=100, report_path=tmp_path / "gate.json")
    assert report["ok"] is True
    assert report["total"] == 100
    assert report["failed"] == 0
    assert report["privacy"]["prompt_content_stored"] is False
    assert report["privacy"]["answer_content_stored"] is False
    assert report["privacy"]["private_reasoning_stored"] is False
