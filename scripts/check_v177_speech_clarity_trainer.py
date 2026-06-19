#!/usr/bin/env python3
"""Check v177_speech_clarity_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v177_speech_clarity_trainer import format_speech, get_modes
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v177_speech_clarity_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v177_speech_clarity_trainer.py").exists(), "src exists")
    r = format_speech("test","short_voice")
    c(r is not None, "result generated")
    c("short_voice" in r["formatted"], "formatted correctly")
    m = get_modes()
    c(len(m) >= 3, "modes available")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
