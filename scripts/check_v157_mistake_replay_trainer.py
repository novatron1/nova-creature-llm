#!/usr/bin/env python3
"""Check v157_mistake_replay_trainer."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v157_mistake_replay_trainer import get_mistake_replays
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v157_mistake_replay_trainer -- Checker\n")
    c(Path(ROOT/"src"/"v157_mistake_replay_trainer.py").exists(), "src exists")
    r = get_mistake_replays()
    c(r is not None, "result generated")
    c(r["count"] >= 2, f"{r["count"]} replays")
    c(r["uses_v074_mistake_memory"], "uses mistake memory")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
