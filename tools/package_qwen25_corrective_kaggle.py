from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DATASET = ROOT / "artifacts" / "nova_qwen25_corrective_20260723"
PACKAGE_ROOT = ROOT / "artifacts" / "nova_qwen25_corrective_kaggle_20260723"
STAGE = PACKAGE_ROOT / "package" / "nova_corrective"
ZIP_BASE = PACKAGE_ROOT / "nova_qwen25_corrective_kaggle_20260723"

ALLOWED_DATASET_FILES = (
    "train.jsonl",
    "validation.jsonl",
    "holdout.jsonl",
    "corrective_eval.json",
    "manifest.json",
    "KAGGLE_README.md",
)
ALLOWED_TOOL_FILES = (
    "train_qwen25_corrective_lora.py",
    "run_kaggle_qwen25_corrective.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    if PACKAGE_ROOT.exists():
        resolved = PACKAGE_ROOT.resolve()
        expected_parent = (ROOT / "artifacts").resolve()
        if resolved.parent != expected_parent or not resolved.name.startswith(
            "nova_qwen25_corrective_kaggle_"
        ):
            raise RuntimeError(f"Refusing to replace unexpected path: {resolved}")
        shutil.rmtree(resolved)

    data_target = STAGE / "artifacts" / SOURCE_DATASET.name
    tools_target = STAGE / "tools"
    data_target.mkdir(parents=True, exist_ok=True)
    tools_target.mkdir(parents=True, exist_ok=True)

    for name in ALLOWED_DATASET_FILES:
        shutil.copy2(SOURCE_DATASET / name, data_target / name)
    dataset_manifest_path = data_target / "manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    dataset_manifest["source_dir"] = "local_historical_dataset_filtered"
    dataset_manifest_path.write_text(
        json.dumps(dataset_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for name in ALLOWED_TOOL_FILES:
        shutil.copy2(ROOT / "tools" / name, tools_target / name)
    shutil.copy2(
        ROOT / "requirements-kaggle-corrective.txt",
        STAGE / "requirements-kaggle-corrective.txt",
    )
    shutil.copy2(
        SOURCE_DATASET / "KAGGLE_README.md",
        STAGE / "README.md",
    )

    packaged_files = sorted(path for path in STAGE.rglob("*") if path.is_file())
    manifest = {
        "package": "nova_qwen25_corrective_kaggle_20260723",
        "purpose": "Fresh assistant-only corrective QLoRA for Qwen2.5 1.5B",
        "privacy": {
            "contains_chat_history": False,
            "contains_memory_database": False,
            "contains_personal_files": False,
            "contains_previous_adapter": False,
        },
        "files": [
            {
                "path": path.relative_to(STAGE).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for path in packaged_files
        ],
    }
    manifest_path = STAGE / "PACKAGE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    archive = Path(shutil.make_archive(str(ZIP_BASE), "zip", STAGE))
    print(
        json.dumps(
            {
                "stage": str(STAGE),
                "archive": str(archive),
                "archive_bytes": archive.stat().st_size,
                "archive_sha256": sha256(archive),
                "packaged_file_count": len(packaged_files) + 1,
                "privacy": manifest["privacy"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
