from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry


def test_registry_prefers_promoted_winner(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline.write_bytes(b"baseline")
    candidate.write_bytes(b"candidate")
    registry.register_baseline("left_hemisphere", baseline, "basehash")
    registry.register_candidate("left_hemisphere", candidate, "candidatehash", {"joint": 88.0})
    assert registry.resolve_live("left_hemisphere").path == baseline
    registry.promote("left_hemisphere", "candidatehash")
    assert registry.resolve_live("left_hemisphere").path == candidate


def test_rejected_candidate_never_becomes_live(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline.write_bytes(b"baseline")
    candidate.write_bytes(b"candidate")
    registry.register_baseline("planner_transformer", baseline, "basehash")
    registry.register_candidate("planner_transformer", candidate, "candidatehash", {"joint": 70.0})
    registry.reject("planner_transformer", "candidatehash", ["route regression"])
    assert registry.resolve_live("planner_transformer").path == baseline
