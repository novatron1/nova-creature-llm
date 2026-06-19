"""v929_training_style_winner_selector — Check"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v929_training_style_winner_selector import training_style_winner_selector
    r = training_style_winner_selector()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v929_training_style_winner_selector")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v929_training_style_winner_selector: " + str(e))
    raise SystemExit(1)
