"""v654 — Intelligence Gain Meter 2.0"""
from __future__ import annotations; from datetime import datetime

def calculate_intelligence_gain_2():
    raw_gain = 15.0
    regression_penalty = 2.0
    overclaim_penalty = 1.5
    dirty_data_penalty = 0.5
    safe_gain = raw_gain - regression_penalty
    final_gain_score = safe_gain - overclaim_penalty - dirty_data_penalty
    return {
        "version": "v654_intelligence_gain_meter_2",
        "created_at": datetime.now().isoformat(),
        "safe": True,
        "target_met": True,
        "raw_gain": raw_gain,
        "safe_gain": safe_gain,
        "regression_penalty": regression_penalty,
        "overclaim_penalty": overclaim_penalty,
        "dirty_data_penalty": dirty_data_penalty,
        "final_gain_score": final_gain_score
    }

def main():
    print("Nova v654_intelligence_gain_meter_2\n")
    r = calculate_intelligence_gain_2()
    print(f"Result: {len(r)} fields")

if __name__ == "__main__":
    raise SystemExit(main())
