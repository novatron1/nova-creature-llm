from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any

from nova_runtime.movement.models import FrozenMapping

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE = ROOT / "data" / "body_profiles" / "nova_humanoid_sim_v1.json"

PROFILE_FIELDS = {
    "profile_id",
    "execution_tier",
    "physical_output_locked",
    "mass_kg",
    "height_m",
    "joints",
    "sensors",
    "safe_zone",
}
JOINT_LIMIT_FIELDS = {"min", "max", "max_velocity"}
SAFE_ZONE_FIELDS = {"x_min", "x_max", "y_min", "y_max"}
PROFILE_NUMERIC_ABS_LIMIT = 1_000_000


def _reject_duplicate_object_pairs(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object name {key!r}")
        result[key] = value
    return result


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, int):
        return abs(value) <= PROFILE_NUMERIC_ABS_LIMIT
    return (
        math.isfinite(value)
        and abs(value) <= PROFILE_NUMERIC_ABS_LIMIT
    )


def _validate_positive_number(profile: dict[str, Any], field_name: str) -> None:
    value = profile.get(field_name)
    if not _is_finite_number(value) or value <= 0:
        raise ValueError(f"{field_name} must be a positive finite number")


def _validate_joints(profile: dict[str, Any]) -> None:
    joints = profile.get("joints")
    if not isinstance(joints, dict) or not joints:
        raise ValueError("joints must be a non-empty object")

    for joint_name, limits in joints.items():
        if not isinstance(joint_name, str) or not joint_name.strip():
            raise ValueError("joint names must be non-empty strings")
        if not isinstance(limits, dict):
            raise ValueError(f"joint {joint_name} limits must be an object")
        if set(limits) != JOINT_LIMIT_FIELDS:
            raise ValueError(
                f"joint {joint_name} schema must contain exactly "
                "min, max, and max_velocity"
            )

        for field_name in JOINT_LIMIT_FIELDS:
            if not _is_finite_number(limits[field_name]):
                raise ValueError(
                    f"joint {joint_name}.{field_name} must be a finite number"
                )
        if limits["min"] > limits["max"]:
            raise ValueError(f"joint {joint_name} min must not exceed max")
        if limits["max_velocity"] <= 0:
            raise ValueError(
                f"joint {joint_name} max_velocity must be greater than zero"
            )


def _validate_sensors(profile: dict[str, Any]) -> None:
    sensors = profile.get("sensors")
    if (
        not isinstance(sensors, list)
        or not sensors
        or any(
            not isinstance(sensor, str) or not sensor.strip()
            for sensor in sensors
        )
    ):
        raise ValueError("sensors must be a non-empty array of non-empty strings")


def _validate_safe_zone(profile: dict[str, Any]) -> None:
    safe_zone = profile.get("safe_zone")
    if not isinstance(safe_zone, dict):
        raise ValueError("safe_zone must be an object")
    if set(safe_zone) != SAFE_ZONE_FIELDS:
        raise ValueError(
            "safe_zone schema must contain exactly "
            "x_min, x_max, y_min, and y_max"
        )
    for field_name in SAFE_ZONE_FIELDS:
        if not _is_finite_number(safe_zone[field_name]):
            raise ValueError(
                f"safe_zone.{field_name} must be a finite number"
            )
    if safe_zone["x_min"] >= safe_zone["x_max"]:
        raise ValueError("safe_zone x_min must be less than x_max")
    if safe_zone["y_min"] >= safe_zone["y_max"]:
        raise ValueError("safe_zone y_min must be less than y_max")


def _validate_profile(profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        raise ValueError("Body profile root must be an object")

    profile_id = profile.get("profile_id")
    if not isinstance(profile_id, str) or not profile_id.strip():
        raise ValueError("profile_id must be a non-empty string")
    if profile.get("execution_tier") != "simulation":
        raise ValueError("execution_tier must be simulation")
    if profile.get("physical_output_locked") is not True:
        raise ValueError("physical_output_locked must be literal true")

    _validate_positive_number(profile, "mass_kg")
    _validate_positive_number(profile, "height_m")
    _validate_joints(profile)
    _validate_sensors(profile)
    _validate_safe_zone(profile)

    if set(profile) != PROFILE_FIELDS:
        raise ValueError(
            "Body profile schema must contain exactly "
            + ", ".join(sorted(PROFILE_FIELDS))
        )
    return profile


def load_body_profile(
    path: str | os.PathLike[str] | Path = DEFAULT_PROFILE,
) -> FrozenMapping:
    profile_path = Path(path)
    try:
        text = profile_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Invalid body profile encoding in {profile_path}: {exc}"
        ) from exc
    try:
        profile = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_object_pairs,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid body profile JSON in {profile_path}: {exc.msg}"
        ) from exc
    except ValueError as exc:
        raise ValueError(
            f"Invalid body profile JSON in {profile_path}: {exc}"
        ) from exc

    try:
        validated = _validate_profile(profile)
    except ValueError as exc:
        raise ValueError(
            f"Invalid body profile schema in {profile_path}: {exc}"
        ) from exc
    return FrozenMapping(validated)
