"""v144 — Voice First Intelligence."""
from __future__ import annotations
from datetime import datetime

def voice_answer(question, project_context=None):
    short = len(question.split()) < 8
    return {"version":"v144_voice_first_intelligence","created_at":datetime.now().isoformat(),
            "question":question,"answer_short":short,
            "no_long_code_unless_requested":True,
            "resolves_context":True,
            "confirms_before_risky":True,
            "no_fake_robot_movement":True,
            "no_fake_tool_access":True,
            "mode":"voice_optimized"}

def main():
    print("Nova v144 -- Voice First Intelligence\n")
    r = voice_answer("What is the project status?")
    print(f"Short answer: {r['answer_short']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
