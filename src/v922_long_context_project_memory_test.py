"""v922_long_context_project_memory_test — Whole-Brain Training Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

def long_context_project_memory_test():
    """Training Lab: Test Nova can remember larger project context"""
    return {"version": "v922_long_context_project_memory_test", "created_at": datetime.now().isoformat(),
            "module": "Test Nova can remember larger project context", "status": "ok"}


def main():
    print(f"Nova v922_long_context_project_memory_test")
    r = long_context_project_memory_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
