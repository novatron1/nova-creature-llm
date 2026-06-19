"""v182 — Targeted Role Training Exporter."""
from __future__ import annotations
from datetime import datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports" / "v182_targeted_role_training_sets"
ROLES = ["planner_transformer","memory_transformer","critic_conscience_transformer",
         "dream_simulation_transformer","left_hemisphere","right_hemisphere","speech_output_transformer"]

def _ensure():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        (EXPORT_DIR / f"{role}.jsonl").touch()

def export_targeted_training():
    _ensure()
    # Load approved batch
    batch_file = ROOT / "data" / "intelligence_age_cycle" / "approved_training_batch.jsonl"
    items = []
    if batch_file.exists():
        with open(batch_file) as f:
            items = [json.loads(l) for l in f if l.strip()]

    totals = {}
    for role in ROLES:
        role_items = [i for i in items if i.get("target_brain_role") == role]
        with open(EXPORT_DIR / f"{role}.jsonl","w") as f:
            for item in role_items:
                entry = {"prompt":item.get("question",""),"completion":item.get("expected_answer",""),
                         "role":role,"skill_target":item.get("skill_target",""),
                         "source_system":item.get("source_system","age_cycle"),
                         "difficulty":item.get("difficulty","medium"),
                         "benchmark_category":item.get("benchmark_category",""),
                         "approval_status":item.get("approval_status","approved")}
                f.write(json.dumps(entry)+"\n")
        totals[role] = len(role_items)

    # Unassigned items go to left_hemisphere default
    assigned_ids = set()
    for role in ROLES:
        if (EXPORT_DIR / f"{role}.jsonl").exists():
            with open(EXPORT_DIR / f"{role}.jsonl") as f:
                assigned_ids.update(json.loads(l)["prompt"] for l in f if l.strip())

    return {"version":"v182_targeted_role_exporter","created_at":datetime.now().isoformat(),
            "role_counts":totals,"total_exported":sum(totals.values()),
            "roles_exported":ROLES}

def main():
    print("Nova v182 -- Targeted Role Training Exporter\n")
    r = export_targeted_training()
    for role, count in r["role_counts"].items():
        if count > 0: print(f"  {role}: {count} items")
    print(f"Total: {r['total_exported']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
