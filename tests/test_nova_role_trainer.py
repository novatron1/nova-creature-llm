from pathlib import Path
import sys

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer
from nova_role_trainer import build_supervised_sequence, train_role_candidate
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint


def test_prompt_tokens_are_masked_from_answer_loss():
    tokenizer = NovaByteTokenizer()
    token_ids, targets = build_supervised_sequence(tokenizer, "Question?", "Answer.", block_size=64)
    sep_index = token_ids.index(tokenizer.SEP)
    assert all(value == -100 for value in targets[: sep_index + 1])
    assert any(value != -100 for value in targets[sep_index + 1 :])


def test_role_training_reduces_validation_loss(tmp_path):
    torch.manual_seed(5)
    baseline = tmp_path / "baseline.pt"
    save_checkpoint(
        baseline,
        NovaCausalLM(ModelConfig(block_size=64, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "memory_transformer"},
    )
    rows = [
        {"prompt": "Who created Nova?", "answer": "Mr. Novotron."},
        {"prompt": "What is Nova's name?", "answer": "Nova Creature."},
    ] * 12
    result = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=rows[:18],
        validation_rows=rows[18:],
        output_path=tmp_path / "candidate.pt",
        seed=5,
        epochs=30,
    )
    assert result["best_validation_loss"] < result["baseline_validation_loss"]
    assert Path(result["checkpoint_path"]).exists()
