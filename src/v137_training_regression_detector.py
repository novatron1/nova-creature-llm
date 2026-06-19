"""v137 — Training Regression Detector."""
from __future__ import annotations
from datetime import datetime

def detect_training_regression(before_scores, after_scores):
    regressions = []
    for test, before in before_scores.items():
        after = after_scores.get(test, 0)
        if after < before:
            regressions.append({"test":test,"before":before,"after":after,"change":after-before})
    return {"version":"v137_training_regression_detector","created_at":datetime.now().isoformat(),
            "regressions":regressions,"regression_count":len(regressions),
            "regression_detected":len(regressions) > 0,
            "note":"If regression detected, block promotion."}

def main():
    print("Nova v137 -- Regression Detector\n")
    r = detect_training_regression({"reasoning":90},{"reasoning":85})
    print(f"Regression: {r['regression_detected']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
