from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from datetime import datetime

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]

def backup_if_exists(path: Path):
    if path.exists():
        backup = path.with_suffix(path.suffix + ".codex_backup")
        if not backup.exists():
            shutil.copy2(path, backup)

def copy_file(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup_if_exists(dest)
    shutil.copy2(src, dest)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()

    bundle_root = Path(__file__).resolve().parents[1]
    project = Path(args.project_root).resolve()

    print("Applying Nova Creature Codex Cloud Catch-Up")
    print("Project:", project)
    print("Bundle:", bundle_root)

    # Copy src/scripts.
    for src in (bundle_root / "src").glob("*.py"):
        copy_file(src, project / "src" / src.name)
    for src in (bundle_root / "scripts").glob("*.py"):
        copy_file(src, project / "scripts" / src.name)

    # Brain slots.
    for role in ROLES:
        slot = project / "checkpoints" / "brain_slots" / role
        slot.mkdir(parents=True, exist_ok=True)
        cfg = slot / "brain_slot_config.json"
        if not cfg.exists():
            cfg.write_text(json.dumps({
                "slot": role,
                "checkpoint_status": "awaiting_checkpoint_or_v054_builder",
                "checkpoint_path": "",
                "role_layer": "installed",
                "cloud_project": True
            }, indent=2), encoding="utf-8")

    # Training folders.
    for role in ROLES:
        d = project / "training_data" / "role_brains" / role
        d.mkdir(parents=True, exist_ok=True)
        for fn in ["pending_lessons.jsonl", "approved_lessons.jsonl"]:
            p = d / fn
            if not p.exists():
                p.write_text("", encoding="utf-8")

    # Docs.
    (project / "reports").mkdir(exist_ok=True)
    status = {
        "version": "codex_cloud_catchup_v049_to_v055",
        "created_at": datetime.now().isoformat(),
        "project_root": str(project),
        "installed": {
            "v049_brain_slots": True,
            "v050_router": True,
            "v051_chat_adapter": True,
            "v052_role_layers": True,
            "v053_training_prep": True,
            "v054_role_checkpoint_builder": True,
            "v055_cloud_torch_ready_script": True
        }
    }
    (project / "reports" / "codex_cloud_catchup_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
    print("PASS: Codex cloud catch-up applied.")
    print("Next:")
    print("  python scripts/check_codex_brain_stack.py")
    print("  python scripts/v053_training_prep.py gold")
    print("  python scripts/v054_role_checkpoint_builder.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
