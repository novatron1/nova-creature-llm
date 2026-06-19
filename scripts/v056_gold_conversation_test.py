from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(msg: str) -> str:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "src" / "v056_conversation_router.py"), "--message", msg, "--thread-id", "gold_v056"],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        timeout=30,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        raise SystemExit(proc.returncode)
    return proc.stdout

def main() -> int:
    # Reset the gold thread if possible.
    state = ROOT / "data" / "conversation_memory" / "gold_v056_state.json"
    log = ROOT / "data" / "conversation_memory" / "gold_v056_turns.jsonl"
    if state.exists():
        state.unlink()
    if log.exists():
        log.unlink()

    tests = [
        "We need conversation memory.",
        "Do that.",
        "What next?",
        "Who created you?",
        "What is my favorite color?",
    ]

    for msg in tests:
        print("USER:", msg)
        out = run(msg)
        print(out)
        print("-" * 40)

    print("PASS: v056 conversation memory gold test ran.")
    print("Check data/conversation_memory/gold_v056_state.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
