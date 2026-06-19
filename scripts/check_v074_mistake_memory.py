#!/usr/bin/env python3
"""Check v074 mistake memory."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v074_mistake_memory import log_mistake, log_fix, get_mistakes, get_fixes
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v074 -- Mistake Memory Checker\n")
    c(Path(ROOT/"src"/"v074_mistake_memory.py").exists(), "src exists")
    m = log_mistake("test_error", "checker", "test failure", "fake error", "", "test", False, "", "", False, True)
    c(m.get("id"), "mistake logged with id")
    c(m["error_type"] == "test_error", "error type recorded")
    fix = log_fix(m["id"], "fixed test", True, "passed")
    c(fix["mistake_id"] == m["id"], "fix linked to mistake")
    mistakes = get_mistakes()
    c(len(mistakes) >= 1, f"mistakes found ({len(mistakes)})")
    fixes = get_fixes()
    c(len(fixes) >= 1, f"fixes found ({len(fixes)})")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
