from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from nova_checkpoint_registry import CheckpointRegistry
from nova_training_types import ROLE_NAMES

ROLES = list(ROLE_NAMES)


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def resolve_checkpoint(role: str) -> dict:
    """
    Resolve the registry-controlled live checkpoint for a role.
    """
    try:
        registry = CheckpointRegistry(root())
        resolved = registry.resolve_live(role)
    except (LookupError, FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as exc:
        return _missing_checkpoint_result(role, str(exc))

    exists = resolved.path.exists()
    try:
        selected_checkpoint = resolved.path.relative_to(root()).as_posix()
    except ValueError:
        selected_checkpoint = resolved.path.as_posix()
    return {
        "role": role,
        "selected_checkpoint": selected_checkpoint,
        "checkpoint_version": resolved.status,
        "exists": exists,
        "size_bytes": resolved.path.stat().st_size if exists else 0,
        "sha256": resolved.sha256,
        "fallback_used": resolved.status == "baseline",
        "promote_ready": resolved.status == "promoted",
    }


def _missing_checkpoint_result(role: str, error: str | None = None) -> dict:
    return {
        "role": role,
        "selected_checkpoint": None,
        "checkpoint_version": "none",
        "exists": False,
        "size_bytes": 0,
        "sha256": None,
        "fallback_used": True,
        "promote_ready": False,
        "error": error or "checkpoint is missing",
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
