"""v669 — Planner Growth Decision Gate"""
from __future__ import annotations; from datetime import datetime

def gate_planner_growth_decision():
    """Statuses: target_met_85, improved_but_below_target, no_improvement,
    regression_detected, blocked_by_missing_candidate, blocked_by_missing_torch,
    needs_more_clean_training"""
    # Simulate: improved but not yet at target
    current_score = 79.8
    target = 85
    previous_score = 72.4
    regression_detected = False
    candidate_exists = True
    torch_available = False

    if not candidate_exists:
        status = "blocked_by_missing_candidate"
    elif not torch_available:
        status = "blocked_by_missing_torch"
    elif regression_detected:
        status = "regression_detected"
    elif current_score >= target:
        status = "target_met_85"
    elif current_score > previous_score:
        status = "improved_but_below_target"
    elif current_score == previous_score:
        status = "no_improvement"
    else:
        status = "needs_more_clean_training"

    return {
        "version": "v669_growth_decision_gate",
        "created_at": datetime.now().isoformat(),
        "safe": True,
        "status": status,
        "current_score": current_score,
        "target": target,
        "previous_score": previous_score,
        "improvement": round(current_score - previous_score, 1),
        "regression_detected": regression_detected,
        "candidate_exists": candidate_exists,
        "torch_available": torch_available,
        "gate_passed": status in ("target_met_85", "improved_but_below_target"),
        "warning": "real_hardware_enabled: False, real_robot_movement_allowed: False"
    }

def main():
    print("Nova v669_growth_decision_gate\n")
    r = gate_planner_growth_decision()
    print(f"Result: {len(r)} fields — Status: {r['status']}")

if __name__ == "__main__":
    raise SystemExit(main())
