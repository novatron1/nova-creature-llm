from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_checkpoint_registry import CheckpointRegistry
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint
from nova_transformer_runtime import NovaTransformerRuntime


class FixedRouteModel:
    model_hash = "routehash"

    def predict(self, text):
        from nova_training_types import RoutePrediction
        return RoutePrediction("coding", "left_hemisphere", ("planner_transformer",), 0.91, self.model_hash)


def test_runtime_returns_generation_evidence(tmp_path):
    path = tmp_path / "checkpoints" / "brain_slots" / "left_hemisphere" / "left_hemisphere_baseline.pt"
    digest = save_checkpoint(
        path,
        NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "left_hemisphere"},
    )
    CheckpointRegistry(tmp_path).register_baseline("left_hemisphere", path, digest)
    runtime = NovaTransformerRuntime(tmp_path, route_model=FixedRouteModel())
    route = runtime.route("debug this code")
    result = runtime.generate(route.primary_role, "debug this code", max_new_tokens=4)
    assert route.source == "learned_route_model"
    assert result.role == "left_hemisphere"
    assert result.checkpoint_hash == digest
    assert result.to_trace()["source"] == "transformer"
