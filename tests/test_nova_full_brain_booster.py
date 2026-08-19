from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_full_brain_booster as booster


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_full_brain_booster_builds_focused_sft_splits(tmp_path):
    manifest = booster.build_booster_dataset(tmp_path, target_count=600, seed=11)

    assert manifest["record_count"] == 600
    assert set(manifest["split_counts"]) == {"train", "validation", "holdout"}
    assert manifest["split_counts"]["train"] > manifest["split_counts"]["validation"] > 0
    assert manifest["split_counts"]["holdout"] > 0

    output_dir = tmp_path / "artifacts" / "nova_full_brain_booster"
    all_rows = []
    for split in ("train", "validation", "holdout"):
        rows = _rows(output_dir / f"{split}.jsonl")
        assert rows
        assert all(row["split"] == split for row in rows)
        all_rows.extend(rows)

    required_keys = {"id", "source", "category", "prompt", "response", "messages", "quality_tags", "split"}
    for row in all_rows:
        assert required_keys <= set(row)
        assert row["messages"][0]["role"] == "system"
        assert row["messages"][-2]["role"] == "user"
        assert row["messages"][-1]["role"] == "assistant"
        assert row["messages"][-1]["content"] == row["response"]
        assert not booster._has_banned_response(row["response"])
        assert row["prompt"].strip().lower() != row["response"].strip().lower()

    categories = {row["category"] for row in all_rows}
    assert {
        "agentic_action_loop",
        "robot_body_awareness",
        "sensor_overlay_awareness",
        "memory_action_rules",
        "anti_vague_execution",
        "natural_presence",
    } <= categories


def test_full_brain_booster_is_deterministic(tmp_path):
    first = booster.build_booster_dataset(tmp_path / "a", target_count=500, seed=77)
    second = booster.build_booster_dataset(tmp_path / "b", target_count=500, seed=77)

    assert first["content_fingerprint"] == second["content_fingerprint"]
    assert first["split_counts"] == second["split_counts"]


def test_full_brain_benchmark_scores_missing_and_bad_markers():
    case = {
        "keywords": ["inspect", "fix", "re-test"],
        "bad_markers": ["cannot"],
    }

    good = booster.score_output("I will inspect the blocker, fix the route, and re-test it.", case)
    bad = booster.score_output("I cannot do that, but I'll fix it.", case)

    assert good["score"] == 100
    assert good["missing_keywords"] == []
    assert bad["score"] < good["score"]
    assert bad["bad_hits"] == ["cannot"]


def test_full_brain_benchmark_cases_cover_known_weak_spots():
    names = {case["name"] for case in booster.benchmark_cases()}

    assert {
        "agentic_fix_loop",
        "robot_body_awareness",
        "sensor_distance_mode",
        "long_term_memory_rule",
        "anti_vague_action",
    } <= names
