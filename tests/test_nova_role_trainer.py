from pathlib import Path
import sys

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer
from nova_role_trainer import build_supervised_sequence, train_role_candidate
from nova_torch_transformer import ModelConfig, NovaCausalLM, save_checkpoint


def test_prompt_tokens_are_masked_from_answer_loss():
    tokenizer = NovaByteTokenizer()
    answer = "Answer."
    token_ids, targets = build_supervised_sequence(tokenizer, "Question?", answer, block_size=64)
    sep_index = token_ids.index(tokenizer.SEP)
    answer_ids = tokenizer.encode(answer, add_special=False)
    assert all(value == -100 for value in targets[:sep_index])
    assert targets[sep_index] == answer_ids[0]
    assert targets[sep_index : sep_index + len(answer_ids)] == answer_ids


def test_sequence_truncation_keeps_literal_prefix_without_rebalancing():
    tokenizer = NovaByteTokenizer()
    prompt = "ab"
    answer = "WXYZ"
    token_ids, targets = build_supervised_sequence(tokenizer, prompt, answer, block_size=5)
    expected_prefix = [
        tokenizer.BOS,
        *tokenizer.encode(prompt, add_special=False),
        tokenizer.SEP,
        tokenizer.encode(answer, add_special=False)[0],
    ]
    assert token_ids == expected_prefix
    sep_index = token_ids.index(tokenizer.SEP)
    assert targets[sep_index] == tokenizer.encode(answer, add_special=False)[0]


def test_truncation_that_removes_sep_fails_clearly():
    tokenizer = NovaByteTokenizer()
    with pytest.raises(ValueError, match="SEP"):
        build_supervised_sequence(tokenizer, "abcdef", "Z", block_size=5)


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
