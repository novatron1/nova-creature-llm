"""701 — Sensory Body Layer: Device Scanner"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def device_scanner():
    """Scan available cameras, microphones, and speakers."""
    import json
    result = {
        "version": "v701_device_scanner",
        "created_at": datetime.now().isoformat(),
        "cameras": [],
        "microphones": [],
        "speakers": [],
        "mock_mode": True,
        "status": "ok"
    }
    try:
        import cv2
        for i in range(10):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                result["cameras"].append({"id": i, "name": f"Camera {i}", "available": True})
                cap.release()
    except Exception:
        result["cameras"] = [{"id": 0, "name": "Mock Camera", "available": True, "mock": True}]
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                result["microphones"].append({"id": i, "name": info["name"], "available": True})
            if info["maxOutputChannels"] > 0:
                result["speakers"].append({"id": i, "name": info["name"], "available": True})
        p.terminate()
    except Exception:
        result["microphones"] = [{"id": 0, "name": "Mock Microphone", "available": True, "mock": True}]
        result["speakers"] = [{"id": 0, "name": "Mock Speaker", "available": True, "mock": True}]
    return result


def main():
    print(f"Nova v701_device_scanner")
    r = device_scanner()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
