"""702 — Sensory Body Layer: Device Selector"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def device_selector(devices=None, preferences=None):
    """Choose default device, allow manual override if multiple exist."""
    if devices is None:
        from v701_device_scanner import device_scanner
        devices = device_scanner()
    prefs = preferences or {}
    result = {"version": "v702_device_selector", "created_at": datetime.now().isoformat(), "selected": {}, "manual_override": False}
    for dev_type in ["cameras", "microphones", "speakers"]:
        devs = devices.get(dev_type, [])
        if not devs:
            result["selected"][dev_type] = None
            continue
        saved = prefs.get(dev_type)
        if saved and any(d["id"] == saved["id"] for d in devs):
            result["selected"][dev_type] = saved
            result["manual_override"] = True
        else:
            result["selected"][dev_type] = devs[0]
    result["status"] = "ok"
    return result


def main():
    print(f"Nova v702_device_selector")
    r = device_selector()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
