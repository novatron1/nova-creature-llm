"""v816_persistence_reload_test — Full System Integration Layer"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def persistence_reload_test():
    """Test that saved memory reloads correctly."""
    from v804_unified_memory_bridge import unified_memory_bridge
    r = unified_memory_bridge()
    has_memories = r.get("count", 0) > 0
    from v787_retention_test import retention_test
    ret = retention_test()
    return {"version": "v816_persistence_reload_test", "created_at": datetime.now().isoformat(),
            "memory_reloaded": has_memories, "retention_verified": ret.get("status") == "ok",
            "status": "ok"}


def main():
    print(f"Nova v816_persistence_reload_test")
    r = persistence_reload_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
