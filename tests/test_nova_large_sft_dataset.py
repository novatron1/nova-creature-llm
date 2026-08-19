from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_large_sft_dataset as large_sft


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_large_sft_dataset_builds_schema_splits_and_preferences(tmp_path):
    manifest = large_sft.build_large_sft_dataset(tmp_path, target_count=750, seed=123)

    assert manifest["record_count"] == 750
    assert manifest["preference_pair_count"] >= 150
    assert set(manifest["split_counts"]) == {"train", "validation", "holdout"}
    assert manifest["split_counts"]["train"] > manifest["split_counts"]["validation"] > 0
    assert manifest["split_counts"]["holdout"] > 0

    output_dir = tmp_path / "artifacts" / "nova_large_sft_dataset"
    all_rows = []
    for split in ("train", "validation", "holdout"):
        rows = _rows(output_dir / f"{split}.jsonl")
        all_rows.extend(rows)
        assert rows
        assert all(row["split"] == split for row in rows)

    required_keys = {"id", "source", "category", "prompt", "response", "messages", "quality_tags", "split"}
    for row in all_rows:
        assert required_keys <= set(row)
        assert row["messages"][0]["role"] == "system"
        assert row["messages"][-2]["role"] == "user"
        assert row["messages"][-1]["role"] == "assistant"
        assert row["messages"][-1]["content"] == row["response"]
        assert not large_sft._has_banned_response(row["response"])
        assert row["prompt"].strip().lower() != row["response"].strip().lower()

    categories = {row["category"] for row in all_rows}
    assert {
        "natural_conversation",
        "style_feedback",
        "memory_write",
        "memory_recall",
        "voice_vision_tools",
        "sensor_overlay",
        "agentic_navigation",
        "coding_app_repair",
        "knowledge",
        "critic_safety",
        "robot_body",
    } <= categories

    pairs = _rows(output_dir / "preference_pairs.jsonl")
    assert pairs
    for pair in pairs:
        assert {"id", "prompt", "chosen", "rejected", "category", "source"} <= set(pair)
        assert pair["chosen"] != pair["rejected"]
        assert not large_sft._has_banned_response(pair["chosen"])
        assert large_sft._has_banned_response(pair["rejected"])


def test_large_sft_dataset_is_deterministic(tmp_path):
    first = large_sft.build_large_sft_dataset(tmp_path / "a", target_count=300, seed=77)
    second = large_sft.build_large_sft_dataset(tmp_path / "b", target_count=300, seed=77)

    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert first["split_counts"] == second["split_counts"]


def test_large_sft_harvest_rejects_echo_rows(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "conversation_training_data.jsonl").write_text(
        json.dumps({"user": "Explain: bad echo", "nova": "Explain: bad echo"}) + "\n"
        + json.dumps({"user": "how u doing", "nova": "I'm here with you."}) + "\n",
        encoding="utf-8",
    )

    manifest = large_sft.build_large_sft_dataset(tmp_path, target_count=50, seed=5)
    train_rows = _rows(tmp_path / manifest["outputs"]["train"])
    validation_rows = _rows(tmp_path / manifest["outputs"]["validation"])
    holdout_rows = _rows(tmp_path / manifest["outputs"]["holdout"])
    prompts = {row["prompt"] for row in [*train_rows, *validation_rows, *holdout_rows]}

    assert "Explain: bad echo" not in prompts
    assert "how u doing" in prompts
