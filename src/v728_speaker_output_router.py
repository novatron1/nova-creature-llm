"""728 — Sensory Body Layer: Speaker Output Router"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def speaker_output_router(text=None, role_brain="speech_output_transformer"):
    """Route voice output through speech_output_transformer."""
    if text is None:
        return {"version": "v728_speaker_output_router", "created_at": datetime.now().isoformat(),
                "routed_to": role_brain, "status": "idle"}
    result = {"version": "v728_speaker_output_router", "created_at": datetime.now().isoformat(),
              "text": text, "routed_to": role_brain, "spoken": True,
              "mock_mode": True, "status": "ok"}
    return result


def main():
    print(f"Nova v728_speaker_output_router")
    r = speaker_output_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
