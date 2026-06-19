"""v912_regression_guard — Whole-Brain Training Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def regression_guard():
    """Check no training broke existing systems."""
    checks = {}
    for label, mod, func in [
        ("v700_core", "v700_real_intelligence_growth_final_report", "generate_real_intelligence_growth_final_report"),
        ("v750_sensory", "v750_readiness_report", "readiness_report"),
        ("v775_people", "v775_people_memory_report", "people_memory_report"),
        ("v800_rapid_learning", "v800_rapid_learning_final_report", "rapid_learning_final_report"),
        ("v825_integration", "v825_final_integration_readiness_report", "final_integration_readiness_report"),
        ("v900_coding_master", "v900_coding_master_final_report", "coding_master_final_report"),
    ]:
        try:
            exec(f"from {mod} import {func}")
            r = eval(f"{func}()")
            checks[label] = r.get("growth_proven", r.get("all_checks_passed", False)) if "all_checks_passed" in r or "growth_proven" in r else r.get("status") == "ok"
        except: checks[label] = False
    all_pass = all(v for v in checks.values())
    return {"version": "v912_regression_guard", "created_at": datetime.now().isoformat(),
            "checks": checks, "all_intact": all_pass, "status": "ok" if all_pass else "regression_detected"}

def main():
    print(f"Nova v912_regression_guard")
    r = regression_guard()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
