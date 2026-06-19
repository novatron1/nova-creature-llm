#!/usr/bin/env python3
"""Check v078 voice mode."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v078_voice_mode import process_voice, SHORT_COMMANDS
E, P = [], []
def c(cond, msg):
    if cond:
        P.append(f"  [PASS] {msg}")
    else:
        E.append(f"  [FAIL] {msg}")
def main():
    print("Nova v078 -- Voice Mode Checker\n")
    c(Path(ROOT/"src"/"v078_voice_mode.py").exists(), "src exists")
    r = process_voice("Do that")
    c(r["mode"] == "voice_project", "do that -> project")
    r2 = process_voice("What next")
    c(r2["mode"] == "voice_project", "what next -> project")
    r3 = process_voice("Tell me short")
    c(r3["mode"] == "voice_short", "tell me short -> short")
    r4 = process_voice("Is robot movement active")
    c(r4["mode"] == "voice_robot_sim", "robot -> robot_sim")
    c(r4["real_hardware_enabled"] == False, "no fake robot claim")
    r5 = process_voice("Write a Python function")
    c(r5["mode"] == "voice_coding", "code -> coding mode")
    r6 = process_voice("Explain in detail")
    c(r6["mode"] == "voice_deep", "explain -> deep mode")
    c(len(SHORT_COMMANDS) == 8, f"8 short commands ({len(SHORT_COMMANDS)})")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P:
        print(p)
    for e in E:
        print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
