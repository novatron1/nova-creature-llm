from __future__ import annotations

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


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def check_torch() -> dict:
    info = {"installed": False, "version": None, "cuda_available": False, "error": None}
    try:
        import torch

        info["installed"] = True
        info["version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
    except Exception as e:
        info["error"] = repr(e)
    return info


def check_checkpoints(r: Path) -> dict:
    base_pt = r / "checkpoints" / "base" / BASE_CHECKPOINT_NAME
    exp_pt = r / "checkpoints" / "experimental" / BASE_CHECKPOINT_NAME
    any_pts = list((r / "checkpoints").glob("**/*.pt")) if (r / "checkpoints").exists() else []
    any_pts = [p for p in any_pts if "v054" not in p.name and "v055" not in p.name]

    slot_files = {}
    for role in ROLES:
        f = r / "checkpoints" / "brain_slots" / role / f"{role}_v054_specialized.pt"
        slot_files[role] = {
            "exists": f.exists(),
            "is_placeholder": f.exists() and f.stat().st_size < 200,
        }

    return {
        "base_checkpoint": {
            "exists": base_pt.exists(),
            "path": f"checkpoints/base/{BASE_CHECKPOINT_NAME}",
            "size_bytes": base_pt.stat().st_size if base_pt.exists() else 0,
        },
        "experimental_checkpoint": {
            "exists": exp_pt.exists(),
            "path": f"checkpoints/experimental/{BASE_CHECKPOINT_NAME}",
            "size_bytes": exp_pt.stat().st_size if exp_pt.exists() else 0,
        },
        "other_pt_count": len(any_pts),
        "other_pt_paths": [str(p.relative_to(r)) for p in any_pts[:5]],
        "role_slot_files": slot_files,
    }


def check_training_sets(r: Path) -> dict:
    info = {}
    total = 0
    for role in ROLES:
        f = r / "exports" / "v053_training_sets" / f"{role}_training_set.json"
        lessons = []
        if f.exists():
            try:
                lessons = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        info[role] = {"exists": f.exists(), "lesson_count": len(lessons)}
        total += len(lessons)
    info["total_lessons"] = total
    info["all_roles_have_data"] = all(info[r]["lesson_count"] > 0 for r in ROLES)
    return info


def check_brain_slots(r: Path) -> dict:
    info = {}
    for role in ROLES:
        d = r / "checkpoints" / "brain_slots" / role
        config = d / "brain_slot_config.json"
        manifest = d / "v054_role_checkpoint_manifest.json"
        info[role] = {
            "dir_exists": d.exists(),
            "config_exists": config.exists(),
            "manifest_exists": manifest.exists(),
            "checkpoint_file": f"{role}_v054_specialized.pt",
        }
    return info


def can_run_finetune(torch_info: dict, ckpt_info: dict, training_info: dict) -> dict:
    torch_ok = torch_info["installed"]
    has_real_ckpt = ckpt_info["base_checkpoint"]["exists"] or ckpt_info["experimental_checkpoint"]["exists"] or ckpt_info["other_pt_count"] > 0
    has_training_data = training_info["all_roles_have_data"]

    blockers = []
    if not torch_ok:
        blockers.append("torch_not_installed")
    if not has_real_ckpt:
        blockers.append("no_real_base_checkpoint")
    if not has_training_data:
        blockers.append("no_training_data")

    return {
        "can_finetune": len(blockers) == 0,
        "torch_ready": torch_ok,
        "checkpoint_ready": has_real_ckpt,
        "training_data_ready": has_training_data,
        "blockers": blockers,
        "summary": "Ready for gradient fine-tuning" if len(blockers) == 0 else f"Blocked by: {', '.join(blockers)}",
    }


def main() -> int:
    r = root()
    reports = r / "reports"
    reports.mkdir(exist_ok=True)

    torch_info = check_torch()
    ckpt_info = check_checkpoints(r)
    training_info = check_training_sets(r)
    slots_info = check_brain_slots(r)
    readiness = can_run_finetune(torch_info, ckpt_info, training_info)

    report = {
        "version": "codex_cloud_v055",
        "created_at": datetime.now().isoformat(),
        "project_root": str(r),
        "torch": torch_info,
        "checkpoints": ckpt_info,
        "training_sets": training_info,
        "brain_slots": slots_info,
        "readiness": readiness,
        "architecture_versions": {
            "v049_brain_slots": True,
            "v050_v052_role_router": True,
            "v051_chat_adapter": True,
            "v053_training_prep": True,
            "v054_role_checkpoint_builder": True,
            "v055_finetune_readiness": True,
        },
    }

    # Write the cloud v055 status report
    (reports / "cloud_v055_checkpoint_and_torch_status.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )

    # Also update the legacy report
    if torch_info["installed"]:
        (reports / "codex_v055_torch_ready.json").write_text(
            json.dumps(
                {
                    "version": "codex_cloud_v055",
                    "created_at": datetime.now().isoformat(),
                    "torch_version": torch_info["version"],
                    "cuda_available": torch_info["cuda_available"],
                    "status": "torch_available_ready_for_project_specific_finetune",
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    print("=== Nova Creature Cloud v055 Status ===")
    print(f"Project root: {r}")
    print()

    if torch_info["installed"]:
        print(f"Torch: {torch_info['version']} (CUDA: {torch_info['cuda_available']})")
    else:
        print(f"Torch: NOT INSTALLED ({torch_info['error']})")

    if ckpt_info["base_checkpoint"]["exists"]:
        print(f"Base checkpoint: FOUND ({ckpt_info['base_checkpoint']['size_bytes']} bytes)")
    elif ckpt_info["experimental_checkpoint"]["exists"]:
        print(f"Experimental checkpoint: FOUND ({ckpt_info['experimental_checkpoint']['size_bytes']} bytes)")
    elif ckpt_info["other_pt_count"] > 0:
        print(f"Other checkpoint: FOUND ({ckpt_info['other_pt_count']} files)")
    else:
        print("Base checkpoint: NOT FOUND (placeholders active)")

    print(f"Training sets: {training_info['total_lessons']} lessons across {len(ROLES)} roles")
    print(f"Brain slots: {sum(1 for v in slots_info.values() if v['dir_exists'])}/{len(ROLES)} present")
    print()
    print(f"Fine-tune readiness: {readiness['summary']}")
    print(f"Report saved: {reports / 'cloud_v055_checkpoint_and_torch_status.json'}")

    if readiness["can_finetune"]:
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
