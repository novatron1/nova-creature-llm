from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(cmd):
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=30)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout

def main() -> int:
    print("Adding approved dictionary lesson...")
    run([sys.executable, "scripts/v057_add_dictionary_lesson.py", "--question", "What is the v057 system?", "--answer", "Dictionary plus conversation memory.", "--approve"])

    print("Testing dictionary exact hit...")
    out1 = run([sys.executable, "scripts/v057_chat_once.py", "--message", "What is the v057 system?", "--thread-id", "gold_v057"])
    assert "Dictionary plus conversation memory" in out1
    assert "Dictionary found: True" in out1

    print("Testing fallback to conversation/router...")
    out2 = run([sys.executable, "scripts/v057_chat_once.py", "--message", "We need conversation memory.", "--thread-id", "gold_v057"])
    assert "Route:" in out2

    print("PASS: v057 dictionary gold test completed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
