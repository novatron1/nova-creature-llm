"""703 — Sensory Body Layer: Device Saver"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def device_saver(selection=None):
    """Save selected device preferences to JSON."""
    prefs_path = ROOT / "data/sensory/device_preferences.json"
    if selection is None:
        return {"version": "v703_device_saver", "status": "no_selection"}
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(json.dumps(selection, indent=2))
    return {"version": "v703_device_saver", "created_at": datetime.now().isoformat(), "saved": True, "path": str(prefs_path), "status": "ok"}

def device_saver_load():
    prefs_path = ROOT / "data/sensory/device_preferences.json"
    if prefs_path.exists():
        return json.loads(prefs_path.read_text())
    return {"version": "v703_device_saver", "status": "not_found"}


def main():
    print(f"Nova v703_device_saver")
    r = device_saver()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
