import json
from dataclasses import asdict
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_types import (
    DOMAIN_NAMES,
    GenerationResult,
    PromotionDecision,
    ROLE_NAMES,
    RoutePrediction,
)


def test_generation_result_requires_transformer_evidence():
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path="checkpoints/brain_slots/left_hemisphere/winner.pt",
        checkpoint_hash="a" * 64,
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    assert ROLE_NAMES == (
        "left_hemisphere",
        "right_hemisphere",
        "memory_transformer",
        "planner_transformer",
        "critic_conscience_transformer",
        "dream_simulation_transformer",
        "speech_output_transformer",
    )
    assert result.ok is True
    trace = result.to_trace()
    assert trace["source"] == "transformer"
    assert trace["checkpoint_hash"] == "a" * 64
    assert json.dumps(trace, allow_nan=False)


def test_generation_result_with_error_is_not_ok():
    result = GenerationResult.failed("planner_transformer", "checkpoint missing")
    assert result.ok is False
    assert result.error == "checkpoint missing"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"checkpoint_hash": "z" * 64},
        {"checkpoint_path": ""},
        {"role": "unknown_role"},
        {"tokens_generated": -1},
        {"elapsed_seconds": float("nan")},
        {"tokens_per_second": float("inf")},
        {"finish_reason": "stop"},
    ],
)
def test_generation_result_rejects_bad_evidence(kwargs):
    base = dict(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path="checkpoints/brain_slots/left_hemisphere/winner.pt",
        checkpoint_hash="a" * 64,
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    base.update(kwargs)
    result = GenerationResult(**base)
    assert result.ok is False


@pytest.mark.parametrize(
    "checkpoint_path",
    [
        "artifacts/transformer_training/winner.pt",
        "../checkpoints/left_hemisphere/winner.pt",
        "checkpoints/left_hemisphere/winner.txt",
    ],
)
def test_generation_result_rejects_malformed_checkpoint_paths(checkpoint_path):
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path=checkpoint_path,
        checkpoint_hash="a" * 64,
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    assert result.ok is False


@pytest.mark.parametrize("tokens_generated", [float("inf"), 1.5, True])
def test_generation_result_rejects_non_integer_token_counts(tokens_generated):
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path="checkpoints/brain_slots/left_hemisphere/winner.pt",
        checkpoint_hash="a" * 64,
        tokens_generated=tokens_generated,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    assert result.ok is False


def test_generation_result_handles_none_evidence_without_raising():
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path=None,  # type: ignore[arg-type]
        checkpoint_hash=None,  # type: ignore[arg-type]
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
    )
    assert result.ok is False


def test_generation_result_invalid_trace_is_json_safe():
    result = GenerationResult(
        text="Use a loop.",
        role="left_hemisphere",
        checkpoint_path="checkpoints/brain_slots/left_hemisphere/winner.pt",
        checkpoint_hash="a" * 64,
        tokens_generated=float("inf"),
        elapsed_seconds=float("nan"),
        tokens_per_second=float("inf"),
        finish_reason="eos",
    )
    trace = result.to_trace()
    assert result.ok is False
    assert json.dumps(trace, allow_nan=False)


def test_generation_result_trace_sanitizes_non_string_runtime_values():
    result = GenerationResult(
        text=b"ok",  # type: ignore[arg-type]
        role=b"left_hemisphere",  # type: ignore[arg-type]
        checkpoint_path=Path("checkpoints/brain_slots/left_hemisphere/winner.pt"),  # type: ignore[arg-type]
        checkpoint_hash=None,  # type: ignore[arg-type]
        tokens_generated=4,
        elapsed_seconds=0.02,
        tokens_per_second=200.0,
        finish_reason="eos",
        error=object(),  # type: ignore[arg-type]
    )
    trace = result.to_trace()
    assert result.ok is False
    assert json.dumps(trace, allow_nan=False)
    assert isinstance(trace["text"], str)
    assert isinstance(trace["role"], str)
    assert isinstance(trace["checkpoint_path"], str)
    assert trace["checkpoint_hash"] is None
    assert isinstance(trace["error"], str)


def test_route_prediction_support_roles_become_tuple_and_resist_mutation():
    source_roles = ["left_hemisphere", "memory_transformer"]
    prediction = RoutePrediction(
        domain="coding",
        primary_role="planner_transformer",
        support_roles=source_roles,
        confidence=0.91,
        model_hash="b" * 64,
    )
    assert prediction.domain in DOMAIN_NAMES
    assert isinstance(prediction.support_roles, tuple)
    assert prediction.support_roles == ("left_hemisphere", "memory_transformer")
    source_roles.append("speech_output_transformer")
    assert prediction.support_roles == ("left_hemisphere", "memory_transformer")
    trace = asdict(prediction)
    assert json.dumps(trace, allow_nan=False)


def test_route_prediction_rejects_string_collection_and_invalid_metadata():
    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles="left_hemisphere",
            confidence=0.91,
            model_hash="b" * 64,
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="unknown",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=0.91,
            model_hash="b" * 64,
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=0.91,
            model_hash="b" * 64,
            source="invalid",
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=1.1,
            model_hash="b" * 64,
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=float("nan"),
            model_hash="b" * 64,
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=0.91,
            model_hash="not-a-hash",
        )

    with pytest.raises(ValueError):
        RoutePrediction(
            domain="coding",
            primary_role="planner_transformer",
            support_roles=("left_hemisphere",),
            confidence=0.91,
            model_hash="b" * 64,
            source="transformer",
        )


def test_route_prediction_supports_learned_and_baseline_sources():
    learned = RoutePrediction(
        domain="coding",
        primary_role="planner_transformer",
        support_roles=("left_hemisphere",),
        confidence=0.33,
        model_hash="b" * 64,
        source="learned_route_model",
    )
    baseline = RoutePrediction(
        domain="general",
        primary_role="right_hemisphere",
        support_roles=("memory_transformer",),
        confidence=0.11,
        model_hash="c" * 64,
        source="baseline_fallback",
    )
    assert learned.source == "learned_route_model"
    assert baseline.source == "baseline_fallback"
    assert json.dumps(asdict(learned), allow_nan=False)
    assert json.dumps(asdict(baseline), allow_nan=False)


def test_promotion_decision_reasons_become_tuple_and_resist_mutation():
    reasons = ["candidate beats baseline"]
    decision = PromotionDecision(
        verdict="REJECTED",
        reasons=reasons,
        baseline_joint=0.41,
        candidate_joint=0.55,
        previous_winner_joint=0.44,
    )
    assert isinstance(decision.reasons, tuple)
    assert decision.reasons == ("candidate beats baseline",)
    reasons.append("mutated")
    assert decision.reasons == ("candidate beats baseline",)
    assert json.dumps(asdict(decision), allow_nan=False)


def test_promotion_decision_rejects_string_collection_and_invalid_verdict():
    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="PROMOTED",
            reasons="candidate beats baseline",
            baseline_joint=0.41,
            candidate_joint=0.55,
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="maybe",
            reasons=("candidate beats baseline",),
            baseline_joint=0.41,
            candidate_joint=0.55,
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="PROMOTED",
            reasons=(),
            baseline_joint=0.41,
            candidate_joint=0.55,
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="PROMOTED",
            reasons=("",),
            baseline_joint=0.41,
            candidate_joint=0.55,
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="REJECTED",
            reasons=("candidate beats baseline",),
            baseline_joint=float("inf"),
            candidate_joint=0.55,
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="REJECTED",
            reasons=("candidate beats baseline",),
            baseline_joint=0.41,
            candidate_joint=float("nan"),
            previous_winner_joint=0.44,
        )

    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="REJECTED",
            reasons=("candidate beats baseline",),
            baseline_joint=0.41,
            candidate_joint=0.55,
            previous_winner_joint=float("inf"),
        )


def test_promotion_decision_supports_uppercase_verdict_contract():
    promoted = PromotionDecision(
        verdict="PROMOTED",
        reasons=("candidate beats baseline",),
        baseline_joint=0.41,
        candidate_joint=0.55,
        previous_winner_joint=None,
    )
    rejected = PromotionDecision(
        verdict="REJECTED",
        reasons=("candidate fell short",),
        baseline_joint=0.55,
        candidate_joint=0.41,
        previous_winner_joint=0.49,
    )
    blocked = PromotionDecision(
        verdict="BLOCKED",
        reasons=("need more evidence",),
        baseline_joint=0.55,
        candidate_joint=0.48,
        previous_winner_joint=0.49,
    )
    assert promoted.verdict == "PROMOTED"
    assert rejected.verdict == "REJECTED"
    assert blocked.verdict == "BLOCKED"
    assert json.dumps(asdict(promoted), allow_nan=False)
    assert json.dumps(asdict(rejected), allow_nan=False)
    assert json.dumps(asdict(blocked), allow_nan=False)
