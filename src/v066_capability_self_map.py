from __future__ import annotations

import json, hashlib, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]

BRAIN_PURPOSE = {
    "left_hemisphere": "math, code, logic, exact tests",
    "right_hemisphere": "patterns, imagination, visual maps, creative synthesis",
    "memory_transformer": "identity, facts, names, recall",
    "planner_transformer": "steps, next actions, build sequence",
    "critic_conscience_transformer": "truth check, unknown guard, don't guess",
    "dream_simulation_transformer": "practice scenarios, variants, replay",
    "speech_output_transformer": "clean final answer style",
}


def root() -> Path:
    return ROOT


def sha256(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size < 100:
        return None
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def _check_import(module_name: str) -> bool:
    try:
        __import__(module_name, fromlist=["dummy"])
        return True
    except Exception:
        return False


def _check_file(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def _count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for l in path.read_text().splitlines() if l.strip())


def build_brain_organs() -> dict[str, Any]:
    organs = {}
    for role in ROLES:
        slot_dir = root() / "checkpoints" / "brain_slots" / role
        dir_exists = slot_dir.exists()

        # Checkpoint priority resolution
        ckpt_path = None
        ckpt_version = None
        ckpt_hash = None

        for ver, name in [
            ("v055_finetuned", f"{role}_v055_finetuned.pt"),
            ("v054_specialized", f"{role}_v054_specialized.pt"),
        ]:
            p = slot_dir / name
            if p.exists() and p.stat().st_size > 200:
                ckpt_path = str(p.relative_to(root()))
                ckpt_version = ver
                ckpt_hash = sha256(p)
                break

        organs[role] = {
            "exists": dir_exists,
            "active": ckpt_version is not None,
            "selected_checkpoint": ckpt_path,
            "checkpoint_version": ckpt_version or "none",
            "sha256": ckpt_hash[:16] + "..." if ckpt_hash else None,
            "purpose": BRAIN_PURPOSE.get(role, ""),
            "fallback_used": ckpt_version not in ("v055_finetuned", "v054_specialized") if ckpt_version else True,
        }
    return organs


def build_memory_systems() -> dict[str, Any]:
    smart_mem_dir = root() / "data" / "smart_memory"
    systems = {
        "conversation_memory": {
            "exists": (root() / "data" / "conversation_memory").exists(),
            "storage_path": "data/conversation_memory/",
            "item_count": sum(
                _count_jsonl(p) for p in (root() / "data" / "conversation_memory").glob("*_turns.jsonl")
            ) if (root() / "data" / "conversation_memory").exists() else 0,
            "trainable": False,
            "requires_approval": False,
        },
        "dictionary_memory": {
            "exists": (root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json").exists(),
            "storage_path": "data/dictionary_memory/approved_answer_dictionary.json",
            "item_count": len(json.loads((root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json").read_text())) if (root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json").exists() else 0,
            "trainable": True,
            "requires_approval": False,
        },
    }

    for mt in ["auto_project_memory", "explicit_user_memory", "temporary_conversation_context",
               "pending_approval_memory", "training_candidate_memory"]:
        p = smart_mem_dir / f"{mt}.jsonl"
        systems[mt] = {
            "exists": p.exists(),
            "storage_path": f"data/smart_memory/{mt}.jsonl",
            "item_count": _count_jsonl(p),
            "trainable": mt in ("explicit_user_memory", "training_candidate_memory"),
            "requires_approval": mt == "pending_approval_memory",
        }

    # v064 constitution check
    if _check_file(root() / "src" / "v064_memory_constitution.py"):
        try:
            from v064_memory_constitution import auto_approve, requires_approval, can_train
            for mt in systems:
                if mt in ("auto_project_memory", "explicit_user_memory", "training_candidate_memory"):
                    systems[mt]["trainable"] = can_train(mt)
                if mt == "pending_approval_memory":
                    systems[mt]["requires_approval"] = requires_approval(mt)
        except Exception:
            pass

    return systems


def build_learning_systems() -> dict[str, Any]:
    systems = {}

    # v058 dictionary-to-training
    v058_path = root() / "scripts" / "v058_export_dictionary_to_training.py"
    systems["v058_dictionary_to_training"] = {
        "exists": v058_path.exists(),
        "active": v058_path.exists(),
        "last_report": "reports/v058_dictionary_training/" if (root() / "exports" / "v058_dictionary_training").exists() else None,
    }

    # v060 smart memory capture
    v060_path = root() / "src" / "v060_smart_memory_capture.py"
    systems["v060_smart_memory_capture"] = {
        "exists": v060_path.exists(),
        "active": v060_path.exists(),
    }

    # v061 learning loop
    v061_path = root() / "src" / "v061_learning_loop_manager.py"
    v061_status = root() / "reports" / "v061_learning_loop_status.json"
    v061_last = None
    if v061_status.exists():
        try:
            v061_last = json.loads(v061_status.read_text()).get("final_status")
        except Exception:
            pass
    systems["v061_learning_loop"] = {
        "exists": v061_path.exists(),
        "active": v061_path.exists() and v061_last is not None,
        "last_report": "reports/v061_learning_loop_status.json",
        "last_status": v061_last or "unknown",
    }

    # v055 fine-tune runner
    ft_path = root() / "scripts" / "v055_finetune_role_brains.py"
    ft_report = root() / "reports" / "v055_finetune_summary.json"
    ft_last = None
    if ft_report.exists():
        try:
            ft_last = json.loads(ft_report.read_text()).get("can_promote")
        except Exception:
            pass
    systems["v055_finetune_runner"] = {
        "exists": ft_path.exists(),
        "active": ft_path.exists(),
        "last_report": "reports/v055_finetune_summary.json",
        "last_can_promote": ft_last,
    }

    # v059 live router promotion
    gck_path = root() / "scripts" / "check_v059_router_uses_finetuned_brains.py"
    gck_report = root() / "reports" / "v059_live_router_checkpoint_priority.json"
    gck_last = None
    if gck_report.exists():
        try:
            gck_last = json.loads(gck_report.read_text()).get("all_promoted_to_v055")
        except Exception:
            pass
    systems["v059_router_promotion"] = {
        "exists": gck_path.exists(),
        "active": gck_path.exists(),
        "last_report": "reports/v059_live_router_checkpoint_priority.json",
        "all_promoted_to_v055": gck_last,
    }

    # v062 benchmark gate
    bm_path = root() / "src" / "v062_benchmark_gate.py"
    bm_report = root() / "reports" / "v062_benchmark_report.json"
    bm_last = None
    if bm_report.exists():
        try:
            bm_last = json.loads(bm_report.read_text()).get("gate_passed")
        except Exception:
            pass
    systems["v062_benchmark_gate"] = {
        "exists": bm_path.exists(),
        "active": bm_path.exists(),
        "last_report": "reports/v062_benchmark_report.json",
        "last_gate_passed": bm_last,
    }

    # v063 dream replay
    dr_path = root() / "src" / "v063_dream_replay.py"
    systems["v063_dream_replay"] = {
        "exists": dr_path.exists(),
        "active": dr_path.exists(),
    }

    # v064 constitution
    co_path = root() / "src" / "v064_memory_constitution.py"
    systems["v064_memory_constitution"] = {
        "exists": co_path.exists(),
        "active": co_path.exists(),
    }

    return systems


def build_tool_systems() -> dict[str, Any]:
    tools = {}
    script_dir = root() / "scripts"
    src_dir = root() / "src"
    check_scripts = [
        "check_codex_brain_stack.py",
        "check_v059_router_uses_finetuned_brains.py",
        "check_v060_smart_memory_capture.py",
        "check_v061_learning_loop.py",
        "check_v062_benchmark_gate.py",
    ]
    for name in check_scripts:
        p = script_dir / name
        tools[name] = {"exists": p.exists(), "type": "checker"}

    for name in ["v053_training_prep.py", "v054_role_checkpoint_builder.py",
                  "v055_cloud_finetune_ready.py", "v055_finetune_role_brains.py",
                  "v058_export_dictionary_to_training.py", "v061_run_learning_loop.py"]:
        p = script_dir / name
        tools[name] = {"exists": p.exists(), "type": "pipeline"}

    return tools


def build_robot_systems() -> dict[str, Any]:
    return {
        "robot_bridge": {"status": "planned", "active": False, "simulation_only": True},
        "movement_controller": {"status": "inactive", "active": False, "simulation_only": True},
        "vision_sensor": {"status": "not_connected", "active": False, "note": "No camera hardware connected"},
        "microphone_sensor": {"status": "not_connected", "active": False, "note": "No microphone hardware connected"},
        "speaker_output": {"status": "not_connected", "active": False, "note": "No speaker hardware connected"},
        "lidar_or_distance_sensor": {"status": "not_installed", "active": False, "note": "Requires physical sensor"},
        "battery_monitor": {"status": "not_installed", "active": False, "note": "Requires power management hardware"},
        "imu_balance_sensor": {"status": "not_installed", "active": False, "note": "Requires IMU hardware"},
        "emergency_stop": {"status": "required", "active": False, "note": "Must be installed before any real movement"},
        "safety_spine": {"status": "required", "active": False, "note": "v071 safety spine must pass before real movement"},
        "simulation_world": {"status": "required", "active": False, "note": "Simulation world needed before real movement"},
        "real_hardware_enabled": {"status": "disabled", "active": False, "note": "Cannot enable without safety spine, emergency stop, and hardware config"},
    }


def build_capability_self_map() -> dict[str, Any]:
    brain = build_brain_organs()
    memory = build_memory_systems()
    learning = build_learning_systems()
    tools = build_tool_systems()
    robot = build_robot_systems()

    active = []
    inactive = []
    missing = []
    approval_required = []
    benchmark_required = []

    for role, info in brain.items():
        if info["active"]:
            active.append(f"brain_organ:{role}")
        else:
            inactive.append(f"brain_organ:{role}")

    for sys_name, info in memory.items():
        if info.get("exists"):
            active.append(f"memory:{sys_name}")
        else:
            missing.append(f"memory:{sys_name}")
        if info.get("requires_approval"):
            approval_required.append(f"memory:{sys_name}")

    for sys_name, info in learning.items():
        if info.get("active"):
            active.append(f"learning:{sys_name}")
        elif info.get("exists"):
            inactive.append(f"learning:{sys_name}")
        else:
            missing.append(f"learning:{sys_name}")

    for tool_name, info in tools.items():
        if info.get("exists"):
            active.append(f"tool:{tool_name}")
        else:
            missing.append(f"tool:{tool_name}")

    for sys_name, info in robot.items():
        if info.get("active"):
            active.append(f"robot:{sys_name}")
        elif info.get("status") in ("required", "planned"):
            inactive.append(f"robot:{sys_name}")
        else:
            missing.append(f"robot:{sys_name}")

    benchmark_required.append("robot:movement_controller")

    self_map = {
        "version": "v066_capability_self_map",
        "created_at": datetime.now().isoformat(),
        "project_root": str(root()),
        "brain_organs": brain,
        "memory_systems": memory,
        "learning_systems": learning,
        "tool_systems": tools,
        "robot_systems": robot,
        "active_capabilities": sorted(active),
        "inactive_capabilities": sorted(inactive),
        "missing_capabilities": sorted(missing),
        "approval_required_capabilities": sorted(approval_required),
        "benchmark_required_capabilities": sorted(benchmark_required),
        "safety_limits": [
            "Real robot movement is disabled by default",
            "v064 memory constitution blocks uncertain/personal memory from training",
            "v062 benchmark gate must pass before any promotion",
            "v071 safety spine must pass before real robot movement",
        ],
        "real_hardware_enabled": False,
        "next_safe_upgrade": "v069 — Self-Scripting Brain (write/test scripts in sandbox)",
    }

    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v066_capability_self_map_status.json").write_text(json.dumps(self_map, indent=2))
    return self_map


def main() -> int:
    self_map = build_capability_self_map()
    print("Nova Creature v066 — Capability Self-Map\n")
    print(f"Brain organs: {sum(1 for v in self_map['brain_organs'].values() if v['active'])}/{len(self_map['brain_organs'])} active")
    print(f"Memory systems: {sum(1 for v in self_map['memory_systems'].values() if v['exists'])}/{len(self_map['memory_systems'])}")
    print(f"Learning systems: {sum(1 for v in self_map['learning_systems'].values() if v['active'])}/{len(self_map['learning_systems'])} active")
    print(f"Robot systems: {sum(1 for v in self_map['robot_systems'].values() if v['active'])}/{len(self_map['robot_systems'])} active")
    print(f"Active capabilities: {len(self_map['active_capabilities'])}")
    print(f"Inactive capabilities: {len(self_map['inactive_capabilities'])}")
    print(f"Missing capabilities: {len(self_map['missing_capabilities'])}")
    print(f"Real hardware enabled: {self_map['real_hardware_enabled']}")
    print(f"\nReport: reports/v066_capability_self_map_status.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
