from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from datetime import datetime
import json

PATCH_ROOT = Path(__file__).resolve().parents[1]

FILES = [
    ("src/conversation_memory.py", "src/conversation_memory.py"),
    ("src/v056_conversation_router.py", "src/v056_conversation_router.py"),
    ("scripts/v056_chat_once.py", "scripts/v056_chat_once.py"),
    ("scripts/v056_gold_conversation_test.py", "scripts/v056_gold_conversation_test.py"),
    ("scripts/check_v056_conversation_memory.py", "scripts/check_v056_conversation_memory.py"),
    ("docs/V056_CONVERSATION_MEMORY.md", "docs/V056_CONVERSATION_MEMORY.md"),
    ("tests/test_v056_conversation_memory.py", "tests/test_v056_conversation_memory.py"),
]

def backup_if_exists(path: Path):
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(path.name + f".v056_backup_{stamp}")
        shutil.copy2(path, backup)

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-root", default=".")
    args = ap.parse_args()

    project = Path(args.project_root).resolve()
    print("Applying v056 conversation memory loop")
    print("Project root:", project)

    for src_rel, dst_rel in FILES:
        src = PATCH_ROOT / src_rel
        dst = project / dst_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        backup_if_exists(dst)
        shutil.copy2(src, dst)

    (project / "data" / "conversation_memory").mkdir(parents=True, exist_ok=True)
    (project / "reports").mkdir(exist_ok=True)

    status = {
        "version": "v056_conversation_memory_loop",
        "installed_at": datetime.now().isoformat(),
        "installed_files": [dst for _, dst in FILES],
    }
    (project / "reports" / "v056_conversation_memory_install_status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")

    print("PASS: v056 installed.")
    print("Next:")
    print("python scripts/check_v056_conversation_memory.py")
    print("python scripts/v056_gold_conversation_test.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
