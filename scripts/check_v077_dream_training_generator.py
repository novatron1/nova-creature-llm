#!/usr/bin/env python3
"""Check v077 dream training generator."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v077_dream_training_generator import generate_variants, critic_review, export_training_candidates, run_generator
E, P = [], []
def c(cond, msg):
    if cond: P.append(f"  \u2705 {msg}")
    else: E.append(f"  \u274c {msg}")
def main():
    print("Nova v077 -- Dream Training Generator Checker\n")
    c(Path(ROOT/"src"/"v077_dream_training_generator.py").exists(), "src exists")
    vars = generate_variants("Who created you?", "Mr. Novotron", 20)
    c(len(vars) == 20, f"20 variants generated ({len(vars)})")
    safe = [v for v in vars if v["variant_type"] == "safe"]
    distorted = [v for v in vars if v["variant_type"] == "distorted"]
    c(len(safe) >= 18, f">=18 safe ({len(safe)})")
    review = critic_review(vars)
    c(review["approved_count"] >= 18, f"approved: {review['approved_count']}")
    c(review["rejected_count"] >= 2, f"rejected: {review['rejected_count']}")
    export = export_training_candidates(review["approved"])
    c(export["exported_count"] >= 18, f"exported: {export['exported_count']}")
    result = run_generator("Who created you?", "Mr. Novotron", 20)
    c(result["variants_generated"] == 20, "full run: 20 variants")
    c(result["approved"] >= 18, f"full run: >=18 approved ({result['approved']})")
    print(f"\n{'='*60}\nPASSED: {len(P)}, ERRORS: {len(E)}")
    for p in P: print(p)
    for e in E: print(e)
    return 0 if not E else 1
if __name__ == "__main__":
    raise SystemExit(main())
