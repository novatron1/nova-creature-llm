from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import evaluate_lora_grade_levels as grade_eval


def test_grade_eval_has_three_cases_per_band():
    cases = grade_eval._cases()
    assert len(cases) == 15
    bands = {}
    for case in cases:
        bands[case.band] = bands.get(case.band, 0) + 1
    assert set(bands.values()) == {3}


def test_probability_rubric_gives_partial_credit_to_correct_truncated_work():
    case = next(item for item in grade_eval._cases() if item.case_id == "high_probability")
    output = (
        "There are 36 possible outcomes. The favorable combinations are "
        "(2,6), (3,5), (4,4), (5,3), and (6,2). There are 5 such combinations out of"
    )
    criteria = [grade_eval._check_result(output, check) for check in case.checks]
    assert criteria == [False, True, True]


def test_advanced_logic_rubric_rejects_invalid_no_answer():
    case = next(item for item in grade_eval._cases() if item.case_id == "advanced_logic")
    output = "No. Artists are not necessarily engineers."
    criteria = [grade_eval._check_result(output, check) for check in case.checks]
    assert criteria == [False, False]


def test_rescore_changes_only_scoring_fields(tmp_path):
    cases = grade_eval._cases()
    report_path = tmp_path / "report.json"
    original_outputs = {
        case.case_id: "56" if case.case_id == "elementary_arithmetic" else ""
        for case in cases
    }
    report = {
        "adapter_id": "test-adapter",
        "results": [
            {
                "case_id": case.case_id,
                "band": case.band,
                "output": original_outputs[case.case_id],
                "latency_ms": 1,
            }
            for case in cases
        ],
    }
    report_path.write_text(json.dumps(report), encoding="utf-8")

    rescored = grade_eval.rescore_report(report_path)

    assert rescored["scoring_audit"]["generation_rerun"] is False
    assert rescored["scoring_audit"]["model_outputs_changed"] is False
    assert {
        item["case_id"]: item["output"] for item in rescored["results"]
    } == original_outputs
    arithmetic = next(
        item for item in rescored["results"] if item["case_id"] == "elementary_arithmetic"
    )
    assert arithmetic["score"] == 1.0
