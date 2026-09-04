from __future__ import annotations

from pathlib import Path

from nova_verifier import NovaVerifier, skipped_verification


def test_calculation_is_recomputed_deterministically() -> None:
    verifier = NovaVerifier()
    passed = verifier.verify(user_text="What is 12 * 4?", answer="12 × 4 = 48.")
    failed = verifier.verify(user_text="What is 12 * 4?", answer="12 × 4 = 49.")

    assert passed.passed
    assert not failed.passed
    assert failed.unsupported_claims
    assert failed.recommended_repair


def test_json_schema_is_validated() -> None:
    schema = {
        "type": "object",
        "required": ["count"],
        "properties": {"count": {"type": "integer"}},
        "additionalProperties": False,
    }
    verifier = NovaVerifier()

    assert verifier.verify(user_text="", answer='{"count":2}', response_schema=schema).passed
    result = verifier.verify(user_text="", answer='{"count":"two"}', response_schema=schema)
    assert not result.passed


def test_citations_must_exist_and_required_evidence_cannot_be_omitted() -> None:
    verifier = NovaVerifier()
    source = {"source_id": "guide", "chunk_number": 2}

    assert verifier.verify(
        user_text="According to the guide?",
        answer="The guide says this [guide:2].",
        sources=[source],
        require_sources=True,
    ).passed
    missing = verifier.verify(
        user_text="According to the guide?",
        answer="The guide says this [made-up:9].",
        sources=[source],
        require_sources=True,
    )
    assert not missing.passed
    assert missing.missing_evidence


def test_actions_and_files_require_observed_results(tmp_path: Path) -> None:
    expected_file = tmp_path / "created.txt"
    verifier = NovaVerifier()
    result = verifier.verify(
        user_text="create it",
        answer="Done.",
        expected_actions=[{"action_id": "a1"}],
        observed_actions=[{"action_id": "a1", "status": "attempted"}],
        expected_files=[expected_file],
    )

    assert not result.passed
    assert result.failed_actions == ["a1"]
    assert result.missing_evidence


def test_invalid_dates_duplicates_and_contradictions_are_flagged() -> None:
    verifier = NovaVerifier()
    answer = (
        "The launch date is 2026-02-31. "
        "Nova is ready. Nova is not ready. "
        "This long duplicated sentence should only appear once in the answer. "
        "This long duplicated sentence should only appear once in the answer."
    )
    result = verifier.verify(user_text="", answer=answer)

    assert not result.passed
    assert any("Invalid calendar date" in item for item in result.unsupported_claims)
    assert result.conflicting_evidence


def test_model_critic_runs_only_after_deterministic_summary() -> None:
    observed = {}

    def critic(summary):
        observed.update(summary)
        return {"passed": True, "summary": "No additional issue."}

    result = NovaVerifier().verify(
        user_text="Explain architecture",
        answer="Nova is a cognitive layer.",
        model_critic=critic,
    )
    assert result.passed
    assert "deterministic_passed" in observed
    assert "answer" not in observed
    assert result.checks[-1]["check"] == "bounded_model_critic"


def test_low_risk_skip_is_explicit() -> None:
    result = skipped_verification()
    assert result.passed
    assert result.skipped
    assert result.safe_trace()["answer_content_logged"] is False
