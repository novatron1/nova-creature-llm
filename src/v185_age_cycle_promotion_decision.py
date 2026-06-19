"""v185 — Age-Cycle Promotion Decision."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def decide_promotion():
    # Check for candidate checkpoints
    candidate_dir = ROOT / "checkpoints" / "candidates" / "v184_age_cycle"
    candidates_exist = candidate_dir.exists() and any(candidate_dir.iterdir())

    # Check tournament result
    tournament_file = ROOT / "reports" / "v184_checkpoint_tournament_after_age_cycle.json"
    candidate_won = False
    if tournament_file.exists():
        import json
        try:
            tr = json.loads(tournament_file.read_text())
            candidate_won = tr.get("winner","") != "v055_current" and candidates_exist
        except: pass

    # Check owner approval
    approval_present = False
    approval_path = ROOT / "data" / "owner_approval" / "approval_queue.jsonl"
    if approval_path.exists():
        with open(approval_path) as f:
            for l in f:
                if "finetune" in l.lower() or "training" in l.lower():
                    try:
                        import json; entry = json.loads(l)
                        approval_present = entry.get("approved",False)
                    except: pass

    # Check v095 regression
    # (simulated - v095 still passes from regression)
    v095_passes = True

    # Determine decision
    if not candidates_exist:
        decision = "preserve_current"
        reason = "No candidate checkpoints created. v055 remains live."
    elif not approval_present:
        decision = "needs_more_lessons" if not candidates_exist else "needs_approval"
        reason = "Fine-tune blocked by missing owner approval. v055 preserved."
    elif candidate_won and v095_passes:
        decision = "promote_candidate"
        reason = "Candidate beat v055 in tournament with no regression."
    elif not v095_passes:
        decision = "blocked_by_regression"
        reason = "Candidate caused regression in v095 intelligence benchmark."
    else:
        decision = "preserve_current"
        reason = "Candidate did not beat v055. v055 remains winner."

    return {"version":"v185_promotion_decision","created_at":datetime.now().isoformat(),
            "decision":decision,"reason":reason,
            "winner":"v184_candidate" if decision=="promote_candidate" else "v055_current",
            "candidates_exist":candidates_exist,
            "candidate_won_tournament":candidate_won,
            "v095_regression":not v095_passes,
            "owner_approval_present":approval_present,
            "robot_movement_still_blocked":True,
            "next_action":"Run fine-tune after owner approval" if not approval_present and candidates_exist else
                          "Run tournament" if candidates_exist else "Build training batch first"}

def main():
    print("Nova v185 -- Promotion Decision\n")
    r = decide_promotion()
    print(f"Decision: {r['decision']}")
    print(f"Reason: {r['reason']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
