"""v783_cross_brain_learning_router — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def cross_brain_learning_router(topic="", claim=""):
    """Route learning by type to appropriate brain."""
    topic_lower = topic.lower() if topic else (claim.lower() if claim else "")
    route_map = [
        (["math", "code", "logic", "rule", "equation", "algorithm", "syntax"], "left_hemisphere"),
        (["pattern", "visual", "imagin", "creative", "art", "design", "map", "diagram"], "right_hemisphere"),
        (["fact", "history", "name", "identity", "person", "date", "event", "define"], "memory_transformer"),
        (["step", "procedure", "how to", "process", "method", "workflow"], "planner_transformer"),
        (["conflict", "uncertain", "contradict", "wrong", "disagree"], "critic_conscience_transformer"),
        (["practice", "scenario", "drill", "simulate", "replay"], "dream_simulation_transformer"),
        (["explain", "describe", "summarize", "wording"], "speech_output_transformer"),
    ]
    primary = "memory_transformer"
    secondary = []
    for keywords, brain in route_map:
        if any(k in topic_lower for k in keywords):
            primary = brain
            break
    return {"version": "v783_cross_brain_learning_router", "topic": topic,
            "primary_route": primary, "routes": [primary] + secondary, "status": "ok"}


def main():
    print(f"Nova v783_cross_brain_learning_router")
    r = cross_brain_learning_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
