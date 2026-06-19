"""v238 — Planner Promotion Decision"""
from __future__ import annotations
from datetime import datetime

def decide(candidate_exists=False,candidate_won=False,regression=False):
    if not candidate_exists: return {"version":"v238_promotion_decision","created_at":datetime.now().isoformat(),"decision":"preserve_v055","reason":"No candidate checkpoint created.","winner":"v055"}
    if regression: return {"decision":"blocked_by_regression","reason":"Candidate caused regression.","winner":"v055"}
    if candidate_won: return {"decision":"promote_candidate","reason":"Candidate beat v055 in tournament.","winner":"candidate"}
    return {"decision":"preserve_v055","reason":"Candidate did not beat v055.","winner":"v055"}

def main():
    print("Nova v238_planner_promotion_decision\n")
    r = decide()
    if isinstance(r, dict): print(f"Result: {len(r)} fields")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
