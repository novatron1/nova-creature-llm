"""v085 — Full System Health Report. One master report of Nova's system state."""
from __future__ import annotations
import json, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

def build_full_health() -> dict[str, Any]:
    report = {"version": "v085_full_system_health", "created_at": datetime.now().isoformat()}

    # Brain organs
    organ_names = ["left_hemisphere", "right_hemisphere", "memory_transformer", "planner_transformer",
                   "critic_conscience_transformer", "dream_simulation_transformer", "speech_output_transformer"]
    organs = {}
    for role in organ_names:
        slot_dir = ROOT / "checkpoints" / "brain_slots" / role
        ckpt_found = None
        for ver in ("v055_finetuned", "v054_specialized"):
            p = slot_dir / f"{role}_{ver}.pt"
            if p.exists() and p.stat().st_size > 200:
                ckpt_found = ver
                break
        organs[role] = {"exists": slot_dir.exists(), "active": ckpt_found is not None,
                        "checkpoint_version": ckpt_found or "none"}
    report["brain_organs"] = organs

    # Memory systems
    mem_systems = {}
    for mt in ["conversation_memory", "dictionary_memory", "auto_project_memory", "explicit_user_memory",
               "temporary_conversation_context", "pending_approval_memory", "training_candidate_memory"]:
        p = ROOT / "data" / "smart_memory" / f"{mt}.jsonl" if "memory" in mt and mt != "dictionary_memory" and mt != "conversation_memory" else ROOT / "data" / (mt if mt == "dictionary_memory" else "smart_memory") / f"{mt}.jsonl"
        if mt == "dictionary_memory":
            p = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
        elif mt == "conversation_memory":
            p = ROOT / "data" / "conversation_memory"
        mem_systems[mt] = {"exists": p.exists() if not p.is_dir() else p.is_dir()}
    report["memory_systems"] = mem_systems

    # Key reports
    report["key_reports"] = {}
    for rp in ["v062_benchmark_report.json", "v066_capability_self_map_status.json",
               "v075_benchmark_dashboard_status.json", "v095_intelligence_benchmark_status.json"]:
        rp_path = ROOT / "reports" / rp
        report["key_reports"][rp] = {"exists": rp_path.exists()}

    # Robot status
    report["robot_status"] = {"simulation_only": True, "real_hardware_enabled": False,
                              "deployment_ready": False, "physical_movement_blocked": True}

    # Missing capabilities
    report["missing_capabilities"] = ["real_robot_movement", "vision_system", "voice_input",
                                      "local_sync_access", "scheduled_autonomy", "physical_sensors"]

    # Next safe upgrade
    report["next_safe_upgrade"] = "v086-v095 Intelligence Stack (reasoning, planning, evidence, self-correction, benchmarks)"
    return report

def main():
    print("Nova v085 -- Full System Health\n")
    r = build_full_health()
    organs_active = sum(1 for o in r["brain_organs"].values() if o["active"])
    print(f"Brain organs active: {organs_active}/7")
    print(f"Memory systems: {sum(1 for m in r['memory_systems'].values() if m['exists'])}")
    print(f"Robot: sim={r['robot_status']['simulation_only']}, hw={r['robot_status']['real_hardware_enabled']}")
    print(f"Missing: {len(r['missing_capabilities'])} capabilities")
    print(f"Next: {r['next_safe_upgrade'][:60]}...")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
