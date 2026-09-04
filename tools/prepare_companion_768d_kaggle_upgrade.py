from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNNER = ROOT / "tools" / "companion_768d_kaggle_runner.py"
DEFAULT_TOKEN_UTILS = ROOT / "tools" / "companion_768d_token_utils.py"
DEFAULT_CONCEPT_ROOT = ROOT / "artifacts" / "companion_768d_dictionary_upgrade"
DEFAULT_OUTPUT = ROOT / "artifacts" / "companion_768d_kaggle_upgrade_bundle"


def validate_base_checkpoint(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Base checkpoint does not exist: {resolved}")
    return resolved


def build_run_manifest(
    *,
    base_checkpoint: Path,
    concept_root: Path,
    run_dir: Path,
    max_steps: int,
    concept_ratio: float,
    learning_rate: float,
) -> dict[str, Any]:
    checkpoint = validate_base_checkpoint(base_checkpoint)
    concept_root = Path(concept_root).expanduser().resolve()
    run_dir = Path(run_dir).expanduser().resolve()
    if run_dir == checkpoint.parent:
        raise ValueError("Upgrade run_dir must be separate from the base checkpoint directory")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if not 0 < concept_ratio <= 1:
        raise ValueError("concept_ratio must be greater than 0 and at most 1")
    if learning_rate <= 0:
        raise ValueError("learning_rate must be positive")
    return {
        "version": "companion_768d_kaggle_upgrade_v1",
        "base_checkpoint": str(checkpoint),
        "concept_root": str(concept_root),
        "run_dir": str(run_dir),
        "max_steps": int(max_steps),
        "concept_ratio": float(concept_ratio),
        "learning_rate": float(learning_rate),
        "tokenizer_policy": "load_and_validate_base_checkpoint_tokenizer",
        "optimizer_policy": "reset_for_continuation",
    }


def prepare_bundle(
    *,
    runner_source: Path,
    concept_root: Path,
    base_checkpoint: Path,
    output_dir: Path,
    run_dir: Path,
    max_steps: int,
    concept_ratio: float,
    learning_rate: float,
) -> dict[str, Any]:
    manifest = build_run_manifest(
        base_checkpoint=base_checkpoint,
        concept_root=concept_root,
        run_dir=run_dir,
        max_steps=max_steps,
        concept_ratio=concept_ratio,
        learning_rate=learning_rate,
    )
    runner_source = Path(runner_source).expanduser().resolve()
    if not runner_source.is_file():
        raise FileNotFoundError(f"Runner source does not exist: {runner_source}")
    concept_root = Path(concept_root).expanduser().resolve()
    required = [concept_root / "train.jsonl", concept_root / "validation.jsonl"]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Concept artifact is missing: {missing}")

    output_dir = Path(output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runner_source, output_dir / "nova-companion-768d-concept-upgrade.py")
    shutil.copy2(DEFAULT_TOKEN_UTILS, output_dir / "companion_768d_token_utils.py")
    target_concepts = output_dir / "concept_upgrade"
    target_concepts.mkdir(parents=True, exist_ok=True)
    for source in concept_root.iterdir():
        if source.is_file():
            shutil.copy2(source, target_concepts / source.name)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Nova Companion 768d Kaggle upgrade bundle")
    parser.add_argument("--runner-source", type=Path, default=DEFAULT_RUNNER)
    parser.add_argument("--concept-root", type=Path, default=DEFAULT_CONCEPT_ROOT)
    parser.add_argument("--base-checkpoint", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--max-steps", type=int, default=8000)
    parser.add_argument("--concept-ratio", type=float, default=0.75)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    args = parser.parse_args()
    manifest = prepare_bundle(
        runner_source=args.runner_source,
        concept_root=args.concept_root,
        base_checkpoint=args.base_checkpoint,
        output_dir=args.output_dir,
        run_dir=args.run_dir,
        max_steps=args.max_steps,
        concept_ratio=args.concept_ratio,
        learning_rate=args.learning_rate,
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
