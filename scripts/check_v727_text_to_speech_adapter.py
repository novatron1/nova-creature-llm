"""727 — Check Text To Speech Adapter"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v727_text_to_speech_adapter import text_to_speech_adapter
    r = text_to_speech_adapter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v727_text_to_speech_adapter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v727_text_to_speech_adapter: " + str(e))
    raise SystemExit(1)
