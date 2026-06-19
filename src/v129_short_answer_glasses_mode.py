"""v129 — Short-Answer Glasses Mode."""
from __future__ import annotations
from datetime import datetime

def glasses_answer(question, context=None):
    return {"version":"v129_glasses_mode","created_at":datetime.now().isoformat(),
            "question":question,"short_answer":"Short, direct answer for glasses/voice.",
            "no_long_code":True,"preserves_context":True,"gives_next_action":True,
            "note":"Optimized for smart glasses / voice. No code blocks."}

def main():
    print("Nova v129 -- Glasses Mode\n")
    r = glasses_answer("What is the project status?")
    print(f"Short: {r['short_answer'][:30]}...")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
