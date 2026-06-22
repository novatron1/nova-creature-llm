from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_torch_transformer import (
    ModelConfig,
    NovaCausalLM,
    load_checkpoint,
    save_checkpoint,
)


def test_model_computes_answer_masked_loss():
    torch.manual_seed(7)
    config = ModelConfig(
        vocab_size=260,
        block_size=32,
        d_model=32,
        n_heads=4,
        n_layers=1,
        dropout=0.0,
    )
    model = NovaCausalLM(config)
    tokens = torch.tensor([[1, 10, 11, 3, 12, 13, 2]], dtype=torch.long)
    targets = tokens.clone()
    targets[:, :4] = -100

    logits, loss = model(tokens, targets)

    assert logits.shape == (1, 7, 260)
    assert torch.isfinite(loss)


def test_checkpoint_round_trip_preserves_logits(tmp_path):
    torch.manual_seed(11)
    config = ModelConfig(
        vocab_size=260,
        block_size=32,
        d_model=32,
        n_heads=4,
        n_layers=1,
        dropout=0.0,
    )
    model = NovaCausalLM(config).eval()
    tokens = torch.tensor([[1, 40, 41, 2]], dtype=torch.long)
    expected, _ = model(tokens)
    path = tmp_path / "model.pt"

    save_checkpoint(path, model, metadata={"role": "left_hemisphere"})
    loaded, payload = load_checkpoint(path)
    actual, _ = loaded.eval()(tokens)

    assert payload["metadata"]["role"] == "left_hemisphere"
    assert torch.equal(expected, actual)
