#!/usr/bin/env python3
import sys; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "src"))
from v229_next_best_training_recommender import recommend_training; import json
def main():
    r = recommend_training(); print(f"Next-Best Training Recommendation\n")
    for rec in r["recommendations"]:
        print(f"  #{rec['priority']}: {rec['skill']} for {rec['role']} (score: {rec['current_score']})")
    print(f"\nNext role to train: {r['next_best_role']}")
    print(f"Next skill to train: {r['next_best_skill']}")
    (ROOT/"reports"/"v229_training_recommendation.json").write_text(json.dumps(r,indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
