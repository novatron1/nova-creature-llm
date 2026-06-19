from __future__ import annotations

from pathlib import Path
import sys

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = []
    for rel in [
        "src/dictionary_memory.py",
        "src/v057_dictionary_conversation_router.py",
        "data/dictionary_memory/approved_answer_dictionary.json",
        "data/dictionary_memory/pending_dictionary_lessons.jsonl",
        "data/dictionary_memory/dictionary_hits.jsonl",
    ]:
        if not (root / rel).exists():
            missing.append(rel)

    print("Nova Creature v057 Dictionary Memory Check")
    print("Project root:", root)
    print()

    if missing:
        print("FAIL missing:")
        for m in missing:
            print(" -", m)
        return 1

    print("PASS: v057 dictionary memory files are installed.")
    print()
    print("Run:")
    print('python scripts/v057_gold_dictionary_test.py')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
