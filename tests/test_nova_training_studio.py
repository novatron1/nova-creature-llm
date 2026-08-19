from __future__ import annotations

import json
import zipfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nova_training_studio import (  # noqa: E402
    build_training_studio_kaggle_bundle,
    import_training_data,
    list_correction_reviews,
    list_training_studio_datasets,
    review_correction_example,
    save_correction_example,
)
from nova_reviewed_training import ReviewedTrainingStore  # noqa: E402


def test_training_studio_imports_plain_text_into_sft_splits(tmp_path):
    report = import_training_data(
        tmp_path,
        name="Nova Style Notes",
        content=(
            "Nova should answer like a relaxed friend who stays with the conversation.\n\n"
            "When the user asks for training, Nova should build a dataset, validate it, and explain the GPU path."
        ),
        source_format="text",
    )

    assert report["ok"] is True
    assert report["record_count"] == 2
    assert report["split_counts"]["train"] >= 1
    dataset_dir = tmp_path / report["dataset_dir"]
    train_rows = [
        json.loads(line)
        for line in (dataset_dir / "train.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert train_rows
    assert train_rows[0]["messages"][-1]["role"] == "assistant"
    assert "training_studio" in train_rows[0]["quality_tags"]


def test_training_studio_imports_jsonl_prompt_response(tmp_path):
    content = "\n".join(
        [
            json.dumps({"prompt": "How should Nova talk?", "response": "Naturally and directly."}),
            json.dumps({"question": "What should Nova do with files?", "answer": "Import them and build a dataset."}),
        ]
    )

    report = import_training_data(tmp_path, name="Pairs", content=content, source_format="jsonl")

    assert report["record_count"] == 2
    assert report["category_counts"]["imported_pairs"] == 2
    assert report["preview"][0]["prompt"]


def test_training_studio_marks_explicit_reviewed_pack_ready_without_exposing_api_bypass(tmp_path):
    content = json.dumps(
        {
            "data": [
                {"prompt": "How should Nova answer?", "response": "Directly and naturally.", "category": "style"},
                {"prompt": "Should Nova guess?", "response": "No. It should be honest about uncertainty.", "category": "accuracy"},
            ]
        }
    )

    report = import_training_data(
        tmp_path,
        name="Reviewed Pack",
        content=content,
        source_format="json",
        reviewed=True,
        reviewer="user authorized curator",
    )

    assert report["record_count"] == 2
    assert report["training_ready"] is True
    assert report["review_required"] is False
    assert report["review_status"] == "approved"
    assert report["reviewer"] == "user authorized curator"
    dataset_dir = tmp_path / report["dataset_dir"]
    rows = []
    for split in ("train", "validation", "holdout"):
        rows.extend(
            json.loads(line)
            for line in (dataset_dir / f"{split}.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    assert all(row["quality_tags"] == ["reviewed", "user_authorized", "training_studio"] for row in rows)
    assert all(row["review_status"] == "approved" for row in rows)


def test_training_studio_lists_latest_dataset(tmp_path):
    first = import_training_data(tmp_path, name="One", content="First useful training note for Nova.", source_format="text")
    status = list_training_studio_datasets(tmp_path)

    assert status["ok"] is True
    assert status["latest"]["dataset_id"] == first["dataset_id"]
    assert status["datasets"][0]["dataset_id"] == first["dataset_id"]


def test_training_studio_kaggle_bundle_contains_dataset_and_trainer(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "train_nova_lora_sft.py").write_text("print('trainer')\n", encoding="utf-8")
    report = import_training_data(
        tmp_path,
        name="Bundle Test",
        content="Nova should turn imported notes into a trainable dataset.",
        source_format="text",
    )

    bundle = build_training_studio_kaggle_bundle(tmp_path, dataset_id=report["dataset_id"])

    assert bundle["ok"] is True
    zip_path = tmp_path / bundle["filename"]
    zip_path.write_bytes(bundle["bytes"])
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "nova_training_studio_kaggle.ipynb" in names
    assert "tools/train_nova_lora_sft.py" in names
    assert f"{report['dataset_dir']}/train.jsonl" in names


def test_training_studio_saves_bad_answer_correction_dataset(tmp_path):
    result = save_correction_example(
        tmp_path,
        user_input="How should Nova answer when I am tired?",
        bad_response="How can I assist you today?",
        better_response="Yeah, I hear you. Let's keep it light and do one small thing at a time.",
        trace={"route_path": ["speech_output_transformer"], "domain": "conversation"},
    )

    assert result["ok"] is True
    assert result["dataset"]["dataset_id"] == "user_corrections"
    assert result["dataset"]["record_count"] == 1
    feedback = tmp_path / "nova_training_logs" / "feedback.jsonl"
    assert feedback.exists()
    feedback_event = json.loads(feedback.read_text(encoding="utf-8").splitlines()[-1])
    assert feedback_event["feedback_type"] == "correction"
    assert "Let's keep it light" in feedback_event["target_answer"]
    train_rows = [
        json.loads(line)
        for line in (tmp_path / result["dataset"]["files"]["train"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert train_rows[0]["category"] == "user_correction"
    assert train_rows[0]["rejected_response"] == "How can I assist you today?"
    assert "review_pending" in train_rows[0]["quality_tags"]
    assert result["review"]["status"] == "pending"
    assert result["dataset"]["training_ready"] is False


def test_correction_requires_review_then_teaches_runtime_and_clean_dataset(tmp_path):
    saved = save_correction_example(
        tmp_path,
        user_input="Why do you sound robotic?",
        bad_response="How may I assist?",
        better_response="I fell into a canned response. I will stay with your actual words.",
        trace={"route_path": ["critic_conscience_transformer"], "domain": "self_reflection"},
    )

    pending = list_correction_reviews(tmp_path, status="pending")
    assert pending["counts"] == {"pending": 1, "approved": 0, "rejected": 0}
    assert pending["reviews"][0]["review_id"] == saved["review"]["review_id"]
    assert ReviewedTrainingStore(tmp_path / "data" / "reviewed_conversation_training.json").lookup(
        "Why do you sound robotic?"
    ) is None

    approved = review_correction_example(
        tmp_path,
        review_id=saved["review"]["review_id"],
        action="approve",
        response="Fair point. I used a canned response instead of answering your actual words.",
        aliases=["Why are you talking like a robot?", "That sounded robotic"],
    )

    assert approved["review"]["status"] == "approved"
    assert approved["dataset"]["dataset_id"] == "approved_corrections"
    assert approved["dataset"]["training_ready"] is True
    lesson = ReviewedTrainingStore(tmp_path / "data" / "reviewed_conversation_training.json").lookup(
        "Why do you sound robotic?"
    )
    assert lesson is not None
    assert "actual words" in lesson.response
    alias_lesson = ReviewedTrainingStore(
        tmp_path / "data" / "reviewed_conversation_training.json"
    ).lookup("Why are you talking like a robot?")
    assert alias_lesson is not None
    assert alias_lesson.lesson_id == lesson.lesson_id
    assert approved["review"]["approved_aliases"] == [
        "Why do you sound robotic?",
        "Why are you talking like a robot?",
        "That sounded robotic",
    ]
    approved_rows = [
        json.loads(line)
        for line in (tmp_path / approved["dataset"]["files"]["train"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert approved_rows[0]["quality_tags"] == ["human_reviewed", "approved", "training_studio"]


def test_rejected_correction_never_enters_runtime_or_approved_dataset(tmp_path):
    saved = save_correction_example(
        tmp_path,
        user_input="What is my secret?",
        bad_response="I guessed it.",
        better_response="The secret is probably blue.",
    )

    rejected = review_correction_example(
        tmp_path,
        review_id=saved["review"]["review_id"],
        action="reject",
    )

    assert rejected["review"]["status"] == "rejected"
    assert rejected["dataset"] is None
    assert rejected["queue"]["counts"]["rejected"] == 1
    assert not (tmp_path / "data" / "reviewed_conversation_training.json").exists()
