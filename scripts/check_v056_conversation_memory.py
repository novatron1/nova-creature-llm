from __future__ import annotations

from pathlib import Path

REQUIRED = [
    "src/conversation_memory.py",
    "src/v056_conversation_router.py",
    "scripts/v056_chat_once.py",
    "scripts/v056_gold_conversation_test.py",
    "data/conversation_memory",
]

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = []
    for rel in REQUIRED:
        p = root / rel
        if not p.exists():
            missing.append(rel)

    print("Nova Creature v056 Conversation Memory Check")
    print("Project root:", root)
    print()

    if missing:
        print("FAIL missing:")
        for m in missing:
            print(" -", m)
        return 1

    print("PASS: v056 conversation memory files are installed.")
    print()
    print("Run:")
    print('python scripts/v056_gold_conversation_test.py')
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
