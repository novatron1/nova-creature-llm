"""v763_social_context_logger — Natural People Memory Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re
ROOT = Path(__file__).resolve().parents[1]

def social_context_logger(person_id=None, context=None):
    """Log social context of person encounters."""
    ctx_path = ROOT / "data/people/social_context.jsonl"
    ctx_path.parent.mkdir(parents=True, exist_ok=True)
    if person_id and context:
        entry = {"person_id": person_id, "context": context, "timestamp": datetime.now().isoformat()}
        with open(ctx_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"version": "v763_social_context_logger", "logged": entry, "status": "ok"}
    logs = []
    if ctx_path.exists():
        with open(ctx_path) as f:
            for line in f:
                line = line.strip()
                if line: logs.append(json.loads(line))
    return {"version": "v763_social_context_logger", "logs": logs[-50:], "count": len(logs), "status": "ok"}


def main():
    import sys
    print(f"Nova v763_social_context_logger")
    r = social_context_logger()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
