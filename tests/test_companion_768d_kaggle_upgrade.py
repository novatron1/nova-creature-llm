import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.prepare_companion_768d_kaggle_upgrade import (
    DEFAULT_RUNNER,
    build_run_manifest,
    prepare_bundle,
    validate_base_checkpoint,
)
from tools.companion_768d_token_utils import (
    build_loss_mask,
    end_of_text_token_id,
    truncate_at_end_of_text,
    tokenize_documents_with_boundaries,
    unknown_token_id,
)


def test_missing_base_checkpoint_is_rejected(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        validate_base_checkpoint(tmp_path / "missing.pt")


def test_manifest_requires_a_separate_upgrade_run_directory(tmp_path: Path):
    base = tmp_path / "base"
    base.mkdir()
    checkpoint = base / "final.pt"
    checkpoint.write_bytes(b"checkpoint")

    with pytest.raises(ValueError, match="separate"):
        build_run_manifest(
            base_checkpoint=checkpoint,
            concept_root=tmp_path / "concepts",
            run_dir=base,
            max_steps=100,
            concept_ratio=0.75,
            learning_rate=5e-5,
        )


def test_prepare_bundle_copies_concept_artifact_and_runner(tmp_path: Path):
    concept_root = tmp_path / "concepts"
    concept_root.mkdir()
    (concept_root / "train.jsonl").write_text('{"text":"gravity"}\n', encoding="utf-8")
    (concept_root / "validation.jsonl").write_text('{"text":"mass"}\n', encoding="utf-8")
    runner = tmp_path / "runner.py"
    runner.write_text("NOVA_BASE_CHECKPOINT\nNOVA_CONCEPT_ROOT\n", encoding="utf-8")
    checkpoint = tmp_path / "base.pt"
    checkpoint.write_bytes(b"checkpoint")
    output = tmp_path / "bundle"

    manifest = prepare_bundle(
        runner_source=runner,
        concept_root=concept_root,
        base_checkpoint=checkpoint,
        output_dir=output,
        run_dir=tmp_path / "upgrade-run",
        max_steps=100,
        concept_ratio=0.75,
        learning_rate=5e-5,
    )

    assert (output / "nova-companion-768d-concept-upgrade.py").exists()
    assert (output / "companion_768d_token_utils.py").exists()
    assert (output / "concept_upgrade" / "train.jsonl").exists()
    assert json.loads((output / "run_manifest.json").read_text()) == manifest
    assert manifest["base_checkpoint"] == str(checkpoint.resolve())
    assert manifest["run_dir"] != str(tmp_path.resolve())


class FakeCuratedTokenizer:
    UNK = "<unk>"
    EOT = "<|endoftext|>"
    tokens = ["<unk>", "<|endoftext|>", "gravity", "mass"]

    def encode(self, text: str) -> list[int]:
        return {"gravity": [2], "mass": [3]}[text]


class WordTokenizer(FakeCuratedTokenizer):
    tokens = ["<unk>", "<|endoftext|>", "Question:", "What", "is", "density?", "Answer:", "Density", "mass", "per", "volume."]

    def encode(self, text: str) -> list[int]:
        return [self.tokens.index(word) for word in text.split()]


def test_curated_tokenizer_special_ids_are_detected_from_real_schema():
    tokenizer = FakeCuratedTokenizer()

    assert unknown_token_id(tokenizer) == 0
    assert end_of_text_token_id(tokenizer) == 1


def test_documents_are_separated_by_end_of_text_token():
    tokenizer = FakeCuratedTokenizer()

    assert tokenize_documents_with_boundaries(["gravity", "mass"], tokenizer) == [2, 1, 3, 1]


def test_generated_text_stops_at_the_first_end_of_text_marker():
    tokenizer = FakeCuratedTokenizer()

    assert truncate_at_end_of_text("answer<|endoftext|>next record", tokenizer) == "answer"


def test_answer_loss_mask_ignores_question_tokens():
    tokenizer = WordTokenizer()
    text = "Question: What is density? Answer: Density mass per volume."

    assert build_loss_mask(text, tokenizer) == [0, 0, 0, 0, 0, 1, 1, 1, 1]


def test_default_kaggle_runner_is_packaged_source():
    expected = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "companion_768d_kaggle_runner.py"
    )

    assert DEFAULT_RUNNER == expected
    assert DEFAULT_RUNNER.is_file()


def test_kaggle_runner_uses_unknown_rescue_for_coverage_and_training():
    runner = DEFAULT_RUNNER.read_text(encoding="utf-8")

    assert "encode_with_unknown_fallback" in runner
    assert "_encode_documents" in runner
    assert "_tokenize_documents" in runner


def test_kaggle_runner_supports_append_only_vocab_migration():
    runner = DEFAULT_RUNNER.read_text(encoding="utf-8")

    assert "NOVA_VOCAB_MODE" in runner
    assert "concept_expand" in runner
    assert "extend_tokenizer_state" in runner
    assert "copy_vocab_expanded_state" in runner
    assert "_config_from_checkpoint(checkpoint, vocab_size=" in runner
    assert "_refresh_tokenizer_maps" in runner
