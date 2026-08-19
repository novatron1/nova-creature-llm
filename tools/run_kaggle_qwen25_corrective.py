from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAINER = ROOT / "tools" / "train_qwen25_corrective_lora.py"
DATASET = ROOT / "artifacts" / "nova_qwen25_corrective_20260723"
OUTPUT = Path("/kaggle/working/nova_qwen25_corrective_adapter_20260723")


def main() -> int:
    command = [
        sys.executable,
        str(TRAINER),
        "--project-root",
        str(ROOT),
        "--dataset-dir",
        str(DATASET.relative_to(ROOT)),
        "--output-dir",
        str(OUTPUT),
        "--epochs",
        "2",
        "--learning-rate",
        "1e-4",
        "--use-4bit",
    ]
    print("Starting Nova Qwen2.5 1.5B corrective assistant-only QLoRA.")
    print(f"Training rows: {sum(1 for _ in (DATASET / 'train.jsonl').open(encoding='utf-8'))}")
    print(f"Output: {OUTPUT}")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
