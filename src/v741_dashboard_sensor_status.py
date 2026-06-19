"""741 — Sensory Body Layer: Dashboard Sensor Status"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def dashboard_sensor_status():
    """Display status of all sensors."""
    result = {"version": "v741_dashboard_sensor_status", "created_at": datetime.now().isoformat(),
              "sensors": {}, "status": "ok"}
    try:
        from v711_camera_discovery import camera_discovery
        cams = camera_discovery()
        result["sensors"]["camera"] = {"available": len(cams.get("cameras", [])) > 0, "count": len(cams.get("cameras", [])), "devices": cams["cameras"]}
    except Exception as e:
        result["sensors"]["camera"] = {"available": False, "error": str(e)}
    try:
        from v721_mic_discovery import mic_discovery
        mics = mic_discovery()
        result["sensors"]["microphone"] = {"available": len(mics.get("microphones", [])) > 0, "count": len(mics.get("microphones", [])), "devices": mics["microphones"]}
    except Exception as e:
        result["sensors"]["microphone"] = {"available": False, "error": str(e)}
    try:
        from v726_speaker_discovery import speaker_discovery
        spks = speaker_discovery()
        result["sensors"]["speaker"] = {"available": len(spks.get("speakers", [])) > 0, "count": len(spks.get("speakers", [])), "devices": spks["speakers"]}
    except Exception as e:
        result["sensors"]["speaker"] = {"available": False, "error": str(e)}
    try:
        from v731_screen_capture_discovery import screen_capture_discovery
        scrs = screen_capture_discovery()
        result["sensors"]["screen"] = {"available": len(scrs.get("monitors", [])) > 0, "count": len(scrs.get("monitors", [])), "devices": scrs["monitors"]}
    except Exception as e:
        result["sensors"]["screen"] = {"available": False, "error": str(e)}
    return result


def main():
    print(f"Nova v741_dashboard_sensor_status")
    r = dashboard_sensor_status()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
