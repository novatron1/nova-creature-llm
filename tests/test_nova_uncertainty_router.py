from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_uncertainty_router import (  # noqa: E402
    UNCERTAINTY_ROUTER_VERSION,
    assess_request_difficulty,
    primary_answer_needs_larger_review,
)


HARD_ARCHITECTURE_PROMPT = (
    "Compare local SQLite vector memory with a remote vector database for a "
    "private mobile AI app. Analyze privacy, offline behavior, latency, migration "
    "risk, and cost, then recommend a staged architecture."
)


def test_complex_architecture_request_recommends_larger_local_review():
    assessment = assess_request_difficulty(HARD_ARCHITECTURE_PROMPT)

    assert assessment.version == UNCERTAINTY_ROUTER_VERSION
    assert assessment.tier == "hard"
    assert assessment.task_type == "reasoning"
    assert assessment.larger_local_recommended is True
    assert {"advanced_reasoning", "comparison_with_decision", "multi_constraint"}.issubset(
        assessment.signals
    )
    assert {"reasoning", "comparison", "constraint_tracking"}.issubset(
        assessment.required_capabilities
    )


def test_short_coding_markers_do_not_match_inside_unrelated_words():
    assessment = assess_request_difficulty(
        "Analyze a private architecture and recommend the best migration plan."
    )

    assert assessment.task_type == "reasoning"


def test_routine_chat_and_simple_math_stay_on_small_model():
    for prompt in ("Hi", "Tell me a joke", "What is 2 + 2?"):
        assessment = assess_request_difficulty(prompt)
        assert assessment.tier == "routine"
        assert assessment.larger_local_recommended is False


def test_volatile_fact_needs_evidence_not_automatically_a_larger_model():
    assessment = assess_request_difficulty("Who is the current president?")

    assert assessment.larger_local_recommended is False
    assert "freshness_not_model_size" in assessment.signals


def test_hard_short_primary_answer_needs_independent_review():
    assessment = assess_request_difficulty(HARD_ARCHITECTURE_PROMPT)

    assert primary_answer_needs_larger_review(
        assessment,
        "SQLite is private and cheap, while a remote vector database scales better.",
    ) is True


def test_trace_never_contains_prompt_or_answer_content():
    assessment = assess_request_difficulty(HARD_ARCHITECTURE_PROMPT)
    trace = assessment.as_trace()

    assert HARD_ARCHITECTURE_PROMPT not in str(trace)
    assert trace["content_logged"] is False
    assert trace["private_reasoning_used"] is False
    assert set(trace) == {
        "version",
        "difficulty_score",
        "difficulty_tier",
        "task_type",
        "signals",
        "required_capabilities",
        "larger_local_recommended",
        "threshold",
        "content_logged",
        "private_reasoning_used",
    }
