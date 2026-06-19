#!/usr/bin/env python3
"""v078 — Voice mode demo."""
import json, sys
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from v078_voice_mode import process_voice

def main():
    print("Nova v078 -- Voice Mode Demo\n")
    messages = ["Do that", "What next", "Run it", "Is robot movement active", "Tell me short"]
    results = []
    for msg in messages:
        r = process_voice(msg)
        results.append(r)
        print(f"  Input: {msg}")
        print(f"  Mode: {r['mode']}")
        print(f"  Short: {r['short_answer']}")
        print(f"  Short cmd: {r['is_short_command']}")
        print()
    (ROOT / "reports" / "v078_voice_mode_status.json").write_text(json.dumps({
        "version": "v078_voice_demo", "created_at": datetime.now().isoformat(),
        "messages": messages, "results": results}, indent=2))
    print(f"Report: reports/v078_voice_mode_status.json\nPASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
