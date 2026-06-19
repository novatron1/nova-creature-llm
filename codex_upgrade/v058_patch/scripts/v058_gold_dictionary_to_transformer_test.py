from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def ensure_dictionary():
    d = ROOT / "data" / "dictionary_memory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "approved_answer_dictionary.json"
    if not p.exists():
        p.write_text(json.dumps({
            "who created you": "Mr. Novotron.",
            "what is 12 times 12": "144.",
            "what is the v058 system": "Dictionary lessons exported into transformer training sets.",
            "what is my favorite color": "I do not know."
        }, indent=2), encoding="utf-8")
    else:
        data = json.loads(p.read_text(encoding="utf-8"))
        data["what is the v058 system"] = "Dictionary lessons exported into transformer training sets."
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")

def main() -> int:
    ensure_dictionary()
    proc = subprocess.run([sys.executable, "scripts/v058_export_dictionary_to_training.py"], cwd=str(ROOT), text=True, capture_output=True, timeout=30)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        return proc.returncode

    summary_path = ROOT / "exports" / "v058_dictionary_training" / "v058_dictionary_export_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["dictionary_entries_seen"] >= 1
    assert sum(summary["training_set_counts"].values()) >= 1

    print("PASS: v058 gold dictionary-to-transformer test completed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
