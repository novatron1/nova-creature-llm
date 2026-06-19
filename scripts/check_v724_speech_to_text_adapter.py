"""724 — Check Speech To Text Adapter"""
import sys, json; from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
try:
    from v724_speech_to_text_adapter import speech_to_text_adapter
    r = speech_to_text_adapter()
    ok = r.get("status") == "ok" or r.get("safe") == True
    print("[" + ("PASS" if ok else "FAIL") + "] v724_speech_to_text_adapter")
    print(json.dumps(r, indent=2))
    raise SystemExit(0 if ok else 1)
except Exception as e:
    print("[FAIL] v724_speech_to_text_adapter: " + str(e))
    raise SystemExit(1)
