"""v123 — Conversation Timing Brain."""
from __future__ import annotations
from datetime import datetime

def decide_timing(question, context=None):
    if not question or len(question.strip())==0:
        return {"version":"v123_timing_brain","created_at":datetime.now().isoformat(),
                "decision":"ask_clarification","reason":"Empty question"}
    if len(question.split()) < 5:
        return {"version":"v123_timing_brain","created_at":datetime.now().isoformat(),
                "decision":"answer_short","reason":"Short question"}
    if any(w in question.lower() for w in ["report","status","summary","list"]):
        return {"version":"v123_timing_brain","created_at":datetime.now().isoformat(),
                "decision":"give_full_report","reason":"Requesting report"}
    return {"version":"v123_timing_brain","created_at":datetime.now().isoformat(),
            "decision":"answer_full","reason":"Standard question"}

def main():
    print("Nova v123 -- Timing Brain\n")
    r = decide_timing("What can you do?")
    print(f"Decision: {r['decision']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
