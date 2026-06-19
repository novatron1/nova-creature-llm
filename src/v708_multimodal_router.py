"""708 — Sensory Body Layer: Multimodal Router"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid
ROOT = Path(__file__).resolve().parents[1]


def multimodal_router(source_type, detected_signal=None):
    """Route sensory inputs to appropriate brain roles."""
    routes = {
        "camera": ["right_hemisphere", "memory_transformer"],
        "face": ["right_hemisphere", "memory_transformer"],
        "hand": ["right_hemisphere"],
        "body_pose": ["right_hemisphere"],
        "microphone": ["memory_transformer", "planner_transformer"],
        "hearing": ["memory_transformer", "planner_transformer"],
        "speaker": ["speech_output_transformer"],
        "screen": ["left_hemisphere", "right_hemisphere"],
        "screenshot": ["left_hemisphere", "right_hemisphere"],
        "image": ["right_hemisphere", "memory_transformer"],
        "audio": ["memory_transformer", "planner_transformer"],
        "unknown": ["critic_conscience_transformer"],
    }
    route = routes.get(source_type, routes["unknown"])
    result = {
        "version": "v708_multimodal_router",
        "created_at": datetime.now().isoformat(),
        "source_type": source_type,
        "detected_signal": detected_signal or "none",
        "routes": route,
        "primary_route": route[0] if route else "unknown",
        "status": "ok"
    }
    return result


def main():
    print(f"Nova v708_multimodal_router")
    r = multimodal_router()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
