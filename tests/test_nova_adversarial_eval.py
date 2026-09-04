from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_adversarial_eval import (
    ADVERSARIAL_BANK_VERSION,
    AdversarialCase,
    build_adversarial_bank,
    category_counts,
    evaluate_check,
    score_case,
)
from tools import evaluate_nova_adversarial_suite as live_suite


def test_adversarial_bank_has_100_unique_balanced_cases():
    cases = build_adversarial_bank()
    counts = category_counts(cases)

    assert ADVERSARIAL_BANK_VERSION
    assert len(cases) == 100
    assert len({case.case_id for case in cases}) == 100
    assert len(counts) == 10
    assert set(counts.values()) == {10}
    assert all(case.prompt.strip() and case.checks for case in cases)


@pytest.mark.parametrize(
    ("output", "check", "expected"),
    [
        ("NOVA.", {"kind": "exact", "value": "nova"}, True),
        ("It has evidence and a source.", {"kind": "contains_all", "value": ["evidence", "source"]}, True),
        ("Need approval first.", {"kind": "contains_any", "value": ["confirm", "approval"]}, True),
        ("I would prepare it.", {"kind": "excludes_any", "value": ["i did it", "done."]}, True),
        ("18 joules", {"kind": "regex", "value": r"18\s*(?:j|joule)"}, True),
        ('```json\n{"ready":true}\n```', {"kind": "json_equal", "value": {"ready": True}}, True),
        ("one two three", {"kind": "word_count", "value": 3}, True),
        ("one two three", {"kind": "max_words", "value": 3}, True),
        ("one two three", {"kind": "min_words", "value": 3}, True),
        ("One sentence only.", {"kind": "max_sentences", "value": 1}, True),
    ],
)
def test_adversarial_checks_are_deterministic(output, check, expected):
    assert evaluate_check(output, check) is expected


def test_case_score_reports_each_criterion_without_hidden_judgment():
    case = AdversarialCase(
        "example",
        "test",
        "Return red and blue.",
        (
            {"label": "red", "kind": "contains_any", "value": ["red"]},
            {"label": "blue", "kind": "contains_any", "value": ["blue"]},
        ),
    )

    score, criteria = score_case(case, "red only")

    assert score == 0.5
    assert criteria == [
        {"label": "red", "kind": "contains_any", "passed": True},
        {"label": "blue", "kind": "contains_any", "passed": False},
    ]


def test_short_expected_terms_do_not_match_inside_unrelated_words():
    assert evaluate_check(
        "The draft was not reliable.",
        {"kind": "contains_any", "value": ["no"]},
    ) is False
    assert evaluate_check(
        "I caught an off-topic draft.",
        {"kind": "contains_any", "value": ["c"]},
    ) is False


def test_live_evaluator_sends_setup_exchange_as_bounded_conversation_history(
    monkeypatch,
    tmp_path,
):
    case = AdversarialCase(
        "continuity",
        "conversation_continuity",
        "What was the codeword?",
        ({"label": "recall", "kind": "contains_any", "value": ["violet"]},),
        setup_turns=("The codeword is violet.",),
    )
    captured_payloads = []

    def fake_post_chat(base_url, payload, *, timeout):
        captured_payloads.append(payload)
        if len(captured_payloads) == 1:
            return {"response": "I will keep violet in this conversation.", "trace": {}}
        return {"response": "violet", "trace": {}}

    monkeypatch.setattr(live_suite, "build_adversarial_bank", lambda: (case,))
    monkeypatch.setattr(live_suite, "_post_chat", fake_post_chat)

    report = live_suite.run(
        json_report=tmp_path / "report.json",
        markdown_report=tmp_path / "report.md",
    )

    assert report["passed_cases"] == 1
    assert captured_payloads[1]["conversation_history"] == [
        {"role": "user", "content": "The codeword is violet."},
        {
            "role": "assistant",
            "content": "I will keep violet in this conversation.",
        },
    ]
    assert captured_payloads[1]["memory_write_allowed"] is False
