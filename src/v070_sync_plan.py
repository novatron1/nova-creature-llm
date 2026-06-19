from __future__ import annotations

"""v070 — Local + Cloud Sync Plan

Defines the sync contract between cloud and local Nova Creature instances.

This module documents what artifacts can sync, generates a sync manifest,
and provides dry-run planning. It does NOT connect to any external
machine — it only produces the sync plan manifest.

Syncable artifacts:
- checkpoints/brain_slots/ (v054, v055)
- checkpoints/base/ (v032 base, v019 fallback)
- data/dictionary_memory/ (approved Q&A)
- data/smart_memory/ (memory stores)
- exports/v053_training_sets/ (training data)
- reports/ (status reports)
- src/ (source code)
- scripts/ (CLI scripts)
"""

import json, hashlib
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

SYNC_MANIFEST_PATH = ROOT / "reports" / "v070_sync_manifest.json"

SYNC_GROUPS: list[dict[str, Any]] = [
    {
        "id": "checkpoints_base",
        "label": "Base checkpoints",
        "paths": ["checkpoints/base/*.pt"],
        "essential": True,
        "direction": "cloud_to_local",
    },
    {
        "id": "brain_slots",
        "label": "Role brain checkpoints",
        "paths": ["checkpoints/brain_slots/*/*.pt"],
        "essential": True,
        "direction": "cloud_to_local",
    },
    {
        "id": "dictionary_memory",
        "label": "Dictionary Q&A memory",
        "paths": ["data/dictionary_memory/*.json"],
        "essential": True,
        "direction": "bidirectional",
    },
    {
        "id": "smart_memory",
        "label": "Smart memory stores",
        "paths": ["data/smart_memory/*.jsonl"],
        "essential": True,
        "direction": "bidirectional",
    },
    {
        "id": "training_sets",
        "label": "Training sets",
        "paths": ["exports/v053_training_sets/*.json"],
        "essential": True,
        "direction": "cloud_to_local",
    },
    {
        "id": "reports",
        "label": "Status reports",
        "paths": ["reports/*.json"],
        "essential": False,
        "direction": "cloud_to_local",
    },
    {
        "id": "source_code",
        "label": "Source code (src/scripts)",
        "paths": ["src/*.py", "scripts/*.py"],
        "essential": True,
        "direction": "cloud_to_local",
    },
    {
        "id": "conversation_logs",
        "label": "Conversation history",
        "paths": ["data/conversation_memory/*.jsonl"],
        "essential": False,
        "direction": "bidirectional",
    },
    {
        "id": "error_bank",
        "label": "Error bank",
        "paths": ["data/error_bank/*.jsonl"],
        "essential": False,
        "direction": "bidirectional",
    },
    {
        "id": "vision_logs",
        "label": "Vision stream logs",
        "paths": ["data/vision_stream/*.jsonl"],
        "essential": False,
        "direction": "bidirectional",
    },
]


def root() -> Path:
    return ROOT


def generate_sync_manifest() -> dict[str, Any]:
    """Generate a sync manifest listing all artifacts and their hashes."""
    groups = []
    total_files = 0
    total_size = 0

    for group in SYNC_GROUPS:
        files = []
        for pattern in group["paths"]:
            for p in sorted(ROOT.glob(pattern)):
                if p.is_file() and p.stat().st_size > 0:
                    fhash = hashlib.sha256(p.read_bytes()).hexdigest()
                    files.append({
                        "path": str(p.relative_to(ROOT)),
                        "size_bytes": p.stat().st_size,
                        "sha256": fhash,
                        "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(),
                    })
                    total_files += 1
                    total_size += p.stat().st_size

        groups.append({
            "id": group["id"],
            "label": group["label"],
            "essential": group["essential"],
            "direction": group["direction"],
            "file_count": len(files),
            "total_size_bytes": sum(f["size_bytes"] for f in files),
            "files": files,
        })

    manifest = {
        "version": "v070_sync_plan",
        "created_at": datetime.now().isoformat(),
        "project_root": str(ROOT),
        "total_groups": len(groups),
        "total_files": total_files,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 1),
        "groups": groups,
        "sync_command_template": (
            "To sync: copy the listed files from cloud to local project root.\n"
            "Use rsync, scp, or manual copy. Do NOT overwrite local "
            "dictionary memory without backup."
        ),
    }

    SYNC_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


def print_plan(manifest: dict[str, Any] | None = None):
    if manifest is None:
        manifest = generate_sync_manifest()

    print("Nova Creature v070 — Local + Cloud Sync Plan\n")
    print(f"Total files: {manifest['total_files']}")
    print(f"Total size:  {manifest['total_size_mb']} MB\n")

    for g in manifest["groups"]:
        essential = "⭐" if g["essential"] else "  "
        label = g["label"]
        direction = g["direction"]
        count = g["file_count"]
        mb = round(g["total_size_bytes"] / (1024 * 1024), 1)
        print(f"  {essential} {label} ({count} files, {mb} MB) [{direction}]")

    print(f"\n{manifest['sync_command_template']}")
    print(f"\nFull manifest: {SYNC_MANIFEST_PATH}")


def main() -> int:
    manifest = generate_sync_manifest()
    print_plan(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
