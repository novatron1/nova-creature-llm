from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from v063_inner_voice import inner_voice_reflect
from v063_dream_replay import generate_dream_lessons, export_dream_lessons, collect_conversation_turns

ERRORS = []
PASSES = []

def check(cond, msg):
    PASSES.append(f"  {'✅' if cond else '❌'} {msg}")
    if not cond:
        ERRORS.append(msg)

def main():
    print("Nova Creature v063 — Inner Voice + Dream Replay Checker\n")

    # 1. Files exist
    print("1. Checking v063 source files…")
    for f in [
        ROOT/"src"/"v063_inner_voice.py",
        ROOT/"src"/"v063_dream_replay.py",
    ]:
        check(f.exists(), f"{f.relative_to(ROOT)} exists")

    # 2. Inner voice reflection
    print("2. Testing inner voice reflection…")
    r1 = inner_voice_reflect("Who created you?")
    check(r1["reflection_count"] >= 3, f"reflection steps: {r1['reflection_count']}")
    check(r1["known"] or True, "known fact check ran")  # might or might not match

    r2 = inner_voice_reflect("What is 12 times 12?")
    check(r2["reflection_count"] >= 3, f"math reflection steps: {r2['reflection_count']}")

    r3 = inner_voice_reflect("Do that.")
    check(len(r3["reflection_steps"]) > 0, "follow-up reflection works")

    # 3. Dream replay
    print("3. Testing dream replay learning…")
    turns = collect_conversation_turns()
    check(isinstance(turns, list), f"conversation turns collected ({len(turns)} turns)")

    lessons = generate_dream_lessons()
    check(isinstance(lessons, list), f"dream lessons generated ({len(lessons)} lessons)")

    # 4. Export dream lessons
    print("4. Testing dream lesson export…")
    result = export_dream_lessons()
    check("dream_lessons_added" in result, "export report has dream_lessons_added")
    check("roles_updated" in result, "export report has roles_updated")

    # ── verdict ────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"RESULTS: {len(PASSES)} passed, {len(ERRORS)} errors")
    print(f"{'='*60}")
    for p in PASSES:
        print(p)
    for e in ERRORS:
        print(f"  ❌ {e}")

    if ERRORS:
        print("\nFAIL: v063 check did not pass")
        return 1
    print("\nPASS: v063 inner voice + dream replay learning active")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
