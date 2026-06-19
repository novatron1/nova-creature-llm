"""v776_learning_intake — Rapid Education Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def learning_intake(source="text", content="", metadata=None):
    """Accept learning input from multiple sources."""
    now = datetime.now().isoformat()
    intake_id = f"li_{now[:10]}_{uuid.uuid4().hex[:6]}"
    entry = {
        "intake_id": intake_id,
        "source": source,
        "content": content,
        "metadata": metadata or {},
        "received_at": now,
        "status": "received"
    }
    log_path = ROOT / "data/rapid_learning/intake_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return {"version": "v776_learning_intake", "created_at": now,
            "intake_id": intake_id, "source": source, "content_length": len(content),
            "status": "ok"}


def main():
    print(f"Nova v776_learning_intake")
    r = learning_intake()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
