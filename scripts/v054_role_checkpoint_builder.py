from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from datetime import datetime

BASE_CHECKPOINT_NAME = "creature_v032_bigfit_twenty_plain.pt"

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

def root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_any_checkpoint() -> Path | None:
    """Find the best available checkpoint in priority order."""
    r = root()

    # Priority 1: checkpoints/base/
    p1 = r / "checkpoints" / "base" / BASE_CHECKPOINT_NAME
    if p1.exists() and p1.stat().st_size > 0:
        return p1

    # Priority 2: checkpoints/experimental/
    p2 = r / "checkpoints" / "experimental" / BASE_CHECKPOINT_NAME
    if p2.exists() and p2.stat().st_size > 0:
        return p2

    # Priority 3: any other .pt under checkpoints/ (excluding v054/v055 output)
    pts = list((r / "checkpoints").glob("**/*.pt")) if (r / "checkpoints").exists() else []
    pts = [p for p in pts if "v054" not in p.name and "v055" not in p.name]
    pts.sort(key=lambda p: p.stat().st_size, reverse=True)
    return pts[0] if pts else None


def _checkpoint_priority_label(checkpoint: Path | None, project_root: Path) -> str:
    if checkpoint is None:
        return "none"
    try:
        rel = str(checkpoint.relative_to(project_root))
    except ValueError:
        rel = str(checkpoint)
    if rel == f"checkpoints/base/{BASE_CHECKPOINT_NAME}":
        return "1_base_priority"
    if rel == f"checkpoints/experimental/{BASE_CHECKPOINT_NAME}":
        return "2_experimental_priority"
    return "3_fallback_glob"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build():
    r = root()
    base = find_any_checkpoint()
    reports = r / "reports"
    reports.mkdir(exist_ok=True)
    manifests = []
    source_info = {
        "found": bool(base),
        "path": str(base) if base else None,
        "priority": _checkpoint_priority_label(base, r) if base else None,
    }

    for role in ROLES:
        slot = r / "checkpoints" / "brain_slots" / role
        slot.mkdir(parents=True, exist_ok=True)
        out = slot / f"{role}_v054_specialized.pt"
        training = r / "exports" / "v053_training_sets" / f"{role}_training_set.json"
        lessons = []
        if training.exists():
            lessons = json.loads(training.read_text(encoding="utf-8"))

        if base:
            shutil.copy2(base, out)
            checkpoint_status = "copied_from_available_base_checkpoint"
            file_hash = sha256(out)
        else:
            out.write_text(
                "PLACEHOLDER: add a real .pt checkpoint to enable actual training.\n",
                encoding="utf-8",
            )
            checkpoint_status = "missing_checkpoint_placeholder"
            file_hash = sha256(out)

        manifest = {
            "version": "codex_cloud_v054",
            "created_at": datetime.now().isoformat(),
            "role": role,
            "checkpoint": str(out.relative_to(r)),
            "checkpoint_status": checkpoint_status,
            "source_checkpoint": str(base.relative_to(r)) if base else "",
            "source_priority": _checkpoint_priority_label(base, r) if base else "",
            "training_set": str(training.relative_to(r)) if training.exists() else "",
            "lesson_count": len(lessons),
            "sha256": file_hash,
        }
        (slot / "v054_role_checkpoint_manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        (slot / "brain_slot_config_v054.json").write_text(
            json.dumps(
                {
                    "slot": role,
                    "checkpoint_path": f"./{out.name}",
                    "checkpoint_status": checkpoint_status,
                    "source_checkpoint": str(base.relative_to(r)) if base else "",
                    "source_priority": _checkpoint_priority_label(base, r) if base else "",
                    "training_set": str(training.relative_to(r)) if training.exists() else "",
                    "lesson_count": len(lessons),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        manifests.append(manifest)

    summary = {"roles": manifests, "source_checkpoint": source_info}
    (reports / "codex_v054_role_checkpoint_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("PASS: built cloud role checkpoint layer.")
    print("Base checkpoint:", base if base else "none; placeholders created")
    if base:
        print("Source priority:", _checkpoint_priority_label(base, r))


if __name__ == "__main__":
    build()
