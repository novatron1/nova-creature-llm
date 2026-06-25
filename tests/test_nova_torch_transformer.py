from pathlib import Path
import hashlib
import sys

import pytest
import torch
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_torch_transformer import (
    ModelConfig,
    NovaCausalLM,
    load_checkpoint,
    save_checkpoint,
)


def _small_config() -> ModelConfig:
    return ModelConfig(
        vocab_size=260,
        block_size=32,
        d_model=32,
        n_heads=4,
        n_layers=1,
        dropout=0.0,
    )


def test_model_computes_answer_masked_loss():
    torch.manual_seed(7)
    config = _small_config()
    model = NovaCausalLM(config)
    tokens = torch.tensor([[1, 10, 11, 3, 12, 13, 2]], dtype=torch.long)
    targets = tokens.clone()
    targets[:, :4] = -100

    logits, loss = model(tokens, targets)
    expected_loss = F.cross_entropy(
        logits.reshape(-1, logits.size(-1)),
        targets.reshape(-1),
        ignore_index=-100,
    )

    assert logits.shape == (1, 7, 260)
    assert torch.isfinite(loss)
    torch.testing.assert_close(loss, expected_loss)


def test_model_rejects_sequences_beyond_block_size():
    model = NovaCausalLM(ModelConfig(block_size=3, dropout=0.0))
    tokens = torch.tensor([[1, 10, 11, 2]], dtype=torch.long)

    with pytest.raises(ValueError, match="block_size"):
        model(tokens)


def test_causal_mask_keeps_prefix_logits_unchanged_when_future_tokens_change():
    torch.manual_seed(13)
    model = NovaCausalLM(_small_config()).eval()
    tokens_a = torch.tensor([[1, 10, 11, 12, 2]], dtype=torch.long)
    tokens_b = torch.tensor([[1, 10, 11, 77, 88]], dtype=torch.long)

    logits_a, _ = model(tokens_a)
    logits_b, _ = model(tokens_b)

    torch.testing.assert_close(logits_a[:, :3, :], logits_b[:, :3, :], rtol=0.0, atol=0.0)


def test_checkpoint_round_trip_preserves_logits(tmp_path):
    torch.manual_seed(11)
    config = _small_config()
    model = NovaCausalLM(config).eval()
    tokens = torch.tensor([[1, 40, 41, 2]], dtype=torch.long)
    expected, _ = model(tokens)
    path = tmp_path / "model.pt"

    digest = save_checkpoint(path, model, metadata={"role": "left_hemisphere"})
    loaded, payload = load_checkpoint(path)
    actual, _ = loaded.eval()(tokens)

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert payload["metadata"]["role"] == "left_hemisphere"
    assert torch.equal(expected, actual)


def test_load_checkpoint_uses_weights_only_deserialization(monkeypatch, tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    payload = {
        "format_version": 1,
        "config": model.config.__dict__,
        "model_state": model.state_dict(),
        "metadata": {},
    }
    seen = {}

    def fake_load(path, *, map_location, weights_only):
        seen["path"] = path
        seen["map_location"] = map_location
        seen["weights_only"] = weights_only
        return payload

    monkeypatch.setattr(torch, "load", fake_load)

    load_checkpoint(tmp_path / "model.pt")

    assert seen["map_location"] == "cpu"
    assert seen["weights_only"] is True


def test_save_checkpoint_uses_unique_temp_path_without_colliding_with_simple_tmp(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    path = tmp_path / "model.pt"
    simple_tmp = tmp_path / "model.tmp"
    simple_tmp.write_text("keep me", encoding="utf-8")

    digest = save_checkpoint(path, model, metadata={})

    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert simple_tmp.read_text(encoding="utf-8") == "keep me"
    assert not list(tmp_path.glob("model.pt.*.tmp"))


def test_load_checkpoint_rejects_unsupported_format_version(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    payload = {
        "format_version": 2,
        "config": model.config.__dict__,
        "model_state": model.state_dict(),
        "metadata": {},
    }
    path = tmp_path / "unsupported.pt"
    torch.save(payload, path)

    with pytest.raises(ValueError, match="format_version"):
        load_checkpoint(path)


def test_load_checkpoint_rejects_malformed_payload_shapes(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    valid_payload = {
        "format_version": 1,
        "config": model.config.__dict__,
        "model_state": model.state_dict(),
        "metadata": {},
    }
    cases = [
        ("not a payload", "payload"),
        ({k: v for k, v in valid_payload.items() if k != "config"}, "config"),
        ({k: v for k, v in valid_payload.items() if k != "model_state"}, "model_state"),
        ({k: v for k, v in valid_payload.items() if k != "metadata"}, "metadata"),
        ({**valid_payload, "config": []}, "config"),
        ({**valid_payload, "model_state": []}, "model_state"),
    ]

    for index, (payload, expected_message) in enumerate(cases):
        path = tmp_path / f"malformed-{index}.pt"
        torch.save(payload, path)
        with pytest.raises(ValueError, match=expected_message):
            load_checkpoint(path)


def test_load_checkpoint_normalizes_non_mapping_metadata(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    path = tmp_path / "metadata.pt"
    torch.save(
        {
            "format_version": 1,
            "config": model.config.__dict__,
            "model_state": model.state_dict(),
            "metadata": ["not", "a", "mapping"],
        },
        path,
    )

    _, payload = load_checkpoint(path)

    assert payload["metadata"] == {}


def test_save_checkpoint_rejects_non_finite_parameters(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    with torch.no_grad():
        model.lm_head.weight[0, 0] = float("nan")

    with pytest.raises(ValueError, match="non-finite parameter"):
        save_checkpoint(tmp_path / "bad.pt", model, metadata={})


def test_load_checkpoint_rejects_non_finite_parameters(tmp_path):
    model = NovaCausalLM(_small_config()).eval()
    payload = {
        "format_version": 1,
        "config": model.config.__dict__,
        "model_state": model.state_dict(),
        "metadata": {},
    }
    payload["model_state"]["lm_head.weight"][0, 0] = float("inf")
    path = tmp_path / "bad-load.pt"
    torch.save(payload, path)

    with pytest.raises(ValueError, match="non-finite parameter"):
        load_checkpoint(path)
