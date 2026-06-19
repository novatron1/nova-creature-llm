"""709 — Sensory Body Layer: Sensory Config"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


SENSORY_CONFIG = {
    "auto_discovery": True,
    "auto_select_default": True,
    "manual_override_allowed": True,
    "mock_mode": True,
    "save_preferences": True,
    "log_all_events": True,
    "max_memory_events": 1000,
    "dashboard_refresh_seconds": 1.0,
}

def sensory_config(config_update=None):
    """Get or update sensory configuration."""
    global SENSORY_CONFIG
    if config_update:
        SENSORY_CONFIG.update(config_update)
        _save_config()
    return {"version": "v709_sensory_config", "config": dict(SENSORY_CONFIG), "status": "ok"}

def _save_config():
    p = ROOT / "data/sensory/sensory_config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(SENSORY_CONFIG, indent=2))


def main():
    print(f"Nova v709_sensory_config")
    r = sensory_config()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
