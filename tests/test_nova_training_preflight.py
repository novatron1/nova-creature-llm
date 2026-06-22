from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_training_preflight import run_preflight


def test_preflight_rejects_placeholder_checkpoint(tmp_path):
    role_dir = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere"
    role_dir.mkdir(parents=True)
    (role_dir / "left_hemisphere_baseline.pt").write_text("PLACEHOLDER", encoding="utf-8")
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "BLOCKED"
    assert any("placeholder" in reason.lower() or "invalid" in reason.lower() for reason in result["reasons"])


def test_preflight_accepts_valid_registry_checkpoint(tmp_path):
    from nova_checkpoint_registry import CheckpointRegistry
    from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint

    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    model = NovaCausalLM(ModelConfig(d_model=32, n_heads=4, n_layers=1, block_size=32))
    digest = save_checkpoint(path, model, {"role": "left_hemisphere"})
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)
    result = run_preflight(tmp_path, required_roles=("left_hemisphere",))
    assert result["verdict"] == "READY"
    assert result["roles_ready"] == 1
