"""v805_people_learning_bridge — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def people_learning_bridge(introduction_text=""):
    """When introduced, create people profile + social learning memory."""
    if not introduction_text:
        return {"version": "v805_people_learning_bridge", "status": "no_input"}
    from v753_auto_people_memory_lock import auto_people_memory_lock
    from v802_unified_event_bus import unified_event_bus
    from v804_unified_memory_bridge import unified_memory_bridge
    result = auto_people_memory_lock(introduction_text)
    if result.get("profiles_created", 0) > 0:
        unified_event_bus("people_introduction", {"text": introduction_text, "profiles": result.get("results", [])})
        unified_memory_bridge("people_learning", {"confidence": 0.8, "subsystem": "people_memory", "text": introduction_text})
    return {"version": "v805_people_learning_bridge", "introduction": introduction_text,
            "profiles_created": result.get("profiles_created", 0), "status": "ok"}


def main():
    print(f"Nova v805_people_learning_bridge")
    r = people_learning_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
