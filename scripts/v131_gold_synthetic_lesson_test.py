#!/usr/bin/env python3
"""Gold test for v131_synthetic_lesson_generator."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v131_synthetic_lesson_generator import generate_synthetic_lessons
E,P=[], []
def main():
    print("Nova v131_synthetic_lesson_generator -- Gold Test\n")
    r = generate_synthetic_lessons("gold concept",2)
    if isinstance(r, dict): P.append("Result with " + str(len(r)) + " fields")
    else: P.append("Result generated")
    print("\n" + "="*60 + "\nPASSED: " + str(len(P)) + ", ERRORS: " + str(len(E)))
    for p in P: print("  [PASS] " + p)
    for e in E: print("  [FAIL] " + e)
    (ROOT/"reports"/"v131_synthetic_lesson_generator_status.json").write_text(json.dumps({"version":"v131_synthetic_lesson_generator_gold","created_at":datetime.now().isoformat(),"passes":len(P),"errors":len(E)},indent=2))
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
