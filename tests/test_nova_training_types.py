from pathlib import Path
import json
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


def test_promotion_decision_reasons_become_tuple_and_resist_mutation():
    reasons = ["candidate beats baseline"]
    decision = PromotionDecision(
        verdict="promote",
        reasons=reasons,
        baseline_joint=0.41,
        candidate_joint=0.55,
        previous_winner_joint=0.44,
    )
    assert isinstance(decision.reasons, tuple)
    assert decision.reasons == ("candidate beats baseline",)
    reasons.append("mutated")
    assert decision.reasons == ("candidate beats baseline",)


def test_promotion_decision_rejects_string_collection_and_invalid_verdict():
    with pytest.raises(ValueError):
        PromotionDecision(
            verdict="promote",
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
