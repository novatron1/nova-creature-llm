"""v818_system_health_checker — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def system_health_checker():
    """Verify all required system components exist."""
    checks = {}
    required_dirs = ["src", "scripts", "reports", "data", "checkpoints/brain_slots", "training_data/role_brains"]
    for d in required_dirs:
        checks[f"dir_{d.replace('/','_')}"] = (ROOT / d).exists()
    required_reports = ["v700_gold.json", "v750_sensory_body_readiness_report.json", "v775_natural_people_memory_report.json", "v800_rapid_learning_final_report.json"]
    for rpt in required_reports:
        checks[f"report_{rpt.split('.')[0]}"] = (ROOT / "reports" / rpt).exists()
    required_src_modules = ["v052_role_brain_router.py", "v701_device_scanner.py", "v751_people_memory_database.py", "v776_learning_intake.py"]
    for mod in required_src_modules:
        checks[f"src_{mod.split('.')[0]}"] = (ROOT / "src" / mod).exists()
    all_ok = all(checks.values())
    return {"version": "v818_system_health_checker", "created_at": datetime.now().isoformat(),
            "checks": checks, "all_healthy": all_ok, "status": "ok" if all_ok else "degraded"}


def main():
    print(f"Nova v818_system_health_checker")
    r = system_health_checker()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
