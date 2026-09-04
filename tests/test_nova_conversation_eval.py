from __future__ import annotations

import hashlib
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_conversation_eval import (  # noqa: E402
    CONVERSATION_EVAL_VERSION,
    load_conversation_eval_pack,
    run_conversation_eval,
)
from nova_adversarial_eval import evaluation_bank_manifest  # noqa: E402


PACK = ROOT / "data" / "evals" / "nova_conversation_variations_v1.json"
TRAINING_DATA = ROOT / "data" / "conversation_training_data.jsonl"


def _digest(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_versioned_pack_contains_at_least_five_hundred_unique_cases() -> None:
    cases = load_conversation_eval_pack(PACK)

    assert len(cases) >= 500
    assert len({case.case_id for case in cases}) == len(cases)
    assert len(
        {
            (
                " ".join(case.prompt.lower().split()),
                case.expected_intent_family,
            )
            for case in cases
        }
    ) == len(cases)
    assert {
        "social",
        "relationship",
        "followup",
        "current_fact",
        "recovery",
    } <= {case.category for case in cases}


def test_decision_eval_reports_exact_failures_without_training_writes() -> None:
    cases = load_conversation_eval_pack(PACK)
    before = _digest(TRAINING_DATA)

    report = run_conversation_eval(cases[:25])

    assert report.total == 25
    assert report.failed == 0
    assert report.training_writes == 0
    assert report.content_logged is False
    assert _digest(TRAINING_DATA) == before


def test_complete_decision_pack_passes_without_prompt_content_in_report() -> None:
    cases = load_conversation_eval_pack(PACK)

    report = run_conversation_eval(cases)
    payload = report.to_dict()

    assert report.total >= 500
    assert report.failed == 0
    assert report.passed == report.total
    assert all(score == 1.0 for score in report.category_scores.values())
    assert payload["content_logged"] is False
    assert "prompt" not in payload


def test_evaluation_manifest_links_adversarial_and_conversation_banks() -> None:
    manifest = evaluation_bank_manifest(
        conversation_case_count=len(load_conversation_eval_pack(PACK))
    )

    assert manifest["evaluation_only"] is True
    assert manifest["training_writes"] == 0
    assert manifest["adversarial"]["case_count"] == 100
    assert manifest["conversation"]["version"] == CONVERSATION_EVAL_VERSION
    assert manifest["conversation"]["case_count"] >= 500


def test_live_server_diagnostic_marks_conversation_pack_evaluation_only() -> None:
    import nova_enhanced_server as server

    status = server._conversation_evaluation_status()

    assert status["ok"] is True
    assert status["case_count"] >= 500
    assert status["evaluation_only"] is True
    assert status["training_allowed"] is False
    assert status["content_logged"] is False


def test_evaluation_only_turn_disables_legacy_conversation_training_writer() -> None:
    import nova_enhanced_server as server

    server._CONVERSATION_WRITES_ALLOWED.set(True)
    _response, trace = server.brain_route(
        "Hi",
        {
            "evaluation_only": True,
            "conversation_summary_write_allowed": False,
        },
    )

    assert server._CONVERSATION_WRITES_ALLOWED.get() is False
    assert trace["evaluation_only"] is True
    assert trace["training_write_allowed"] is False
