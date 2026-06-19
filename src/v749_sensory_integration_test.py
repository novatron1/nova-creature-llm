"""749 — Sensory Body Layer: Sensory Integration Test"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def sensory_integration_test():
    """Integration test for the full sensory body system."""
    tests = []
    passed = 0
    failed = 0

    # Test full pipeline: device -> permission -> event -> memory -> route
    try:
        from v701_device_scanner import device_scanner
        from v704_permission_gate import permission_gate, check_permission
        from v706_sensory_event import sensory_event
        from v707_sensory_memory import sensory_memory
        from v708_multimodal_router import multimodal_router
        devices = device_scanner()
        permission_gate("camera", True)
        perm_ok = check_permission("camera")
        ev = sensory_event("camera", "face_detected", "integration test", 0.9, "right_hemisphere", "granted" if perm_ok else "denied")
        mem = sensory_memory(ev)
        route = multimodal_router("camera", "face")
        pipeline_ok = devices.get("status") == "ok" and perm_ok and mem.get("status") == "ok" and "right_hemisphere" in route.get("routes", [])
        tests.append({"test": "full_sensory_pipeline", "passed": pipeline_ok, "detail": "camera->permission->event->memory->route"})
        passed += pipeline_ok; failed += not pipeline_ok
    except Exception as e:
        tests.append({"test": "full_sensory_pipeline", "passed": False, "detail": str(e)}); failed += 1

    # Dashboard integration
    try:
        from v747_sensory_body_dashboard import sensory_body_dashboard
        db = sensory_body_dashboard()
        ok = db.get("status") == "ok" and "dashboard" in db
        tests.append({"test": "dashboard_integration", "passed": ok, "detail": "sensory body dashboard renders"})
        passed += ok; failed += not ok
    except Exception as e:
        tests.append({"test": "dashboard_integration", "passed": False, "detail": str(e)}); failed += 1

    return {"version": "v749_sensory_integration_test", "created_at": datetime.now().isoformat(),
            "total_tests": len(tests), "passed": passed, "failed": failed,
            "tests": tests, "status": "ok" if failed == 0 else "partial"}


def main():
    print(f"Nova v749_sensory_integration_test")
    r = sensory_integration_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
