from __future__ import annotations

from copy import deepcopy
from threading import RLock
from typing import Any


DEFAULT_STATE: dict[str, Any] = {
    "active_tab": "home",
    "body_mode": "neutral",
    "movement_status": "idle",
    "active_motion": None,
    "execution_tier": "avatar",
    "physical_output_locked": True,
    "mic": False,
    "camera": False,
    "speaker": False,
    "private_mode": False,
}


class RuntimeState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._data = deepcopy(DEFAULT_STATE)

    def update(self, **changes: Any) -> dict[str, Any]:
        with self._lock:
            self._data.update(changes)
            return deepcopy(self._data)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def stop_all(self) -> dict[str, Any]:
        return self.update(
            body_mode="neutral",
            movement_status="idle",
            active_motion=None,
            mic=False,
            camera=False,
            speaker=False,
        )
