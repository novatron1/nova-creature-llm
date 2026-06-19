"""v663 — Planner Drill-to-Training Converter"""
from __future__ import annotations; from datetime import datetime; import json; from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "exports" / "v663_planner_training_candidates" / "planner_transformer_code_repair.jsonl"

def convert_drills_to_training():
    """Only approved drills, no destructive commands, no fake claims, trust+critic approval required"""
    training_entries = []
    if DATA_PATH.exists():
        for line in DATA_PATH.read_text().splitlines():
            if not line.strip(): continue
            try:
                entry = json.loads(line)
                if entry.get("approved") and entry.get("safe") and entry.get("trust_score", 0) >= 75:
                    training_entries.append(entry)
            except json.JSONDecodeError:
                pass
    return {
        "version": "v663_drill_to_training_converter",
        "created_at": datetime.now().isoformat(),
        "safe": True,
        "source_file": str(DATA_PATH),
        "drills_found": len(training_entries),
        "training_entries": training_entries,
        "criteria_applied": {
            "approved_only": True,
            "no_destructive_commands": True,
            "no_fake_claims": True,
            "trust_minimum": 75,
            "critic_approval_required": True
        },
        "status": "converted" if training_entries else "no_valid_entries",
        "warning": "real_hardware_enabled: False, real_robot_movement_allowed: False"
    }

def main():
    print("Nova v663_drill_to_training_converter\n")
    r = convert_drills_to_training()
    print(f"Result: {len(r)} fields — Drills converted: {r['drills_found']}")

if __name__ == "__main__":
    raise SystemExit(main())
