"""v810_master_output_router — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def master_output_router(content="", output_type="normal_answer"):
    """Route final output."""
    routes = {
        "normal_answer": {"format": "text", "route": "speech_output_transformer", "spoken": False},
        "spoken_answer": {"format": "text+audio", "route": "speech_output_transformer", "spoken": True},
        "memory_confirmation": {"format": "text", "route": "memory_transformer", "spoken": False},
        "learning_report": {"format": "text", "route": "planner_transformer", "spoken": False},
        "uncertainty_report": {"format": "text", "route": "critic_conscience_transformer", "spoken": False},
        "permission_request": {"format": "text", "route": "planner_transformer", "spoken": False},
        "test_result": {"format": "json", "route": "left_hemisphere", "spoken": False},
        "action_ready": {"format": "text", "route": "speech_output_transformer", "spoken": True},
    }
    route = routes.get(output_type, routes["normal_answer"])
    return {"version": "v810_master_output_router", "content": content[:200], "output_type": output_type,
            "format": route["format"], "route": route["route"], "spoken": route["spoken"], "status": "ok"}


def main():
    print(f"Nova v810_master_output_router")
    r = master_output_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
