from __future__ import annotations

import hashlib
import json
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

BASE_CHECKPOINT_NAME = "creature_v032_bigfit_twenty_plain.pt"
FALLBACK_CHECKPOINT_NAME = "creature_v019_proof_fallback.pt"


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve_checkpoint(role: str) -> dict:
    """
    Resolve the best available checkpoint for a role using priority order:

    1. *_v055_finetuned.pt  (fine-tuned weights)
    2. *_v054_specialized.pt  (base copy)
    3. checkpoints/base/creature_v032_bigfit_twenty_plain.pt
    4. checkpoints/base/creature_v019_proof_fallback.pt
    """
    slot_dir = root() / "checkpoints" / "brain_slots" / role

    candidates = [
        ("v055_finetuned", slot_dir / f"{role}_v055_finetuned.pt"),
        ("v054_specialized", slot_dir / f"{role}_v054_specialized.pt"),
        ("v032_base", root() / "checkpoints" / "base" / BASE_CHECKPOINT_NAME),
        ("v019_fallback", root() / "checkpoints" / "base" / FALLBACK_CHECKPOINT_NAME),
    ]

    for version_name, path in candidates:
        if path.exists() and path.stat().st_size > 200:
            file_hash = sha256(path)
            return {
                "role": role,
                "selected_checkpoint": str(path.relative_to(root())),
                "checkpoint_version": version_name,
                "exists": True,
                "size_bytes": path.stat().st_size,
                "sha256": file_hash,
                "fallback_used": version_name in ("v032_base", "v019_fallback"),
                "promote_ready": version_name == "v055_finetuned",
            }

    # No checkpoint found at all
    return {
        "role": role,
        "selected_checkpoint": None,
        "checkpoint_version": "none",
        "exists": False,
        "size_bytes": 0,
        "sha256": None,
        "fallback_used": True,
        "promote_ready": False,
    }


def resolve_all() -> list[dict]:
    return [resolve_checkpoint(r) for r in ROLES]


def build_priority_report() -> dict:
    results = resolve_all()
    all_promoted = all(r["promote_ready"] for r in results)
    any_fallback = any(r["fallback_used"] for r in results)

    report = {
        "version": "codex_cloud_v059_checkpoint_resolver",
        "created_at": datetime.now().isoformat(),
        "project_root": str(root()),
        "roles": results,
        "all_promoted_to_v055": all_promoted,
        "any_fallback_active": any_fallback,
        "summary": (
            "All roles promoted to v055 fine-tuned checkpoints"
            if all_promoted
            else "Some roles still using fallback — run v055 fine-tune"
        ),
    }

    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v059_live_router_checkpoint_priority.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def print_report(report: dict | None = None):
    if report is None:
        report = build_priority_report()
    print("Nova Creature v059 — Checkpoint Priority Resolver")
    print(f"Project root: {report['project_root']}")
    print()
    for r in report["roles"]:
        version = r["checkpoint_version"]
        label = {
            "v055_finetuned": "v055 ✅",
            "v054_specialized": "v054",
            "v032_base": "v032 base",
            "v019_fallback": "v019 fallback",
            "none": "NONE",
        }.get(version, version)
        print(f"  {r['role']:40s} → {label}")
        if r["selected_checkpoint"]:
            print(f"  {'':40s}   {r['selected_checkpoint']}")
            print(f"  {'':40s}   {r['sha256'][:16]}... ({r['size_bytes']} bytes)")
    print()
    print(f"All promoted to v055: {report['all_promoted_to_v055']}")
    print(f"Any fallback active:  {report['any_fallback_active']}")
    print(f"Summary: {report['summary']}")


def main() -> int:
    report = build_priority_report()
    print_report(report)
    return 0 if report["all_promoted_to_v055"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
