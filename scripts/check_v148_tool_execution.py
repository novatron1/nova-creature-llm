#!/usr/bin/env python3
"""Check v148_tool_execution."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v148_tool_execution_readiness import check_tool_readiness, get_all_tools_status
E,P=[], []
def c(cond,msg):
    if cond: P.append(f"  [PASS] {msg}")
    else: E.append(f"  [FAIL] {msg}")
def main():
    print(f"Nova v148_tool_execution -- Checker\n")
    c(Path(ROOT/"src"/"v148_tool_execution_readiness.py").exists(), "src exists")
    r = check_tool_readiness("file_tools")
    c(r is not None, "result generated")
    c("execution_ready" in r, "readiness determined")
    all_tools = get_all_tools_status()
    c(len(all_tools) >= 5, "all tool classes checked")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
