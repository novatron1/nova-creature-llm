from pathlib import Path
import json
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry, sha256
import v059_checkpoint_resolver as resolver


def write_checkpoint(path: Path, contents: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return sha256(path)


def test_registry_prefers_promoted_winner(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    candidate_hash = write_checkpoint(candidate, b"candidate")
    registry.register_baseline("left_hemisphere", baseline, baseline_hash)
    registry.register_candidate("left_hemisphere", candidate, candidate_hash, {"joint": 88.0})
    assert registry.resolve_live("left_hemisphere").path == baseline
    registry.promote("left_hemisphere", candidate_hash)
    assert registry.resolve_live("left_hemisphere").path == candidate


def test_rejected_candidate_never_becomes_live(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    candidate_hash = write_checkpoint(candidate, b"candidate")
    registry.register_baseline("planner_transformer", baseline, baseline_hash)
    registry.register_candidate("planner_transformer", candidate, candidate_hash, {"joint": 70.0})
    registry.reject("planner_transformer", candidate_hash, ["route regression"])
    assert registry.resolve_live("planner_transformer").path == baseline


def test_reregistering_baseline_does_not_demote_promoted_candidate(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    candidate_hash = write_checkpoint(candidate, b"candidate")
    registry.register_baseline("left_hemisphere", baseline, baseline_hash)
    registry.register_candidate("left_hemisphere", candidate, candidate_hash, {"joint": 88.0})
    registry.promote("left_hemisphere", candidate_hash)

    registry.register_baseline("left_hemisphere", baseline, baseline_hash)

    assert registry.resolve_live("left_hemisphere").path == candidate
    assert registry.resolve_live("left_hemisphere").status == "promoted"


def test_updating_baseline_updates_live_when_baseline_is_live(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    first_baseline = tmp_path / "first_baseline.pt"
    second_baseline = tmp_path / "second_baseline.pt"
    first_hash = write_checkpoint(first_baseline, b"first baseline")
    second_hash = write_checkpoint(second_baseline, b"second baseline")
    registry.register_baseline("right_hemisphere", first_baseline, first_hash)

    registry.register_baseline("right_hemisphere", second_baseline, second_hash)

    resolved = registry.resolve_live("right_hemisphere")
    assert resolved.path == second_baseline
    assert resolved.sha256 == second_hash


def test_registration_rejects_invalid_or_mismatched_sha256(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    write_checkpoint(candidate, b"candidate")

    with pytest.raises(ValueError, match="64-character hexadecimal"):
        registry.register_baseline("memory_transformer", baseline, "not-a-real-hash")

    with pytest.raises(ValueError, match="does not match"):
        registry.register_baseline("memory_transformer", baseline, "0" * 64)

    registry.register_baseline("memory_transformer", baseline, baseline_hash)
    with pytest.raises(ValueError, match="does not match"):
        registry.register_candidate("memory_transformer", candidate, "1" * 64, {"joint": 1.0})


def test_registering_missing_checkpoint_fails_clearly(tmp_path):
    registry = CheckpointRegistry(tmp_path)

    with pytest.raises(FileNotFoundError, match="checkpoint path does not exist"):
        registry.register_baseline("critic_conscience_transformer", tmp_path / "missing.pt", "0" * 64)


def test_resolve_live_detects_missing_or_tampered_checkpoint(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    missing_after_register = tmp_path / "missing_after_register.pt"
    missing_hash = write_checkpoint(missing_after_register, b"baseline")
    registry.register_baseline("dream_simulation_transformer", missing_after_register, missing_hash)
    missing_after_register.unlink()
    with pytest.raises(FileNotFoundError, match="registered checkpoint is missing"):
        registry.resolve_live("dream_simulation_transformer")

    registry = CheckpointRegistry(tmp_path / "tamper_project")
    tampered = tmp_path / "tamper_project" / "tampered.pt"
    tampered_hash = write_checkpoint(tampered, b"baseline")
    registry.register_baseline("dream_simulation_transformer", tampered, tampered_hash)
    tampered.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        registry.resolve_live("dream_simulation_transformer")


def test_promote_records_rollback_and_rejecting_promoted_candidate_falls_back(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    candidate_hash = write_checkpoint(candidate, b"candidate")
    registry.register_baseline("speech_output_transformer", baseline, baseline_hash)
    registry.register_candidate("speech_output_transformer", candidate, candidate_hash, {"joint": 92.0})

    registry.promote("speech_output_transformer", candidate_hash)

    snapshot = registry.snapshot()
    candidate_snapshot = snapshot["roles"]["speech_output_transformer"]["candidates"][candidate_hash]
    assert candidate_snapshot["rollback_sha256"] == baseline_hash

    registry.reject("speech_output_transformer", candidate_hash, ["late regression"])
    resolved = registry.resolve_live("speech_output_transformer")
    assert resolved.path == baseline
    assert resolved.status == "baseline"


def test_snapshot_is_deep_copy_and_json_safe(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "baseline.pt"
    candidate = tmp_path / "candidate.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    candidate_hash = write_checkpoint(candidate, b"candidate")
    registry.register_baseline("planner_transformer", baseline, baseline_hash)
    registry.register_candidate("planner_transformer", candidate, candidate_hash, {"joint": 70.0})

    snapshot = registry.snapshot()
    json.dumps(snapshot)
    snapshot["roles"]["planner_transformer"]["candidates"][candidate_hash]["metrics"]["joint"] = 1.0

    assert registry.snapshot()["roles"]["planner_transformer"]["candidates"][candidate_hash]["metrics"]["joint"] == 70.0


def test_registry_serializes_project_relative_paths_with_forward_slashes(tmp_path):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "baseline.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")

    registry.register_baseline("left_hemisphere", baseline, baseline_hash)

    stored_path = registry.snapshot()["roles"]["left_hemisphere"]["baseline"]["path"]
    assert stored_path == "checkpoints/brain_slots/left_hemisphere/baseline.pt"


def test_resolver_returns_registry_controlled_checkpoint_fields(tmp_path, monkeypatch):
    registry = CheckpointRegistry(tmp_path)
    baseline = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "baseline.pt"
    baseline_hash = write_checkpoint(baseline, b"baseline")
    registry.register_baseline("left_hemisphere", baseline, baseline_hash)
    monkeypatch.setattr(resolver, "root", lambda: tmp_path)

    resolved = resolver.resolve_checkpoint("left_hemisphere")

    assert resolved == {
        "role": "left_hemisphere",
        "selected_checkpoint": "checkpoints/brain_slots/left_hemisphere/baseline.pt",
        "checkpoint_version": "baseline",
        "exists": True,
        "size_bytes": len(b"baseline"),
        "sha256": baseline_hash,
        "fallback_used": True,
        "promote_ready": False,
    }
