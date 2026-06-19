"""v806_sensory_learning_bridge — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def sensory_learning_bridge(source_type="", observation=""):
    """Convert sensory observation into learning candidate."""
    if not observation:
        return {"version": "v806_sensory_learning_bridge", "status": "no_input"}
    from v802_unified_event_bus import unified_event_bus
    from v708_multimodal_router import multimodal_router
    from v788_conflict_detection import conflict_detection
    route = multimodal_router(source_type, observation)
    conflict = conflict_detection(observation, [])
    learning_candidate = {
        "source": source_type,
        "observation": observation,
        "route": route.get("routes", ["critic_conscience_transformer"]),
        "has_conflict": conflict.get("conflict_count", 0) > 0,
        "approved": conflict.get("conflict_count", 0) == 0
    }
    unified_event_bus("sensory_learning", learning_candidate)
    return {"version": "v806_sensory_learning_bridge", "candidate": learning_candidate, "status": "ok"}


def main():
    print(f"Nova v806_sensory_learning_bridge")
    r = sensory_learning_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
