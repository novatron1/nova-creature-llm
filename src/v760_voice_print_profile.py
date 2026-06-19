"""v760_voice_print_profile — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def voice_print_profile(voice_data=None, person_id=None):
    """Create or match voice print for person profiles."""
    import hashlib
    voice_path = ROOT / "data/people/voice_prints.jsonl"
    voice_path.parent.mkdir(parents=True, exist_ok=True)
    if voice_data and person_id:
        voice_hash = hashlib.md5(str(voice_data).encode()).hexdigest()[:16]
        entry = {"person_id": person_id, "voice_hash": voice_hash, "created_at": datetime.now().isoformat()}
        with open(voice_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"version": "v760_voice_print_profile", "voice_hash": voice_hash, "person_id": person_id, "status": "ok"}
    prints = []
    if voice_path.exists():
        with open(voice_path) as f:
            for line in f:
                line = line.strip()
                if line: prints.append(json.loads(line))
    return {"version": "v760_voice_print_profile", "voice_prints": prints, "count": len(prints), "status": "ok"}


def main():
    import sys
    print(f"Nova v760_voice_print_profile")
    r = voice_print_profile()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
