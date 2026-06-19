from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dictionary_memory import DictionaryMemory

try:
    from conversation_memory import ConversationMemory
except Exception:
    ConversationMemory = None

try:
    from v056_conversation_router import answer_with_context as v056_answer
except Exception:
    v056_answer = None

try:
    from v052_role_brain_router import run as role_router_run
except Exception:
    role_router_run = None


def fallback_answer(message: str) -> dict:
    if role_router_run:
        report = role_router_run(message)
        results = report.get("results", [])
        if results:
            first = results[0]
            return {
                "answer": first.get("final_answer", "I do not know."),
                "route": first.get("selected_route", "role_router"),
                "router_report": report,
            }
    return {"answer": "I do not know.", "route": "unknown_fallback", "router_report": {}}


def answer(message: str, thread_id: str = "default") -> dict:
    dictionary = DictionaryMemory(ROOT)
    hit = dictionary.lookup(message)

    if hit.get("found"):
        ans = hit["answer"]
        route = "dictionary_memory_exact"
        router_report = {"dictionary_hit": hit}
    elif v056_answer:
        v056 = v056_answer(message, thread_id=thread_id)
        ans = v056.get("answer", "I do not know.")
        route = v056.get("route", "conversation_memory")
        router_report = v056
    else:
        fb = fallback_answer(message)
        ans = fb["answer"]
        route = fb["route"]
        router_report = fb["router_report"]

    if ConversationMemory:
        mem = ConversationMemory(ROOT, thread_id=thread_id)
        state = mem.update_after_turn(message, ans, route, extra={"v057_dictionary_router": router_report})
    else:
        state = {}

    result = {
        "version": "v057_dictionary_conversation_router",
        "created_at": datetime.now().isoformat(),
        "thread_id": thread_id,
        "message": message,
        "answer": ans,
        "route": route,
        "dictionary_found": bool(hit.get("found")),
        "state": {
            "current_topic": state.get("current_topic") if isinstance(state, dict) else "",
            "active_goal": state.get("active_goal") if isinstance(state, dict) else "",
            "turn_count": state.get("turn_count") if isinstance(state, dict) else "",
        },
        "router_report": router_report,
    }

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "v057_dictionary_conversation_last_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--thread-id", default="default")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = answer(args.message, thread_id=args.thread_id)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("SOURCE MODE: Dictionary + Conversation Memory v057")
        print(result["answer"])
        print()
        print("Route:", result["route"])
        print("Dictionary found:", result["dictionary_found"])
        if result["state"]:
            print("Topic:", result["state"].get("current_topic"))
            print("Goal:", result["state"].get("active_goal"))
            print("Turns:", result["state"].get("turn_count"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
