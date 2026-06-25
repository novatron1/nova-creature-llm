from pathlib import Path
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_preflight import run_preflight


def _valid_checkpoint(tmp_path: Path, role: str = "left_hemisphere") -> tuple[Path, str]:
    from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint

    path = tmp_path / "checkpoints" / "brain_slots" / role / f"{role}_baseline.pt"
    model = NovaCausalLM(ModelConfig(d_model=32, n_heads=4, n_layers=1, block_size=32))
    digest = save_checkpoint(path, model, {"role": role})
    return path, digest


def _register_baseline(tmp_path: Path, role: str = "left_hemisphere") -> tuple[Path, str]:
    from nova_checkpoint_registry import CheckpointRegistry

    path, digest = _valid_checkpoint(tmp_path, role)
    CheckpointRegistry(tmp_path).register_baseline(role, path, digest)
    return path, digest


def test_project_root_import_exposes_preflight_api():
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import nova_training_preflight as preflight; "
                "assert callable(preflight.run_preflight); "
                "assert callable(preflight.main); "
                "print(preflight.run_preflight.__name__, preflight.main.__name__)"
            ),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "run_preflight main" in completed.stdout


def test_preflight_rejects_placeholder_checkpoint(tmp_path):
    role_dir = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere"
    role_dir.mkdir(parents=True)
    (role_dir / "left_hemisphere_baseline.pt").write_text("PLACEHOLDER", encoding="utf-8")
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "BLOCKED"
    assert any("placeholder" in reason.lower() or "invalid" in reason.lower() for reason in result["reasons"])


def test_preflight_accepts_valid_registry_checkpoint(tmp_path):
    _register_baseline(tmp_path)
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "READY"
    assert result["roles_ready"] == 1


def test_preflight_output_is_strict_json_when_registry_metrics_are_non_finite(tmp_path):
    from nova_checkpoint_registry import CheckpointRegistry

    registry = CheckpointRegistry(tmp_path)
    baseline, baseline_digest = _valid_checkpoint(tmp_path)
    registry.register_baseline("left_hemisphere", baseline, baseline_digest)
    registry_payload = json.loads((tmp_path / "checkpoints" / "registry.json").read_text(encoding="utf-8"))
    registry_payload["roles"]["left_hemisphere"]["baseline"]["metrics"] = {
        "joint": float("nan"),
        "loss": float("inf"),
        "nested": {"score": float("-inf")},
    }
    (tmp_path / "checkpoints" / "registry.json").write_text(
        json.dumps(registry_payload),
        encoding="utf-8",
    )

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "READY"
    json.dumps(result, allow_nan=False)


def test_preflight_reports_hash_mismatch_with_registry_evidence(tmp_path):
    path, expected_digest = _register_baseline(tmp_path)
    path.write_bytes(b"tampered checkpoint bytes")

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    evidence = result["roles"]["left_hemisphere"]
    assert evidence["path"] == "checkpoints/brain_slots/left_hemisphere/left_hemisphere_baseline.pt"
    assert evidence["sha256"] == expected_digest
    assert evidence.get("actual_sha256")
    assert evidence["actual_sha256"] != expected_digest


def test_preflight_blocks_missing_registry_baseline(tmp_path):
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    assert result["roles_ready"] == 0
    assert any("no checkpoints registered" in reason.lower() for reason in result["reasons"])


def test_preflight_blocks_malformed_registry_json(tmp_path):
    registry_path = tmp_path / "checkpoints" / "registry.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text("{not valid json", encoding="utf-8")

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    assert result["roles_ready"] == 0
    assert any(
        any(word in reason.lower() for word in ("registry", "json", "corrupt", "invalid"))
        for reason in result["reasons"]
    )
    json.dumps(result, allow_nan=False)


def test_preflight_blocks_wrong_vocab_checkpoint(tmp_path):
    from nova_checkpoint_registry import CheckpointRegistry
    from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint

    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    model = NovaCausalLM(ModelConfig(vocab_size=261, d_model=32, n_heads=4, n_layers=1, block_size=32))
    digest = save_checkpoint(path, model, {"role": "left_hemisphere"})
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    assert any("vocab" in reason.lower() for reason in result["reasons"])


def test_preflight_blocks_corrupt_registered_checkpoint(tmp_path):
    from nova_checkpoint_registry import CheckpointRegistry, sha256

    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    path.parent.mkdir(parents=True)
    path.write_text("not a torch checkpoint", encoding="utf-8")
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, sha256(path))

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    assert any("invalid" in reason.lower() for reason in result["reasons"])


def test_preflight_blocks_non_finite_registered_checkpoint_parameters(tmp_path):
    import torch
    from nova_checkpoint_registry import CheckpointRegistry, sha256
    from nova_torch_transformer import ModelConfig, NovaCausalLM

    model = NovaCausalLM(ModelConfig(d_model=32, n_heads=4, n_layers=1, block_size=32))
    payload = {
        "format_version": 1,
        "config": model.config.__dict__,
        "model_state": model.state_dict(),
        "metadata": {"role": "left_hemisphere"},
    }
    payload["model_state"]["lm_head.weight"][0, 0] = float("nan")
    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    path.parent.mkdir(parents=True)
    torch.save(payload, path)
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, sha256(path))

    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))

    assert result["verdict"] == "BLOCKED"
    assert any("non-finite" in reason.lower() for reason in result["reasons"])


def test_module_cli_blocks_missing_registry_project_root(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "nova_training_preflight", "--project-root", str(tmp_path)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["verdict"] == "BLOCKED"
    assert payload["roles_ready"] == 0
