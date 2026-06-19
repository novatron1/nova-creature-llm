"""v758_people_memory_router — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def people_memory_router(person_status=None, signal_type=None):
    """Route people memory into the brain system."""
    routes = {
        "name_identity": {"primary": "memory_transformer", "secondary": []},
        "face_pattern": {"primary": "right_hemisphere", "secondary": ["memory_transformer"]},
        "voice_pattern": {"primary": "memory_transformer", "secondary": []},
        "uncertain_match": {"primary": "critic_conscience_transformer", "secondary": []},
        "social_response": {"primary": "planner_transformer", "secondary": ["memory_transformer"]},
        "spoken_response": {"primary": "speech_output_transformer", "secondary": []},
    }
    route = routes.get(signal_type or "name_identity", {"primary": "memory_transformer", "secondary": []})
    return {"version": "v758_people_memory_router", "created_at": datetime.now().isoformat(),
            "person_status": person_status or "unknown", "signal_type": signal_type or "name_identity",
            "routes": [route["primary"]] + route["secondary"], "primary_route": route["primary"],
            "status": "ok"}


def main():
    import sys
    print(f"Nova v758_people_memory_router")
    r = people_memory_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
