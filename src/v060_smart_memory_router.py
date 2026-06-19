from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v057_dictionary_conversation_router import answer as v057_answer
from v060_memory_manager import process_message


def smart_answer(message: str, thread_id: str = "default") -> dict:
    """Router wrapper: v057 answer + v060 smart memory capture."""
    # Get answer from existing pipeline
    v057 = v057_answer(message, thread_id=thread_id)
    ans = v057.get("answer", "I do not know.")
    route = v057.get("route", "unknown_fallback")

    # Capture memory
    memory = process_message(
        message=message,
        answer=ans,
        route=route,
        context=v057.get("state", {}),
    )

    result = {
        "version": "v060_smart_memory_router",
        "created_at": datetime.now().isoformat(),
        "thread_id": thread_id,
        "message": message,
        "answer": ans,
        "route": route,
        "dictionary_found": v057.get("dictionary_found", False),
        "memory_type": memory["classification"]["memory_type"],
        "memory_confidence": memory["classification"]["confidence"],
        "memory_reason": memory["classification"]["reason"],
        "should_auto_save": memory["classification"]["should_auto_save"],
        "should_require_approval": memory["classification"]["should_require_approval"],
        "should_export_to_training": memory["classification"]["should_export_to_training"],
        "stored_in": memory["stored_in"],
        "extracted_fact": memory["classification"]["extracted_fact"],
        "tags": memory["classification"]["tags"],
        "state": v057.get("state", {}),
        "v057_result": v057,
    }

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "v060_smart_memory_router_last_report.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--thread-id", default="default")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = smart_answer(args.message, thread_id=args.thread_id)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("SOURCE MODE: Smart Memory Router v060")
        print(result["answer"])
        print()
        print("Route:", result["route"])
        print("Dictionary found:", result["dictionary_found"])
        print("Memory type:", result["memory_type"])
        print("Confidence:", result["memory_confidence"])
        print("Reason:", result["memory_reason"])
        print("Auto save:", result["should_auto_save"])
        print("Requires approval:", result["should_require_approval"])
        print("Export to training:", result["should_export_to_training"])
        print("Stored in:", result["stored_in"])
        print("Tags:", result["tags"])
        if result["state"]:
            print("Topic:", result["state"].get("current_topic"))
            print("Goal:", result["state"].get("active_goal"))
            print("Turns:", result["state"].get("turn_count"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
