from pathlib import Path
import sys
import hashlib

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_byte_tokenizer import NovaByteTokenizer
from nova_role_trainer import build_supervised_sequence, train_role_candidate
from nova_torch_transformer import ModelConfig, NovaCausalLM, load_checkpoint, save_checkpoint


def _save_baseline(path: Path, *, block_size: int = 64, seed: int = 5) -> str:
    torch.manual_seed(seed)
    return save_checkpoint(
        path,
        NovaCausalLM(ModelConfig(block_size=block_size, d_model=32, n_heads=4, n_layers=1, dropout=0.0)),
        {"role": "memory_transformer"},
    )


def _answer_rows() -> list[dict[str, str]]:
    return [
        {"prompt": "Who created Nova?", "answer": "Mr. Novotron."},
        {"prompt": "What is Nova's name?", "answer": "Nova Creature."},
    ]


def test_prompt_tokens_are_masked_from_answer_loss():
    tokenizer = NovaByteTokenizer()
    answer = "Answer."
    token_ids, targets = build_supervised_sequence(tokenizer, "Question?", answer, block_size=64)
    sep_index = token_ids.index(tokenizer.SEP)
    answer_ids = tokenizer.encode(answer, add_special=False)
    assert all(value == -100 for value in targets[:sep_index])
    assert targets[sep_index] == answer_ids[0]
    assert targets[sep_index : sep_index + len(answer_ids)] == answer_ids


def test_final_position_target_is_ignored_when_sequence_ends_in_eos():
    tokenizer = NovaByteTokenizer()
    token_ids, targets = build_supervised_sequence(tokenizer, "Q?", "A.", block_size=64)
    assert token_ids[-1] == tokenizer.EOS
    assert targets[-1] == -100


def test_truncated_mid_answer_predicts_next_real_token_not_forced_eos():
    tokenizer = NovaByteTokenizer()
    token_ids, targets = build_supervised_sequence(tokenizer, "q", "abc", block_size=5)
    answer_ids = tokenizer.encode("abc", add_special=False)
    assert token_ids == [
        tokenizer.BOS,
        *tokenizer.encode("q", add_special=False),
        tokenizer.SEP,
        answer_ids[0],
        answer_ids[1],
    ]
    assert targets[-1] == answer_ids[2]
    assert targets[-1] != tokenizer.EOS


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


def test_sequence_build_failures_include_split_and_row_context(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline, block_size=5)
    rows = [
        {"prompt": "a", "answer": "b"},
        {"prompt": "c", "answer": "d"},
        {"prompt": "e", "answer": "f"},
        {"prompt": "abcdef", "answer": "Z"},
    ]
    with pytest.raises(ValueError, match="train row 3"):
        train_role_candidate(
            role="memory_transformer",
            baseline_path=baseline,
            train_rows=rows,
            validation_rows=[{"prompt": "a", "answer": "b"}],
            output_path=tmp_path / "candidate.pt",
            seed=5,
            epochs=1,
        )


def test_all_route_split_reports_no_answer_examples(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    with pytest.raises(ValueError, match="train rows produced no answer examples"):
        train_role_candidate(
            role="memory_transformer",
            baseline_path=baseline,
            train_rows=[{"task_type": "route", "prompt": "route me", "answer": "Route."}],
            validation_rows=_answer_rows(),
            output_path=tmp_path / "candidate.pt",
            seed=5,
            epochs=1,
        )


def test_invalid_role_and_missing_answer_row_are_rejected(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    with pytest.raises(ValueError, match="invalid role"):
        train_role_candidate(
            role="not_a_role",
            baseline_path=baseline,
            train_rows=_answer_rows(),
            validation_rows=_answer_rows(),
            output_path=tmp_path / "candidate.pt",
            seed=5,
            epochs=1,
        )
    with pytest.raises(ValueError, match="train row 0.*missing answer"):
        train_role_candidate(
            role="memory_transformer",
            baseline_path=baseline,
            train_rows=[{"prompt": "missing answer"}],
            validation_rows=_answer_rows(),
            output_path=tmp_path / "candidate.pt",
            seed=5,
            epochs=1,
        )


def test_candidate_path_rejects_baseline_overwrite(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    with pytest.raises(ValueError, match="baseline path"):
        train_role_candidate(
            role="memory_transformer",
            baseline_path=baseline,
            train_rows=_answer_rows(),
            validation_rows=_answer_rows(),
            output_path=baseline,
            seed=5,
            epochs=1,
        )


def test_candidate_path_rejects_exact_protected_paths(tmp_path):
    baseline = tmp_path / "baseline.pt"
    protected = tmp_path / "live.pt"
    _save_baseline(baseline)
    with pytest.raises(ValueError, match="protected path"):
        train_role_candidate(
            role="memory_transformer",
            baseline_path=baseline,
            train_rows=_answer_rows(),
            validation_rows=_answer_rows(),
            output_path=protected,
            protected_paths=[protected],
            seed=5,
            epochs=1,
        )


def test_candidate_path_allows_innocent_baseline_word_when_not_protected(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    result = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=_answer_rows(),
        validation_rows=_answer_rows(),
        output_path=tmp_path / "not_a_baseline_candidate.pt",
        seed=5,
        epochs=1,
    )
    assert Path(result["checkpoint_path"]).exists()


def test_candidate_metadata_round_trips_hashes_and_baseline_comparison(tmp_path):
    baseline = tmp_path / "baseline.pt"
    baseline_sha256 = _save_baseline(baseline)
    result = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=_answer_rows(),
        validation_rows=_answer_rows(),
        output_path=tmp_path / "candidate.pt",
        seed=5,
        epochs=1,
    )
    assert result["baseline_sha256"] == baseline_sha256
    assert result["candidate_sha256"] == hashlib.sha256(Path(result["checkpoint_path"]).read_bytes()).hexdigest()
    assert result["checkpoint_validation_loss"] == result["best_validation_loss"]
    assert result["improves_over_baseline"] == (
        result["checkpoint_validation_loss"] < result["baseline_validation_loss"]
    )
    _, payload = load_checkpoint(result["checkpoint_path"])
    metadata = payload["metadata"]
    assert metadata["baseline_sha256"] == baseline_sha256
    assert metadata["checkpoint_validation_loss"] == result["checkpoint_validation_loss"]
    assert metadata["improves_over_baseline"] == result["improves_over_baseline"]


def test_same_seed_produces_same_training_metrics(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    first = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=_answer_rows() * 2,
        validation_rows=_answer_rows(),
        output_path=tmp_path / "candidate_one.pt",
        seed=7,
        epochs=2,
        batch_size=2,
    )
    second = train_role_candidate(
        role="memory_transformer",
        baseline_path=baseline,
        train_rows=_answer_rows() * 2,
        validation_rows=_answer_rows(),
        output_path=tmp_path / "candidate_two.pt",
        seed=7,
        epochs=2,
        batch_size=2,
    )
    assert second["train_loss_history"] == pytest.approx(first["train_loss_history"])
    assert second["validation_loss_history"] == pytest.approx(first["validation_loss_history"])
    assert second["checkpoint_validation_loss"] == pytest.approx(first["checkpoint_validation_loss"])


def test_role_training_reduces_validation_loss(tmp_path):
    baseline = tmp_path / "baseline.pt"
    _save_baseline(baseline)
    rows = _answer_rows() * 12
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
