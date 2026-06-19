from __future__ import annotations

from pathlib import Path

def main() -> int:
    root = Path(__file__).resolve().parents[1]
    missing = []
    for rel in [
        "src/dictionary_to_training.py",
        "scripts/v058_export_dictionary_to_training.py",
        "exports/v053_training_sets",
    ]:
        if not (root / rel).exists():
            missing.append(rel)

    print("Nova Creature v058 Dictionary-To-Transformer Check")
    print("Project root:", root)
    print()

    if missing:
        print("FAIL missing:")
        for m in missing:
            print(" -", m)
        return 1

    print("PASS: v058 dictionary-to-transformer bridge is installed.")
    print()
    print("Run:")
    print("python scripts/v058_export_dictionary_to_training.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
