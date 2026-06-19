"""vv1386_live_camera_vision_router — Live Voice + Camera Conversation Runtime"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def live_camera_vision_router():
    """Route camera observations: face to people+right, known to memory, unknown to unknown profile, body/pose to right, uncertainty to critic, missing permission to deny/ask"""
    routing = {
        "face_detected": ["people_memory", "right_hemisphere"],
        "known_person": ["memory_transformer"],
        "unknown_person": ["people_memory_unknown_profile"],
        "body_hand_pose": ["right_hemisphere"],
        "visual_uncertainty": ["critic_conscience_transformer"],
        "camera_permission_missing": "deny_or_ask_permission",
    }
    return {"version": "v1386_live_camera_vision_router", "created_at": datetime.now().isoformat(),
            "module": "Route camera observations: face to people+right, known to memory, unknown to unknown profile, body/pose to right, uncertainty to critic, missing permission to deny/ask", "routing_rules": routing, "status": "ok"}


def main():
    print(f"Nova v1386_live_camera_vision_router")
    r = live_camera_vision_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
