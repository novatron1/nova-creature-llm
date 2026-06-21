from __future__ import annotations

from collections.abc import Mapping
import dataclasses as _dataclasses
from dataclasses import asdict, dataclass, field
import math
from types import GeneratorType
from typing import Any, Literal

ExecutionTier = Literal["avatar", "simulation", "shadow", "physical"]
MovementSource = Literal["owner", "task", "self", "safety"]

MOVEMENT_SOURCES = ("owner", "task", "self", "safety")
EXECUTION_TIERS = ("avatar", "simulation", "shadow", "physical")
MAX_CONTAINER_ITEMS = 10_000
MAX_NESTING_DEPTH = 64
MIN_JSON_INTEGER = -(2**63)
MAX_JSON_INTEGER = 2**63 - 1
MOTION_NUMERIC_ABS_LIMIT = 1_000_000
MAX_DURATION_MS = 2**31 - 1


class _AsdictEntry(tuple):
    __slots__ = ()

    def __new__(cls, key: str, value: Any) -> _AsdictEntry:
        return tuple.__new__(cls, (key, value))


class _FrozenKey(str):
    __slots__ = ("_value",)

    def __new__(cls, key: str, value: Any) -> _FrozenKey:
        instance = str.__new__(cls, key)
        instance._value = value
        return instance

    def __deepcopy__(self, memo: dict[int, Any]) -> _AsdictEntry:
        # Python 3.11 dataclasses.asdict treats tuple subclasses as
        # sequences before consulting the mapping's __deepcopy__ method.
        detached = _AsdictEntry(str(self), thaw_value(self._value))
        memo[id(self)] = detached
        return detached


class FrozenMapping(tuple, Mapping[str, Any]):
    __slots__ = ()

    def __new__(
        cls,
        values: Any = None,
        *,
        _path: str = "value",
        _active: set[int] | None = None,
        _depth: int = 0,
    ) -> FrozenMapping:
        if values is None:
            source: Mapping[Any, Any] = {}
        elif isinstance(values, Mapping):
            source = values
        else:
            asdict_result = _consume_asdict_entries(values)
            if asdict_result is not None:
                return asdict_result
            raise TypeError(f"{_path} must be a mapping")

        _validate_container_limits(len(source), _path, _depth)

        active = set() if _active is None else _active
        identity = id(source)
        if identity in active:
            raise ValueError(f"Reference cycle detected at {_path}")
        active.add(identity)
        try:
            frozen: list[tuple[str, Any]] = []
            for index, (key, value) in enumerate(source.items()):
                if index >= MAX_CONTAINER_ITEMS:
                    raise ValueError(
                        f"{_path} exceeds the maximum container size "
                        f"of {MAX_CONTAINER_ITEMS}"
                    )
                if not isinstance(key, str):
                    raise TypeError(
                        f"{_path} mappings require string keys; got {key!r}"
                    )
                frozen.append(
                    (
                        key,
                        freeze_value(
                            value,
                            path=f"{_path}.{key}",
                            _active=active,
                            _depth=_depth + 1,
                        ),
                    )
                )
        finally:
            active.remove(identity)
        frozen.sort(key=lambda item: item[0])
        return tuple.__new__(cls, frozen)

    def __init__(
        self,
        values: Mapping[str, Any] | None = None,
        *,
        _path: str = "value",
        _active: set[int] | None = None,
        _depth: int = 0,
    ) -> None:
        pass

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("FrozenMapping cannot be subclassed")

    def __getitem__(self, key: str) -> Any:
        for candidate, value in tuple.__iter__(self):
            if candidate == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        for key, value in tuple.__iter__(self):
            yield _FrozenKey(key, value)

    def __len__(self) -> int:
        return tuple.__len__(self)

    def __repr__(self) -> str:
        values = {
            key: value
            for key, value in tuple.__iter__(self)
        }
        return f"{type(self).__name__}({values!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return self.to_dict() == thaw_value(other)

    def __ne__(self, other: object) -> bool:
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal

    def __hash__(self) -> int:
        return tuple.__hash__(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        detached = thaw_value(self)
        memo[id(self)] = detached
        return detached

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(self)


FrozenDict = FrozenMapping


def _consume_asdict_entries(values: Any) -> dict[str, Any] | None:
    if (
        not isinstance(values, GeneratorType)
        or values.gi_code.co_filename != _dataclasses.__file__
    ):
        return None

    result: dict[str, Any] = {}
    for index, entry in enumerate(values):
        if index >= MAX_CONTAINER_ITEMS:
            return None
        if not isinstance(entry, _AsdictEntry):
            return None
        key, value = entry
        result[key] = value
    return result


def _validate_container_limits(size: int, path: str, depth: int) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(
            f"{path} exceeds the maximum nesting depth "
            f"of {MAX_NESTING_DEPTH}"
        )
    if size > MAX_CONTAINER_ITEMS:
        raise ValueError(
            f"{path} exceeds the maximum container size "
            f"of {MAX_CONTAINER_ITEMS}"
        )


def _freeze_sequence(
    value: list[Any] | tuple[Any, ...],
    path: str,
    active: set[int],
    depth: int,
) -> tuple[Any, ...]:
    _validate_container_limits(len(value), path, depth)
    identity = id(value)
    if identity in active:
        raise ValueError(f"Reference cycle detected at {path}")
    active.add(identity)
    try:
        return tuple(
            freeze_value(
                item,
                path=f"{path}[{index}]",
                _active=active,
                _depth=depth + 1,
            )
            for index, item in enumerate(value)
        )
    finally:
        active.remove(identity)


def freeze_value(
    value: Any,
    *,
    path: str = "value",
    _active: set[int] | None = None,
    _depth: int = 0,
) -> Any:
    active = set() if _active is None else _active
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if not MIN_JSON_INTEGER <= value <= MAX_JSON_INTEGER:
            raise ValueError(
                f"{path} must be within the signed 64-bit integer range"
            )
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite number")
        return value
    if isinstance(value, Mapping):
        return FrozenMapping(
            value,
            _path=path,
            _active=active,
            _depth=_depth,
        )
    if isinstance(value, (list, tuple)):
        return _freeze_sequence(value, path, active, _depth)
    raise TypeError(
        f"{path} has unsupported value type {type(value).__name__}"
    )


def thaw_value(value: Any, *, path: str = "value") -> Any:
    if isinstance(value, Mapping):
        thawed = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"{path} mappings require string keys; got {key!r}"
                )
            thawed[key] = thaw_value(item, path=f"{path}.{key}")
        return thawed
    if isinstance(value, (list, tuple)):
        return [
            thaw_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite number")
        return value
    raise TypeError(
        f"{path} has unsupported frozen value type {type(value).__name__}"
    )


def _freeze_mapping(
    value: Mapping[str, Any],
    field_name: str,
) -> FrozenMapping:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return FrozenMapping(value, _path=field_name)


def _validate_non_empty_string(value: Any, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a non-empty string")
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_finite_number(value: Any, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a finite number")
    if isinstance(value, int):
        if abs(value) > MOTION_NUMERIC_ABS_LIMIT:
            raise ValueError(
                f"{field_name} exceeds the supported numeric range"
            )
        return
    if (
        not math.isfinite(value)
        or abs(value) > MOTION_NUMERIC_ABS_LIMIT
    ):
        raise ValueError(f"{field_name} must be a finite number")


@dataclass(frozen=True)
class MovementIntent:
    action: str
    source: MovementSource = "owner"
    execution_tier: ExecutionTier = "avatar"
    target: str | None = None
    speed: float = 0.5
    parameters: Mapping[str, Any] = field(default_factory=FrozenMapping)

    def __post_init__(self) -> None:
        _validate_non_empty_string(self.action, "action")
        if self.source not in MOVEMENT_SOURCES:
            raise ValueError(
                "source must be one of owner, task, self, or safety"
            )
        if self.execution_tier not in EXECUTION_TIERS:
            raise ValueError(
                "execution_tier must be one of "
                "avatar, simulation, shadow, or physical"
            )
        if self.target is not None:
            _validate_non_empty_string(self.target, "target")
        _validate_finite_number(self.speed, "speed")
        if not 0 <= self.speed <= 1:
            raise ValueError("speed must be between 0 and 1")
        object.__setattr__(
            self,
            "parameters",
            _freeze_mapping(self.parameters, "parameters"),
        )

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(asdict(self))


@dataclass(frozen=True)
class JointTarget:
    joint: str
    position: float
    velocity: float
    effort: float = 0.0

    def __post_init__(self) -> None:
        _validate_non_empty_string(self.joint, "joint")
        _validate_finite_number(self.position, "position")
        _validate_finite_number(self.velocity, "velocity")
        if self.velocity < 0:
            raise ValueError("velocity must be greater than or equal to zero")
        _validate_finite_number(self.effort, "effort")


@dataclass(frozen=True)
class MovementPlan:
    intent: MovementIntent
    duration_ms: int
    targets: tuple[JointTarget, ...]
    expression: str
    recovery_action: str = "neutral"

    def __post_init__(self) -> None:
        if not isinstance(self.intent, MovementIntent):
            raise TypeError("intent must be a MovementIntent")
        if (
            not isinstance(self.duration_ms, int)
            or isinstance(self.duration_ms, bool)
        ):
            raise TypeError("duration_ms must be a positive integer")
        if self.duration_ms <= 0:
            raise ValueError("duration_ms must be a positive integer")
        if self.duration_ms > MAX_DURATION_MS:
            raise ValueError("duration_ms exceeds the supported range")
        try:
            targets = tuple(self.targets)
        except TypeError as exc:
            raise TypeError(
                "targets must be an iterable of JointTarget values"
            ) from exc
        if any(not isinstance(target, JointTarget) for target in targets):
            raise TypeError("targets must contain only JointTarget values")
        _validate_non_empty_string(self.expression, "expression")
        _validate_non_empty_string(
            self.recovery_action,
            "recovery_action",
        )
        object.__setattr__(self, "targets", targets)


@dataclass(frozen=True)
class MovementResult:
    accepted: bool
    status: str
    reason: str
    body_state: Mapping[str, Any]
    evidence: Mapping[str, Any]

    def __post_init__(self) -> None:
        if type(self.accepted) is not bool:
            raise TypeError("accepted must be a literal bool")
        _validate_non_empty_string(self.status, "status")
        _validate_non_empty_string(self.reason, "reason")
        object.__setattr__(
            self,
            "body_state",
            _freeze_mapping(self.body_state, "body_state"),
        )
        object.__setattr__(
            self,
            "evidence",
            _freeze_mapping(self.evidence, "evidence"),
        )

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(asdict(self))
