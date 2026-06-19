from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from conversation_memory import ConversationMemory

try:
    from v052_role_brain_router import run as role_router_run
except Exception:
    role_router_run = None


def fallback_router(prompt: str) -> dict:
    return {
        "version": "v056_fallback_router",
        "created_at": datetime.now().isoformat(),
        "results": [{
            "question": prompt,
            "final_answer": "I do not know.",
            "selected_route": "unknown_fallback",
        }],
    }


def select_first_result(report: dict) -> tuple[str, str]:
    results = report.get("results", [])
    if not results:
        return "I do not know.", "unknown_fallback"
    first = results[0]
    return first.get("final_answer", "I do not know."), first.get("selected_route", "unknown_fallback")


def answer_with_context(message: str, thread_id: str = "default") -> dict:
    memory = ConversationMemory(ROOT, thread_id=thread_id)
    ctx = memory.build_context(message)

    router_prompt = ctx["resolved_message"]
    if role_router_run:
        report = role_router_run(router_prompt)
    else:
        report = fallback_router(router_prompt)

    answer, route = select_first_result(report)

    # Conversation-specific follow-up help.
    msg = message.strip().lower()
    if ctx["is_followup"] and msg in {"ok", "okay", "go", "do that", "make that", "add that", "let's do that"}:
        if ctx["active_goal"]:
            answer = f"Planner: continuing the active goal — {ctx['active_goal']}."
            route = "conversation_memory_planner"
    elif msg in {"what next", "next"} and ctx["active_goal"]:
        answer = f"Planner: next step is to continue: {ctx['active_goal']}."
        route = "conversation_memory_planner"

    state = memory.update_after_turn(message, answer, route, extra={"router_report": report})

    return {
        "version": "v056_conversation_memory_loop",
        "thread_id": thread_id,
        "message": message,
        "resolved_message": router_prompt,
        "answer": answer,
        "route": route,
        "context": ctx,
        "state": {
            "current_topic": state.get("current_topic"),
            "active_goal": state.get("active_goal"),
            "turn_count": state.get("turn_count"),
            "last_route": state.get("last_route"),
        },
        "router_report": report,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--message", required=True)
    ap.add_argument("--thread-id", default="default")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = answer_with_context(args.message, thread_id=args.thread_id)

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "v056_conversation_memory_last_report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("SOURCE MODE: Conversation Memory Loop v056")
        print(result["answer"])
        print()
        print("Route:", result["route"])
        print("Topic:", result["state"]["current_topic"])
        print("Goal:", result["state"]["active_goal"])
        print("Turns:", result["state"]["turn_count"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
