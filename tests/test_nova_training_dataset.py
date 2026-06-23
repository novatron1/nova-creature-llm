from pathlib import Path
from collections import Counter
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_torch_transformer import ModelConfig
from nova_training_dataset import (
    ROLE_TRAINING_BLOCK_SIZE,
    build_dataset,
    clean_record,
    grouped_split,
)


EXPECTED_ACCEPTED_KEYS = {
    "id",
    "source",
    "intent_group",
    "domain",
    "primary_role",
    "support_roles",
    "prompt",
    "answer",
    "quality_flags",
    "task_type",
}


def test_recursive_followup_is_quarantined():
    record = {
        "user": "yeah",
        "nova": "I recall your last question. I recall your last question. More?",
        "source": "conversation",
    }
    cleaned, reason = clean_record(record)
    assert cleaned is None
    assert reason == "recursive_followup"


def test_truncated_answer_is_quarantined():
    cleaned, reason = clean_record(
        {"prompt": "What is love?", "answer": "Love is a deep emotional bon", "source": "dictionary_hit"}
    )
    assert cleaned is None
    assert reason == "truncated_answer"


def test_role_training_prompt_boundary_comes_from_model_config():
    assert ROLE_TRAINING_BLOCK_SIZE == ModelConfig().block_size


def test_role_training_prompt_that_preserves_sep_is_accepted_at_boundary():
    prompt = "x" * (ModelConfig().block_size - 2)
    cleaned, reason = clean_record({"prompt": prompt, "answer": "Short answer.", "source": "unit"})
    assert reason is None
    assert cleaned is not None


def test_role_training_prompt_too_long_to_keep_sep_is_quarantined():
    prompt = "x" * (ModelConfig().block_size - 1)
    cleaned, reason = clean_record({"prompt": prompt, "answer": "Short answer.", "source": "unit"})
    assert cleaned is None
    assert reason == "prompt_too_long_for_role_training"


def test_paraphrase_group_never_crosses_splits():
    rows = [
        {"id": "1", "intent_group": "creator_identity", "prompt": "Who made you?", "answer": "Mr. Novotron."},
        {"id": "2", "intent_group": "creator_identity", "prompt": "Who created you?", "answer": "Mr. Novotron."},
        {"id": "3", "intent_group": "quadratic", "prompt": "Quadratic formula?", "answer": "x = (-b ± sqrt(b² - 4ac)) / (2a)."},
    ]
    splits = grouped_split(rows, seed=20260622)
    locations = {
        row["intent_group"]: split
        for split, values in splits.items()
        for row in values
    }
    assert sum(any(row["intent_group"] == "creator_identity" for row in values) for values in splits.values()) == 1
    assert set(splits) == {"train", "validation", "promotion"}


def test_grouped_split_bucket_boundaries_are_exact():
    rows = [
        {"id": "train-69", "intent_group": "boundary_8", "prompt": "train 69", "answer": "ok"},
        {"id": "validation-70", "intent_group": "boundary_60", "prompt": "validation 70", "answer": "ok"},
        {"id": "validation-84", "intent_group": "boundary_179", "prompt": "validation 84", "answer": "ok"},
        {"id": "promotion-85", "intent_group": "boundary_67", "prompt": "promotion 85", "answer": "ok"},
    ]
    splits = grouped_split(rows, seed=20260622)
    assert [row["id"] for row in splits["train"]] == ["train-69"]
    assert [row["id"] for row in splits["validation"]] == ["validation-70", "validation-84"]
    assert [row["id"] for row in splits["promotion"]] == ["promotion-85"]


def test_project_root_import_reexports_public_api():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import nova_training_dataset as m; "
                "print(all(hasattr(m, name) for name in "
                "('clean_record', 'grouped_split', 'build_dataset', 'main')))"
            ),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "True"


def test_identical_normalized_prompts_never_cross_splits():
    rows = [
        {
            "id": "a",
            "intent_group": "alpha",
            "domain": "coding",
            "primary_role": "left_hemisphere",
            "prompt": " Explain routing? ",
            "answer": "Use code reasoning.",
        },
        {
            "id": "b",
            "intent_group": "beta",
            "domain": "critic",
            "primary_role": "critic_conscience_transformer",
            "prompt": "explain   routing?",
            "answer": "Check the evidence.",
        },
    ]
    splits = grouped_split(rows, seed=42)
    locations = [
        split
        for split, values in splits.items()
        for row in values
        if row["prompt"].lower().split() == ["explain", "routing?"]
    ]
    assert len(set(locations)) == 1


def test_conversation_prompts_infer_domains_before_generic_speech_default():
    cases = [
        ("what is calculus", "Calculus studies change.", "math", "left_hemisphere"),
        ("what is gravity", "Gravity attracts mass.", "science", "memory_transformer"),
        ("who are you", "Nova Creature.", "memory_recall", "memory_transformer"),
        ("verify this evidence", "The evidence must support the claim.", "critic", "critic_conscience_transformer"),
        ("hello", "Hi there.", "general", "speech_output_transformer"),
    ]
    for prompt, answer, domain, role in cases:
        cleaned, reason = clean_record(
            {
                "user": prompt,
                "nova": answer,
                "source": "conversation",
                "_source_path": "data/conversation_training_data.jsonl",
            }
        )
        assert reason is None
        assert cleaned is not None
        assert cleaned["domain"] == domain
        assert cleaned["primary_role"] == role


def test_route_log_records_keep_route_label_without_empty_answer_quarantine():
    cleaned, reason = clean_record(
        {
            "text": "What is a variable in Python?",
            "domain": "coding",
            "route": ["left_hemisphere", "planner_transformer"],
            "source": "fallback",
            "_source_path": "data/routing_log.jsonl",
        }
    )
    assert reason is None
    assert cleaned is not None
    assert set(cleaned) == EXPECTED_ACCEPTED_KEYS
    assert cleaned["task_type"] == "route"
    assert cleaned["quality_flags"] == ["route_source:fallback"]
    assert cleaned["prompt"] == "What is a variable in Python?"
    assert cleaned["domain"] == "coding"
    assert cleaned["primary_role"] == "left_hemisphere"
    assert cleaned["support_roles"] == ["planner_transformer"]
    assert cleaned["answer"] == "Route to left_hemisphere for coding."


def test_route_log_rejects_tiny_greeting_and_questionable_route_prompts():
    cases = [
        {
            "text": "bet",
            "domain": "dictionary",
            "route": ["memory_transformer"],
            "source": "hit",
            "_source_path": "data/routing_log.jsonl",
        },
        {
            "text": "hello",
            "domain": "general",
            "route": ["speech_output_transformer"],
            "source": "fallback",
            "_source_path": "data/routing_log.jsonl",
        },
        {
            "text": "Can you code?",
            "domain": "coding",
            "route": ["left_hemisphere"],
            "source": "fallback",
            "_source_path": "data/routing_log.jsonl",
        },
        {
            "text": "can you help me debug my python code family/friends",
            "domain": "coding",
            "route": ["memory_transformer"],
            "source": "memory_hit",
            "_source_path": "data/routing_log.jsonl",
        },
    ]
    for record in cases:
        cleaned, reason = clean_record(record)
        assert cleaned is None
        assert reason == "weak_route_prompt"


def test_truncation_accepts_short_technical_endings_but_rejects_fragments():
    for answer in [
        "Functions are defined with def",
        "x = (-b ± sqrt(b² - 4ac)) / 2a",
        "x = (-b ± sqrt(b² - 4ac))/2a",
        "ax²+bx+c=0",
    ]:
        cleaned, reason = clean_record({"prompt": "Technical answer?", "answer": answer, "source": "unit"})
        assert reason is None
        assert cleaned is not None

    cleaned, reason = clean_record(
        {"prompt": "What is love?", "answer": "Love is a deep emotional bon", "source": "dictionary_hit"}
    )
    assert cleaned is None
    assert reason == "truncated_answer"


def test_fallback_template_is_normalized_and_high_repetition_is_quarantined():
    for answer in [" i do not know. ", "I do not know", "i don't know", "I don't know."]:
        cleaned, reason = clean_record({"prompt": "Unknown?", "answer": answer, "source": "unit"})
        assert cleaned is None
        assert reason == "fallback_template"

    cleaned, reason = clean_record({"prompt": "Repeat?", "answer": "loop loop loop loop done.", "source": "unit"})
    assert cleaned is None
    assert reason == "high_repetition"


def test_clean_record_shape_and_stable_id_are_strict():
    record = {
        "prompt": "Who created Nova?",
        "answer": "Mr. Novotron.",
        "source": "unit",
        "domain": "memory_recall",
        "primary_role": "memory_transformer",
    }
    first, first_reason = clean_record(record)
    second, second_reason = clean_record(record)
    assert first_reason is None
    assert second_reason is None
    assert first is not None
    assert second is not None
    assert set(first) == EXPECTED_ACCEPTED_KEYS
    assert first["task_type"] == "answer"
    assert first["id"] == second["id"]
    assert len(first["id"]) == 64
    json.dumps(first, allow_nan=False)


def test_promotion_bank_is_top_level_protected_case_array():
    bank_path = ROOT / "benchmark_lab" / "test_banks" / "transformer_route_promotion_bank.json"
    cases = json.loads(bank_path.read_text(encoding="utf-8"))
    assert isinstance(cases, list)
    assert len(cases) == 21
    required = {"id", "prompt", "domain", "primary_role", "required_terms", "protected"}
    assert all(required <= set(case) for case in cases)
    assert all(case["protected"] is True for case in cases)
    assert len({case["id"] for case in cases}) == 21
    assert Counter(case["primary_role"] for case in cases) == {
        "left_hemisphere": 3,
        "planner_transformer": 3,
        "critic_conscience_transformer": 3,
        "right_hemisphere": 3,
        "memory_transformer": 3,
        "dream_simulation_transformer": 3,
        "speech_output_transformer": 3,
    }


def test_build_dataset_manifest_is_posix_strict_and_excludes_promotion_bank(tmp_path):
    bank_dir = tmp_path / "benchmark_lab" / "test_banks"
    bank_dir.mkdir(parents=True)
    bank_prompt = "Promotion bank prompt must stay sealed."
    (bank_dir / "transformer_route_promotion_bank.json").write_text(
        json.dumps(
            [
                {
                    "id": "sealed-001",
                    "prompt": bank_prompt,
                    "domain": "critic",
                    "primary_role": "critic_conscience_transformer",
                    "required_terms": ["sealed"],
                    "protected": True,
                }
            ]
        ),
        encoding="utf-8",
    )

    source_dir = tmp_path / "exports" / "v053_training_sets"
    source_dir.mkdir(parents=True)
    (source_dir / "left_hemisphere_training_set.json").write_text(
        json.dumps(
            [
                {"prompt": "Same prompt", "answer": "Use a loop.", "source": "unit-a"},
                {"prompt": " same   prompt ", "answer": "Use a function.", "source": "unit-b"},
            ]
        ),
        encoding="utf-8",
    )

    manifest = build_dataset(tmp_path)
    json.dumps(manifest, allow_nan=False)
    assert all("/" in path and "\\" not in path for path in manifest["outputs"].values())

    split_files = {
        "train": tmp_path / "artifacts" / "transformer_training" / "dataset" / "train.jsonl",
        "validation": tmp_path / "artifacts" / "transformer_training" / "dataset" / "validation.jsonl",
        "promotion": tmp_path / "artifacts" / "transformer_training" / "dataset" / "promotion.jsonl",
    }
    prompts_by_split = {}
    all_prompts = set()
    for split, path in split_files.items():
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        prompts_by_split[split] = {row["prompt"].lower().strip() for row in rows}
        all_prompts.update(row["prompt"] for row in rows)
        for row in rows:
            assert set(row) == EXPECTED_ACCEPTED_KEYS
            json.dumps(row, allow_nan=False)

    assert bank_prompt not in all_prompts
    assert sum("same prompt" in prompts for prompts in prompts_by_split.values()) == 1
