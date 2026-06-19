"""v160 — Council Tournament."""
from __future__ import annotations
from datetime import datetime


ROLES = ["planner","critic","memory","left_hemisphere","right_hemisphere","strategy","speech"]

def run_council_tournament(question="What is the next upgrade?"):
    proposals = {r:f"{r} proposes answer" for r in ROLES}
    scores = {"planner":85,"critic":90,"memory":88,"left_hemisphere":80,"right_hemisphere":75,"strategy":92,"speech":85}
    winner = max(scores, key=scores.get)
    return {"version":"v160_council_tournament","created_at":datetime.now().isoformat(),
            "question":question,"proposals":proposals,"scores":scores,
            "winner":winner,"final_answer":f"{winner}: {proposals[winner]}"}


def main():
    print(f"Nova v160_council_tournament\n")
    r = run_council_tournament()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
