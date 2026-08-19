"""Replaceable multimodal, robot, and game engine contracts.

No engine is silently treated as available. Required implementations must pass
registration health; optional configured engines may remain discoverable as
unavailable so Nova can report exactly what is missing without routing work to
them.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any

from .errors import ProviderUnavailableError


ENGINE_INTERFACE_VERSION = "1.0"


class NovaEngine(ABC):
    engine_id = "engine"
    engine_type = "generic"
    local_or_remote = "local"
    cost_type = "free"

    @abstractmethod
    def health_check(self) -> dict[str, Any]: ...

    def estimate_cost(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"estimated_cost": 0.0, "currency": "USD", "cost_type": self.cost_type, "estimated": True}


class NovaVisionEngine(NovaEngine):
    engine_type = "vision"

    @abstractmethod
    def analyze_image(self, image: Any, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def describe_image(self, image: Any, **options: Any) -> str: ...
    @abstractmethod
    def extract_visual_features(self, image: Any, **options: Any) -> dict[str, Any]: ...


class NovaImageGenerationEngine(NovaEngine):
    engine_type = "image_generation"

    @abstractmethod
    def generate_image(self, prompt: str, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def edit_image(self, image: Any, prompt: str, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def upscale_image(self, image: Any, **options: Any) -> dict[str, Any]: ...


class NovaVideoGenerationEngine(NovaEngine):
    engine_type = "video_generation"

    @abstractmethod
    def text_to_video(self, prompt: str, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def image_to_video(self, image: Any, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def extend_video(self, video: Any, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def interpolate_video(self, video: Any, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def job_status(self, job_id: str) -> dict[str, Any]: ...
    @abstractmethod
    def cancel_job(self, job_id: str) -> bool: ...


class NovaSpeechEngine(NovaEngine):
    engine_type = "speech"

    @abstractmethod
    def transcribe(self, audio: Any, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def synthesize(self, text: str, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def detect_speech(self, audio: Any, **options: Any) -> dict[str, Any]: ...


class NovaRobotEngine(NovaEngine):
    engine_type = "robot"

    @abstractmethod
    def observe(self, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def get_sensor_state(self) -> dict[str, Any]: ...
    @abstractmethod
    def move(self, command: dict[str, Any]) -> dict[str, Any]: ...
    @abstractmethod
    def stop(self) -> dict[str, Any]: ...


class NovaGameEngine(NovaEngine):
    engine_type = "game"

    @abstractmethod
    def observe_state(self, **options: Any) -> dict[str, Any]: ...
    @abstractmethod
    def recommend_action(self, state: dict[str, Any]) -> dict[str, Any]: ...
    @abstractmethod
    def perform_action(self, action: dict[str, Any]) -> dict[str, Any]: ...
    @abstractmethod
    def pause(self) -> dict[str, Any]: ...
    @abstractmethod
    def stop(self) -> dict[str, Any]: ...


class NovaEngineRegistry:
    def __init__(self) -> None:
        self._engines: dict[str, NovaEngine] = {}
        self._lock = RLock()

    def register(self, engine: NovaEngine) -> None:
        health = engine.health_check()
        if not health.get("ok"):
            raise ProviderUnavailableError(f"Engine {engine.engine_id!r} failed registration health check.")
        with self._lock:
            self._engines[engine.engine_id] = engine

    def register_optional(self, engine: NovaEngine) -> None:
        """Register a configured extension without claiming it is available."""
        with self._lock:
            self._engines[engine.engine_id] = engine

    def unregister(self, engine_id: str) -> None:
        with self._lock:
            self._engines.pop(engine_id, None)

    def get(self, engine_id: str) -> NovaEngine:
        with self._lock:
            engine = self._engines.get(engine_id)
        if engine is None:
            raise ProviderUnavailableError(f"Nova engine {engine_id!r} is not registered.")
        return engine

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            values = list(self._engines.values())
        return [
            {
                "engine_id": item.engine_id, "engine_type": item.engine_type,
                "local_or_remote": item.local_or_remote, "cost_type": item.cost_type,
                "interface_version": ENGINE_INTERFACE_VERSION, "health": item.health_check(),
            }
            for item in values
        ]

    def health_check(self) -> dict[str, Any]:
        engines = self.list()
        available = sum(1 for item in engines if item["health"].get("ok"))
        return {
            "ok": True,
            "registered": len(engines),
            "available": available,
            "unavailable": len(engines) - available,
            "engines": engines,
            "note": "Optional unavailable engines do not make Nova Core unhealthy.",
        }
