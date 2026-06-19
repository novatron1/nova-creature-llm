"""v079 — Local/Cloud Sync Plan. Tracks drift prevention between cloud and local Nova."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CLOUD_STACK = [
    "v056", "v057", "v058", "v059", "v060", "v061", "v062", "v063", "v064",
    "v065", "v066", "v069", "v070", "v071", "v072", "v073", "v074", "v075",
    "v076", "v077", "v078", "v080",
]

NEVER_SYNC = [
    "checkpoints/base/creature_v032_bigfit_twenty_plain.pt",
    "checkpoints/base/creature_v019_proof_fallback.pt",
    "checkpoints/brain_slots/*/*_v054_specialized.pt",
    "checkpoints/brain_slots/*/*_v055_finetuned.pt",
    "data/owner_approval/",
    "backups/",
    ".git/",
    "__pycache__/",
    "*.pyc",
]

APPROVAL_REQUIRED_BEFORE_SYNC = [
    "checkpoints/",
    "data/smart_memory/",
    "data/dictionary_memory/",
    "data/training_data/",
    "data/mistake_memory/",
]


def build_sync_plan() -> dict[str, Any]:
    return {
        "version": "v079_local_cloud_sync_plan",
        "created_at": datetime.now().isoformat(),
        "cloud_version_stack": CLOUD_STACK,
        "latest_confirmed_cloud_version": "v080",
        "local_version_stack": "unknown (no local access)",
        "checkpoint_names": [
            "checkpoints/base/creature_v032_bigfit_twenty_plain.pt",
            "checkpoints/base/creature_v019_proof_fallback.pt",
        ],
        "brain_slot_checkpoints": [
            "left_hemisphere_v055_finetuned.pt",
            "right_hemisphere_v055_finetuned.pt",
            "memory_transformer_v055_finetuned.pt",
            "planner_transformer_v055_finetuned.pt",
            "critic_conscience_transformer_v055_finetuned.pt",
            "dream_simulation_transformer_v055_finetuned.pt",
            "speech_output_transformer_v055_finetuned.pt",
        ],
        "memory_pack_names": [
            "data/smart_memory/",
            "data/dictionary_memory/approved_answer_dictionary.json",
            "data/conversation_memory/",
            "data/mistake_memory/",
            "data/growth_streams/",
        ],
        "training_export_names": [
            "exports/v053_training_sets/",
        ],
        "patch_history": [
            "v056 conversation memory loop",
            "v057 dictionary memory bridge",
            "v058 dictionary to transformer learning",
            "v059 live router promoted to v055",
            "v060 smart memory capture",
            "v061 smart memory to training loop",
            "v062 growth engine + benchmark gate",
            "v063 inner voice + dream replay",
            "v064 memory law / approval constitution",
            "v065 skill hands + self-test nervous system",
            "v066 capability self-map",
            "v069 self-scripting brain",
            "v070 robot command bridge sim-only",
            "v071 robot safety spine",
            "v072 body sensor registry",
            "v073 robot deployment gate",
            "v074 mistake memory/error bank",
            "v075 benchmark dashboard",
            "v076 auto patch repair loop",
            "v077 dream training generator 2.0",
            "v078 voice/short conversation mode",
            "v080 app builder mode",
        ],
        "reports_that_need_copying": [
            "reports/v059_live_router_checkpoint_priority.json",
            "reports/v062_benchmark_report.json",
            "reports/v066_capability_self_map_status.json",
            "reports/v075_benchmark_dashboard_status.json",
            "reports/v095_intelligence_benchmark_status.json",
        ],
        "never_sync": NEVER_SYNC,
        "approval_required_before_sync": APPROVAL_REQUIRED_BEFORE_SYNC,
        "sync_rules": [
            "Do not assume access to local laptop.",
            "Do not use Windows paths.",
            "Create a sync plan only — do not move or delete files.",
            "Report what would need to be exported for local use.",
        ],
        "status": "sync_plan_only_no_local_access",
        "local_laptop_access": False,
    }


def main() -> int:
    print("Nova v079 -- Local/Cloud Sync Plan\n")
    p = build_sync_plan()
    print(f"Cloud stack: {len(p['cloud_version_stack'])} versions")
    print(f"Checkpoints: {len(p['checkpoint_names']) + len(p['brain_slot_checkpoints'])}")
    print(f"Never sync: {len(p['never_sync'])} patterns")
    print(f"Approval required: {len(p['approval_required_before_sync'])} categories")
    print(f"Local laptop access: {p['local_laptop_access']}")
    print(f"Status: {p['status']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
