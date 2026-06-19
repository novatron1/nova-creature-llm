"""v804_unified_memory_bridge — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def unified_memory_bridge(source="", data=None):
    """Connect all memory systems."""
    now = datetime.now().isoformat()
    if source and data:
        memory_id = f"mem_{now[:10]}_{uuid.uuid4().hex[:6]}"
        record = {
            "memory_id": memory_id,
            "source": source,
            "timestamp": now,
            "confidence": data.get("confidence", 0.5),
            "linked_subsystem": data.get("subsystem", "unknown"),
            "route": data.get("route", "memory_transformer"),
            "status": data.get("status", "stored"),
            **data
        }
        log_path = ROOT / "data/integration/memory_bridge.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        return {"version": "v804_unified_memory_bridge", "memory_id": memory_id, "stored": True, "status": "ok"}
    # List recent memories
    memories = []
    log_path = ROOT / "data/integration/memory_bridge.jsonl"
    if log_path.exists():
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line: memories.append(json.loads(line))
    return {"version": "v804_unified_memory_bridge", "memories": memories[-30:], "count": len(memories), "status": "ok"}


def main():
    print(f"Nova v804_unified_memory_bridge")
    r = unified_memory_bridge()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
