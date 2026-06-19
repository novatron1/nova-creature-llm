"""726 — Sensory Body Layer: Speaker Discovery"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def speaker_discovery():
    """Discover available speaker/audio output devices."""
    result = {"version": "v726_speaker_discovery", "created_at": datetime.now().isoformat(), "speakers": [], "status": "ok"}
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info["maxOutputChannels"] > 0:
                result["speakers"].append({"id": i, "name": info["name"], "channels": info["maxOutputChannels"], "rate": int(info["defaultSampleRate"])})
        p.terminate()
        result["mock_mode"] = False
    except Exception:
        result["speakers"] = [{"id": 0, "name": "Mock Speaker", "channels": 2, "rate": 44100, "mock": True}]
    return result


def main():
    print(f"Nova v726_speaker_discovery")
    r = speaker_discovery()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
