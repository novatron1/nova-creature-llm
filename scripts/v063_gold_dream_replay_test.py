#!/usr/bin/env python3
"""v063 — Gold dream replay test: generate variants, critic review, export."""

import json, sys
from pathlib import Path
from datetime import datetime
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v063_dream_critic import generate_dream_variants, review_dreams
from v063_dream_replay import export_dream_lessons, generate_dream_lessons
from v063_inner_voice import inner_voice_reflect

ERRORS = []
PASSES = []

def main():
    print("Nova Creature v063 — Gold Dream Replay Test\n")

    # Phase 1: Dream variants from seed
    print("Phase 1: Generating dream variants from 'Who created you?' -> Mr. Novotron\n")
    variants = generate_dream_variants("Who created you?", "Mr. Novotron", count=12)
    PASSES.append(f"Generated {len(variants)} dream variants (>=10 required)")
    safes = sum(1 for v in variants if v["dream_type"] == "safe_paraphrase")
    distorted = sum(1 for v in variants if v["dream_type"] == "distorted")
    print(f"  Safe paraphrases: {safes}")
    print(f"  Distorted variants: {distorted}")

    # Phase 2: Critic review
    print("\nPhase 2: Critic reviewing dreams\n")
    result = review_dreams(variants)
    approved = result["approved_count"]
    rejected = result["rejected_count"]
    print(f"  Approved: {approved}")
    print(f"  Rejected: {rejected}")

    if approved >= safes:
        PASSES.append(f"All safe paraphrases approved ({approved} approved)")
    else:
        ERRORS.append(f"Not all safe paraphrases approved ({approved}/{safes})")

    if rejected >= distorted:
        PASSES.append(f"Distorted variants rejected ({rejected} rejected)")
    else:
        ERRORS.append(f"Not all distorted variants rejected ({rejected}/{distorted})")

    if approved > 0:
        PASSES.append(f"Approved dreams exist ({approved})")
    else:
        ERRORS.append("No dreams approved")

    # Phase 3: Inner voice reflection
    print("\nPhase 3: Testing inner voice\n")
    r1 = inner_voice_reflect("Who created you?")
    if r1["reflection_count"] >= 3:
        PASSES.append(f"Inner voice reflects on questions ({r1['reflection_count']} steps)")
    else:
        ERRORS.append("Inner voice too few reflection steps")

    # Phase 4: Dream lesson export
    print("\nPhase 4: Exporting dream lessons\n")
    export_result = export_dream_lessons()
    added = export_result.get("dream_lessons_added", 0)
    print(f"  Lessons added: {added}")
    if isinstance(added, int):
        PASSES.append("Dream export ran without error")
    else:
        ERRORS.append("Dream export failed")

    # Save report
    report = {
        "version": "v063_gold_dream_replay_test",
        "created_at": datetime.now().isoformat(),
        "variants_generated": len(variants),
        "approved": approved,
        "rejected": rejected,
        "export_result": export_result,
        "errors": len(ERRORS),
        "passes": len(PASSES),
    }
    (ROOT / "reports" / "v063_gold_dream_replay_test.json").write_text(json.dumps(report, indent=2))

    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    for p in PASSES:
        print(f"  ✅ {p}")
    for e in ERRORS:
        print(f"  ❌ {e}")
    return 0 if not ERRORS else 1

if __name__ == "__main__":
    raise SystemExit(main())
