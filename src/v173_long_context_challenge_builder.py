"""v173 — Long Context Challenge Builder."""
from __future__ import annotations
from datetime import datetime


CHALLENGES = [
    ("version_order","What comes after v095 and before v108?","v096-v107"),
    ("stack_purpose","What did v069-v080 add?","Tools: self-scripting, robot sim, apps"),
    ("blocked_movement","Why is robot movement blocked?","Safety systems not all passing"),
    ("next_stack","What was the next major stack after v095?","v096 vision expansion"),
    ("benchmark_rule","What is the promotion rule?","Must improve or preserve benchmarks"),
]

def build_challenges():
    return {"version":"v173_long_context_challenge","created_at":datetime.now().isoformat(),
            "challenges":[{"task":t,"prompt":p,"expected":e} for t,p,e in CHALLENGES],
            "total":len(CHALLENGES)}


def main():
    print(f"Nova v173_long_context_challenge_builder\n")
    r = build_challenges()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
