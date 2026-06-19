"""v807_brain_router_integration — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def brain_router_integration(input_type="", content=""):
    """Unified routing for all input types."""
    routes = {
        "math": "left_hemisphere", "code": "left_hemisphere", "rule": "left_hemisphere",
        "visual": "right_hemisphere", "pattern": "right_hemisphere", "face": "right_hemisphere", "screen": "right_hemisphere",
        "fact": "memory_transformer", "name": "memory_transformer", "history": "memory_transformer", "person": "memory_transformer",
        "plan": "planner_transformer", "procedure": "planner_transformer", "next": "planner_transformer",
        "uncertain": "critic_conscience_transformer", "conflict": "critic_conscience_transformer",
        "scenario": "dream_simulation_transformer", "practice": "dream_simulation_transformer", "replay": "dream_simulation_transformer",
        "speak": "speech_output_transformer", "output": "speech_output_transformer",
    }
    content_lower = content.lower() if content else input_type.lower()
    primary = routes.get(input_type, "memory_transformer")
    for key, brain in routes.items():
        if key in content_lower:
            primary = brain
            break
    return {"version": "v807_brain_router_integration", "input_type": input_type,
            "content": content[:100] if content else "", "primary_route": primary, "status": "ok"}


def main():
    print(f"Nova v807_brain_router_integration")
    r = brain_router_integration()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
