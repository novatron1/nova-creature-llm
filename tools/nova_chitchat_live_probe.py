"""Sequential live chat evidence; never submits the next turn before completion."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import time
import urllib.request
import uuid

PROMPTS = [
    "Hi Nova.",
    "How are you doing today?",
    "I had a long day.",
    "Mostly chores. I finally sat down with a cup of tea.",
    "Just chatting sounds good.",
    "What are you curious about?",
    "I like that. I have been getting into music lately.",
    "Mostly mellow guitar and old soul.",
    "What kind of music would suit a quiet evening?",
    "Why that kind?",
    "Actually, I might go for a short walk instead.",
    "It's a little rainy, though.",
    "Then a cozy night indoors it is.",
    "Can you give me a silly name for a lazy Sunday?",
    "Ha, that's a good one.",
    "What were we talking about before the walk?",
    "I appreciate you listening.",
    "Do you really have feelings, or is this how you talk?",
    "Fair enough. It's still nice chatting with you.",
    "Good night, Nova.",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--mode", default="nova")
    args = parser.parse_args()
    identity = "live-chitchat-test-" + uuid.uuid4().hex[:10]
    history = []
    report = {"started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "base_url": args.base_url, "test_user_id": identity,
              "planned_turns": len(PROMPTS), "turns": [],
              "quality_review": "pending; HTTP completion does not establish answer quality"}
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    for index, prompt in enumerate(PROMPTS, 1):
        started = time.monotonic()
        payload = {"text": prompt, "user_id": identity, "conversation_id": identity,
                   "conversation_history": history[-20:], "nova_model_mode": args.mode}
        item = {"number": index, "prompt": prompt}
        try:
            request = urllib.request.Request(args.base_url + "/api/chat",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=args.timeout) as response:
                result = json.load(response)
            answer = result.get("response", "")
            trace = result.get("trace") or {}
            item.update(response=answer, completed=bool(answer),
                model=trace.get("local_llm_model"), source=trace.get("final_answer_source") or trace.get("source"),
                answer_status=result.get("answer_status"),
                conversation_decision=trace.get("conversation_decision"),
                fallback=trace.get("fallback_used"),
                firewall=trace.get("answer_firewall"),
                committed=trace.get("conversation_state_committed"),
                escalation=trace.get("regular_chat_escalation"))
            item.update(trace_source=trace.get("source"),
                        synthesis_used=trace.get("local_llm_synthesis_used"),
                        response_repair=trace.get("response_repair"),
                        context_compaction=trace.get("context_compaction"))
            if trace.get("conversation_state_committed") is not False and answer:
                history.extend([{"role": "user", "content": prompt},
                                {"role": "assistant", "content": answer}])
        except Exception as exc:
            item.update(completed=False, error=f"{type(exc).__name__}: {exc}")
        item["seconds"] = round(time.monotonic() - started, 3)
        report["turns"].append(item)
        report["completed_responses"] = sum(bool(turn["completed"]) for turn in report["turns"])
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({key: item.get(key) for key in (
            "number", "prompt", "response", "seconds", "model", "completed", "error"
        )}, ensure_ascii=False), flush=True)
        if not item["completed"]:
            # Do not build a backlog behind a timed-out live request.
            break
    return 0 if report["completed_responses"] == len(PROMPTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
