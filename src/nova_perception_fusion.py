"""Privacy-safe fusion of Nova vision, OCR, scene, and sensor observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Iterable


PERCEPTION_SCHEMA_VERSION = "1.0"
DEPTH_FRESHNESS_SECONDS = 5
_SPACE_RE = re.compile(r"\s+")
_OBJECT_RE = re.compile(
    r"\b(?:a|an|the)\s+((?:[a-z][a-z0-9-]*\s+){0,2}"
    r"(?:chair|table|hallway|door|person|people|car|vehicle|stairs?|"
    r"screen|phone|computer|dog|cat|box|wall|floor|road|sign|bottle))\b",
    re.IGNORECASE,
)
_SENSOR_CHANNELS = (
    "camera",
    "depth",
    "lidar",
    "imu",
    "odometry",
    "bumper",
    "collision",
    "proximity",
    "battery",
    "location",
)


def _bounded_text(value: Any, maximum: int) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()[:maximum]


def _unique(values: Iterable[str], maximum: int) -> tuple[str, ...]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _bounded_text(value, 160)
        key = clean.lower()
        if clean and key not in seen:
            output.append(clean)
            seen.add(key)
    return tuple(output[:maximum])


def _timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class Observation:
    """One bounded perception claim with its evidence class."""

    text: str
    basis: str
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PerceptionSnapshot:
    semantic_available: bool
    semantic_model: str
    semantic_summary: str
    ocr_texts: tuple[str, ...]
    verified_scene_facts: tuple[str, ...]
    object_observations: tuple[str, ...]
    observations: tuple[Observation, ...]
    metric_depth_available: bool
    sensor_channels: tuple[str, ...]
    unavailable_capabilities: tuple[str, ...]
    stale: bool
    schema_version: str = PERCEPTION_SCHEMA_VERSION

    def safe_trace(self) -> dict[str, object]:
        """Return operational counts only, without observed content or values."""

        return {
            "schema_version": self.schema_version,
            "semantic_available": self.semantic_available,
            "semantic_model": self.semantic_model,
            "ocr_count": len(self.ocr_texts),
            "verified_scene_fact_count": len(self.verified_scene_facts),
            "object_observation_count": len(self.object_observations),
            "metric_depth_available": self.metric_depth_available,
            "sensor_channels": list(self.sensor_channels),
            "unavailable_capabilities": list(self.unavailable_capabilities),
            "stale": self.stale,
            "image_content_logged": False,
            "sensor_values_logged": False,
        }


@dataclass(frozen=True)
class NavigationPlan:
    mode: str
    movement_authorized: bool
    hazards: tuple[str, ...]
    unknowns: tuple[str, ...]
    required_inputs: tuple[str, ...]
    suggested_observation: str
    schema_version: str = PERCEPTION_SCHEMA_VERSION

    def safe_trace(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "mode": self.mode,
            "movement_authorized": self.movement_authorized,
            "hazard_count": len(self.hazards),
            "unknown_count": len(self.unknowns),
            "required_inputs": list(self.required_inputs),
            "content_logged": False,
        }


def _scene_facts(scene_report: Any) -> tuple[str, ...]:
    if not isinstance(scene_report, dict):
        return ()
    facts: list[str] = []
    dimensions = scene_report.get("dimensions")
    if isinstance(dimensions, dict):
        width = dimensions.get("width")
        height = dimensions.get("height")
        if isinstance(width, int) and isinstance(height, int):
            facts.append(f"image dimensions {width}x{height}")
        orientation = _bounded_text(dimensions.get("orientation"), 30)
        if orientation:
            facts.append(f"image orientation {orientation}")
    appearance = (
        scene_report.get("appearance")
        if isinstance(scene_report.get("appearance"), dict)
        else scene_report
    )
    colors = appearance.get("dominant_colors")
    if isinstance(colors, list):
        names = [
            _bounded_text(item.get("name") if isinstance(item, dict) else item, 30)
            for item in colors[:5]
        ]
        names = [name for name in names if name]
        if names:
            facts.append("dominant colors " + ", ".join(names))
    lighting = _bounded_text(appearance.get("lighting"), 40)
    if lighting:
        facts.append(f"lighting {lighting}")
    return _unique(facts, 8)


def _depth_state(
    sensor_snapshot: dict[str, Any],
    now: datetime,
) -> tuple[bool, bool]:
    candidates = [
        sensor_snapshot.get(name)
        for name in ("depth", "lidar")
        if isinstance(sensor_snapshot.get(name), dict)
    ]
    stale = False
    for source in candidates:
        if not bool(source.get("available")) or not bool(source.get("calibrated")):
            continue
        observed_at = _timestamp(source.get("timestamp") or source.get("observed_at"))
        if observed_at is None:
            stale = True
            continue
        age = now - observed_at
        if timedelta(0) <= age <= timedelta(seconds=DEPTH_FRESHNESS_SECONDS):
            return True, False
        stale = True
    return False, stale


def fuse_perception(
    *,
    semantic_text: str,
    semantic_meta: dict[str, Any] | None,
    ocr_records: Iterable[dict[str, Any]],
    scene_report: dict[str, Any] | None,
    sensor_snapshot: dict[str, Any] | None,
    now: datetime | None = None,
) -> PerceptionSnapshot:
    """Fuse independent local evidence while keeping its confidence boundaries."""

    semantic_meta = semantic_meta if isinstance(semantic_meta, dict) else {}
    sensor_snapshot = sensor_snapshot if isinstance(sensor_snapshot, dict) else {}
    semantic_summary = _bounded_text(semantic_text, 2_000)
    semantic_available = bool(semantic_meta.get("used") and semantic_summary)
    semantic_model = _bounded_text(semantic_meta.get("model"), 80)

    ocr_values: list[str] = []
    observations: list[Observation] = []
    for record in list(ocr_records or ())[:32]:
        if not isinstance(record, dict):
            continue
        text = _bounded_text(record.get("text"), 300)
        if not text:
            continue
        ocr_values.append(text)
        try:
            confidence = max(0.0, min(float(record.get("confidence") or 0.0), 1.0))
        except (TypeError, ValueError):
            confidence = 0.0
        observations.append(
            Observation(text=text, basis="local_ocr", confidence=confidence)
        )

    objects = _unique(
        (match.group(1) for match in _OBJECT_RE.finditer(semantic_summary)),
        16,
    )
    observations.extend(
        Observation(
            text=item,
            basis="semantic_model_inference",
            confidence=0.65,
            metadata={"verified_detector": False},
        )
        for item in objects
    )
    facts = _scene_facts(scene_report)
    observations.extend(
        Observation(text=item, basis="deterministic_pixel_probe", confidence=0.95)
        for item in facts
    )

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    depth_available, stale = _depth_state(
        sensor_snapshot,
        current_time.astimezone(timezone.utc),
    )
    channels = tuple(
        name
        for name in _SENSOR_CHANNELS
        if sensor_snapshot.get(name) is not None
    )
    unavailable = ["physical_movement_authorization"]
    if not depth_available:
        unavailable.extend(("metric_distance", "verified_obstacle_clearance"))
    if not semantic_available:
        unavailable.append("semantic_description")

    return PerceptionSnapshot(
        semantic_available=semantic_available,
        semantic_model=semantic_model,
        semantic_summary=semantic_summary,
        ocr_texts=_unique(ocr_values, 24),
        verified_scene_facts=facts,
        object_observations=objects,
        observations=tuple(observations[:48]),
        metric_depth_available=depth_available,
        sensor_channels=channels,
        unavailable_capabilities=tuple(unavailable),
        stale=stale,
    )


def plan_safe_navigation(snapshot: PerceptionSnapshot) -> NavigationPlan:
    """Prepare observation needs without authorizing any physical motion."""

    hazard_terms = ("person", "people", "stairs", "car", "vehicle", "road")
    hazards = _unique(
        (
            item
            for item in snapshot.object_observations
            if any(term in item.lower() for term in hazard_terms)
        ),
        8,
    )
    required = []
    if not snapshot.metric_depth_available:
        required.append("fresh calibrated depth or LiDAR")
    required.extend(
        (
            "fresh obstacle and human-proximity sensing",
            "wheel odometry and IMU",
            "hardware emergency stop",
            "authenticated robot controller",
            "explicit robot.move authorization",
        )
    )
    unknowns = ["traversable floor", "hidden obstacles", "motion clearance"]
    if snapshot.stale:
        unknowns.append("current sensor state")
    return NavigationPlan(
        mode="simulation_only",
        movement_authorized=False,
        hazards=hazards,
        unknowns=tuple(unknowns),
        required_inputs=tuple(required),
        suggested_observation=(
            "Capture a fresh calibrated depth frame and full collision-sensor "
            "state, then simulate the route before requesting movement approval."
        ),
    )


__all__ = [
    "DEPTH_FRESHNESS_SECONDS",
    "NavigationPlan",
    "Observation",
    "PERCEPTION_SCHEMA_VERSION",
    "PerceptionSnapshot",
    "fuse_perception",
    "plan_safe_navigation",
]
