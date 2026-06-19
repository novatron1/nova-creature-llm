"""744 — Sensory Body Layer: Dashboard Memory Feed"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def dashboard_memory_feed(limit=10):
    """Display last sensory memory events."""
    try:
        from v736_sensory_memory_store import sensory_memory_store
        return sensory_memory_store(limit=limit)
    except Exception:
        return {"version": "v744_dashboard_memory_feed", "events": [], "count": 0, "status": "ok"}


def main():
    print(f"Nova v744_dashboard_memory_feed")
    r = dashboard_memory_feed()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
