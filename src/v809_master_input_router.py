"""v809_master_input_router — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def master_input_router(text="", source="plain_text"):
    """Accept input and decide what systems should process it."""
    text_lower = text.lower()
    input_type = "unknown_input"
    systems = []
    if any(w in text_lower for w in ["my name is", "i'm ", "i am ", "they call me", "this is", "meet ", "say hi"]):
        input_type = "introduction"
        systems = ["people_memory", "event_bus", "memory_bridge"]
    elif any(w in text_lower for w in ["no,", "that's wrong", "actually", "correction", "remember it like"]):
        input_type = "correction"
        systems = ["rapid_learning", "correction_loop", "conflict_detection"]
    elif any(w in text_lower for w in ["learn", "remember", "this is important", "note that", "fact:"]):
        input_type = "teaching_text"
        systems = ["rapid_learning", "lesson_chunker", "self_test_engine"]
    elif source in ("image_summary", "audio_transcript", "screen_summary"):
        input_type = source
        systems = ["sensory_learning", "multimodal_router", "memory_bridge"]
    else:
        input_type = "plain_text"
        systems = ["brain_router", "memory_bridge"]
    return {"version": "v809_master_input_router", "text": text[:200], "source": source,
            "input_type": input_type, "systems": systems, "status": "ok"}


def main():
    print(f"Nova v809_master_input_router")
    r = master_input_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
