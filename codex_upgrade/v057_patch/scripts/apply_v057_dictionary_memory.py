from __future__ import annotations

import argparse
import shutil
import json
from pathlib import Path
from datetime import datetime

PATCH_ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ("src/dictionary_memory.py", "src/dictionary_memory.py"),
    ("src/v057_dictionary_conversation_router.py", "src/v057_dictionary_conversation_router.py"),
    ("scripts/check_v057_dictionary_memory.py", "scripts/check_v057_dictionary_memory.py"),
    ("scripts/v057_chat_once.py", "scripts/v057_chat_once.py"),
    ("scripts/v057_add_dictionary_lesson.py", "scripts/v057_add_dictionary_lesson.py"),
    ("scripts/v057_gold_dictionary_test.py", "scripts/v057_gold_dictionary_test.py"),
    ("docs/V057_DICTIONARY_MEMORY.md", "docs/V057_DICTIONARY_MEMORY.md"),
    ("tests/test_v057_dictionary_memory.py", "tests/test_v057_dictionary_memory.py"),
]

def backup_if_exists(path: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(path.name + f".v057_backup_{stamp}")
        shutil.copy2(path, backup)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()

    project = Path(args.project_root).resolve()
    print("Applying v057 dictionary memory bridge")
    print("Project root:", project)

    for src_rel, dst_rel in FILES:
        src = PATCH_ROOT / src_rel
        dst = project / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        backup_if_exists(dst)
        shutil.copy2(src, dst)

    mem_dir = project / "data" / "dictionary_memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    approved = mem_dir / "approved_answer_dictionary.json"
    if not approved.exists():
        approved.write_text(json.dumps({
            "who created you": "Mr. Novotron.",
            "who made you": "Mr. Novotron.",
            "who built you": "Mr. Novotron.",
            "who are you": "Nova Creature.",
            "what is your name": "Nova Creature.",
            "can you browse": "No.",
            "what is 12 times 12": "144."
        }, indent=2), encoding="utf-8")

    for fn in ["pending_dictionary_lessons.jsonl", "dictionary_hits.jsonl"]:
        p = mem_dir / fn
        if not p.exists():
            p.write_text("", encoding="utf-8")

    (project / "reports").mkdir(exist_ok=True)
    (project / "reports" / "v057_dictionary_memory_install_status.json").write_text(json.dumps({
        "version": "v057_dictionary_memory_bridge",
        "installed_at": datetime.now().isoformat(),
        "files": [dst for _, dst in FILES],
    }, indent=2), encoding="utf-8")

    print("PASS: v057 installed.")
    print("Next:")
    print("python scripts/check_v057_dictionary_memory.py")
    print("python scripts/v057_gold_dictionary_test.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
