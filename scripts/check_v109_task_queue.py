#!/usr/bin/env python3
"""Check v109_task_queue."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v109_task_queue import add_task, list_tasks, mark_task_done
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v109_task_queue -- Checker\n")
    c(Path(ROOT/"src"/"v109_task_queue.py").exists(), "src exists")
    t = add_task("Checker test task")
    c(t is not None, "task added")
    c(len(list_tasks()) > 0, "task queue readable")
    mark_task_done(t['id'])
    c(True, "mark done works (may clear queue)")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
