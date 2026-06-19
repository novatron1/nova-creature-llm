#!/usr/bin/env python3
"""Check v069 self-scripting brain."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v069_self_scripting_brain import plan_script, write_script, test_script, run_self_script_cycle
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v069 -- Self-Scripting Checker\n")
    print("1. Files...")
    c((ROOT/"src"/"v069_self_scripting_brain.py").exists(), "src exists")
    print("2. plan_script...")
    plan = plan_script("test")
    c("steps" in plan, "plan has steps")
    print("3. write_script...")
    wr = write_script(plan)
    c(wr.get("written"), f"written to {wr.get('script_path','?')}")
    print("4. test_script...")
    tr = test_script(wr["script_path"])
    c(tr.get("success"), "script runs")
    c(tr.get("json_output_exists"), "JSON output exists")
    c(tr.get("json_valid"), "JSON valid")
    print("5. full cycle...")
    cy = run_self_script_cycle("full test")
    c(cy["cycle_complete"], "cycle complete")
    c(not cy["core_files_overwritten"], "no core overwrite")
    c(not cy["unsafe_commands_used"], "no unsafe commands")
    print(f"\n{'='*60}")
    print(f"PASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
