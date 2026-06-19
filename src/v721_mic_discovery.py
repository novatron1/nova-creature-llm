"""721 — Sensory Body Layer: Mic Discovery"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def mic_discovery():
    """Discover available microphones."""
    result = {"version": "v721_mic_discovery", "created_at": datetime.now().isoformat(), "microphones": [], "status": "ok"}
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0:
                result["microphones"].append({"id": i, "name": info["name"], "channels": info["maxInputChannels"], "rate": int(info["defaultSampleRate"])})
        p.terminate()
        result["mock_mode"] = False
    except Exception:
        result["microphones"] = [{"id": 0, "name": "Mock Microphone", "channels": 1, "rate": 16000, "mock": True}]
    return result


def main():
    print(f"Nova v721_mic_discovery")
    r = mic_discovery()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
