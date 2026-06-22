from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_types import GenerationResult, ROLE_NAMES


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
    assert len(ROLE_NAMES) == 7
    assert result.ok is True
    assert result.to_trace()["source"] == "transformer"
    assert result.to_trace()["checkpoint_hash"] == "a" * 64


def test_generation_result_with_error_is_not_ok():
    result = GenerationResult.failed("planner_transformer", "checkpoint missing")
    assert result.ok is False
    assert result.error == "checkpoint missing"
