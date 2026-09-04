from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import train_nova_lora_sft as lora_sft


def _write_dataset(root: Path):
    dataset = root / "artifacts" / "nova_large_sft_dataset"
    dataset.mkdir(parents=True)
    rows = [
        {
            "id": "one",
            "category": "natural_conversation",
            "prompt": "how u doing",
            "response": "I'm here with you.",
            "messages": [
                {"role": "system", "content": "You are Nova Creature."},
                {"role": "user", "content": "how u doing"},
                {"role": "assistant", "content": "I'm here with you."},
            ],
        },
        {
            "id": "two",
            "category": "memory_recall",
            "prompt": "what is my city",
            "response": "You live in Cincinnati.",
            "messages": [
                {"role": "system", "content": "You are Nova Creature."},
                {"role": "user", "content": "remember that my city is Cincinnati"},
                {"role": "assistant", "content": "Got it."},
                {"role": "user", "content": "what is my city"},
                {"role": "assistant", "content": "You live in Cincinnati."},
            ],
        },
    ]
    for split in ("train", "validation", "holdout"):
        (dataset / f"{split}.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
    return dataset


def test_lora_sft_dataset_validation_and_chat_format(tmp_path):
    dataset = _write_dataset(tmp_path)

    records = lora_sft.load_dataset_records(dataset, max_train_records=1)
    report = lora_sft.validate_records(records)

    assert report["counts"]["train"] == 1
    assert report["counts"]["validation"] == 2
    assert report["problem_count"] == 0
    text = lora_sft.format_chat_text(records["validation"][0]["messages"])
    assert "System: You are Nova Creature." in text
    assert "User: how u doing" in text
    assert "Nova Creature: I'm here with you." in text


def test_lora_sft_dry_run_cli_does_not_require_training_libraries(tmp_path):
    _write_dataset(tmp_path)
    resume_adapter = tmp_path / "models" / "lora_adapters" / "active"
    resume_adapter.mkdir(parents=True)

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools" / "train_nova_lora_sft.py"),
            "--project-root",
            str(tmp_path),
            "--max-train-records",
            "1",
            "--resume-adapter-dir",
            str(resume_adapter),
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["dataset_validation"]["counts"]["train"] == 1
    assert payload["base_model"] == lora_sft.DEFAULT_BASE_MODEL
    assert payload["use_4bit"] is True
    assert payload["resume_adapter_dir"] == str(resume_adapter)
