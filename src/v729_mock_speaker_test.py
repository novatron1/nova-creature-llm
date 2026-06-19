"""729 — Sensory Body Layer: Mock Speaker Test"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def mock_speaker_test(phrase="Hello, I am Nova. My sensory body is active."):
    """Mock speaker output test."""
    return {"version": "v729_mock_speaker_test", "created_at": datetime.now().isoformat(),
            "phrase": phrase, "output": "mock_audio_data", "mock_mode": True,
            "test_passed": True, "status": "ok"}


def main():
    print(f"Nova v729_mock_speaker_test")
    r = mock_speaker_test()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
