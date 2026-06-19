"""v100 — Visual Memory Builder. Converts screenshot reports into smart memory events."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any
ROOT = Path(__file__).resolve().parents[1]

def build_visual_memory(vision_event: dict, context: dict | None = None) -> dict[str, Any]:
    text = str(vision_event.get("text_or_description", vision_event.get("source_text", ""))).lower()
    status = vision_event.get("pass_fail_status", "")
    error_type = vision_event.get("error_type", "")
    mem_type = "auto_project_memory"
    trainable = False
    if "pass" in status or "passed" in text:
        mem_type = "auto_project_memory"
        trainable = False
    elif error_type and error_type != "success":
        mem_type = "mistake_memory"
        trainable = True
    elif "maybe" in text or "uncertain" in text:
        mem_type = "pending_approval_memory"
        trainable = False
    return {
        "version": "v100_visual_memory", "created_at": datetime.now().isoformat(),
        "memory_type": mem_type, "trainable_after_approval": trainable,
        "approved": mem_type == "auto_project_memory",
        "requires_approval": mem_type == "pending_approval_memory",
        "suggested_storage_path": f"data/smart_memory/{mem_type}.jsonl",
    }

def main():
    print("Nova v100 -- Visual Memory Builder\n")
    event = {"text_or_description": "v095 passed 13/13.", "pass_fail_status": "pass"}
    r = build_visual_memory(event)
    print(f"Type: {r['memory_type']}, Trainable: {r['trainable_after_approval']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
