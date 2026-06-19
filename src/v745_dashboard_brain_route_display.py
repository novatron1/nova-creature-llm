"""745 — Sensory Body Layer: Dashboard Brain Route Display"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def dashboard_brain_route_display():
    """Display currently routed brain roles for sensory inputs."""
    routes = {
        "face/camera/vision": ["right_hemisphere", "memory_transformer"],
        "microphone/hearing": ["memory_transformer", "planner_transformer"],
        "screenshot/screen": ["left_hemisphere", "right_hemisphere"],
        "speaker_output": ["speech_output_transformer"],
        "uncertain_signal": ["critic_conscience_transformer"],
    }
    return {"version": "v745_dashboard_brain_route_display", "created_at": datetime.now().isoformat(),
            "routes": routes, "status": "ok"}


def main():
    print(f"Nova v745_dashboard_brain_route_display")
    r = dashboard_brain_route_display()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
