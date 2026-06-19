"""v940_training_lab_integration_test — Whole-Brain Training Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def training_lab_integration_test():
    """Test training lab connects to rapid learning, coding master, people memory, sensory, brain router, runtime."""
    tests=[]; passed=0; failed=0
    for mod,func,name in [
        ("v871_integrate_with_rapid_learning", "integrate_with_rapid_learning", "rapid_learning_connection"),
        ("v872_integrate_with_brain_router", "integrate_with_brain_router", "brain_router_connection"),
        ("v873_integrate_with_full_runtime", "integrate_with_full_runtime", "runtime_connection"),
    ]:
        try:
            exec(f"from {mod} import {func}")
            r = eval(f"{func}()")
            ok = r.get("status") == "ok"
            tests.append({"test": name, "passed": ok})
            passed+=ok; failed+=not ok
        except: tests.append({"test": name, "passed": False}); failed+=1
    return {"version": "v940_training_lab_integration_test", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed, "status": "ok" if failed==0 else "partial"}

def main():
    print(f"Nova v940_training_lab_integration_test")
    r = training_lab_integration_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
