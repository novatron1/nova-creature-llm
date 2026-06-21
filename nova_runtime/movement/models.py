from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import math
from types import MappingProxyType
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


class FrozenMapping(Mapping[str, Any]):
    __slots__ = ("__data",)

    def __init__(
        self,
        values: Mapping[str, Any] | None = None,
        *,
        _path: str = "value",
        _active: set[int] | None = None,
        _depth: int = 0,
    ) -> None:
        if values is None:
            source: Mapping[Any, Any] = {}
        elif isinstance(values, FrozenMapping):
            source = values.to_dict()
        elif isinstance(values, Mapping):
            source = values
        else:
            raise TypeError(f"{_path} must be a mapping")

        _validate_nesting_depth(_path, _depth)

        active = set() if _active is None else _active
        identity = id(source)
        if identity in active:
            raise ValueError(f"Reference cycle detected at {_path}")
        active.add(identity)
        try:
            frozen: dict[str, Any] = {}
            seen: set[str] = set()
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
                if key in seen:
                    raise ValueError(
                        f"{_path} mappings require unique keys; "
                        f"duplicate key {key!r}"
                    )
                seen.add(key)
                frozen[key] = freeze_value(
                    value,
                    path=f"{_path}.{key}",
                    _active=active,
                    _depth=_depth + 1,
                )
        finally:
            active.remove(identity)
        ordered = {key: frozen[key] for key in sorted(frozen)}
        object.__setattr__(
            self,
            "_FrozenMapping__data",
            MappingProxyType(ordered),
        )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        raise TypeError("FrozenMapping cannot be subclassed")

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("FrozenMapping is immutable")

    def __getitem__(self, key: str) -> Any:
        return self.__data[key]

    def __iter__(self):
        return iter(self.__data)

    def __len__(self) -> int:
        return len(self.__data)

    def __contains__(self, key: object) -> bool:
        return key in self.__data

    def __repr__(self) -> str:
        return f"{type(self).__name__}({dict(self.__data)!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return NotImplemented
        return dict(self.__data) == dict(other)

    def __ne__(self, other: object) -> bool:
        equal = self.__eq__(other)
        if equal is NotImplemented:
            return NotImplemented
        return not equal

    def __hash__(self) -> int:
        return hash(tuple(self.__data.items()))

    def __copy__(self) -> FrozenMapping:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> dict[str, Any]:
        detached = thaw_value(self)
        memo[id(self)] = detached
        return detached

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(self)

    def __reduce__(self):
        return (type(self), (self.to_dict(),))


FrozenDict = FrozenMapping


def _validate_nesting_depth(path: str, depth: int) -> None:
    if depth > MAX_NESTING_DEPTH:
        raise ValueError(
            f"{path} exceeds the maximum nesting depth "
            f"of {MAX_NESTING_DEPTH}"
        )


def _freeze_sequence(
    value: list[Any],
    path: str,
    active: set[int],
    depth: int,
) -> tuple[Any, ...]:
    _validate_nesting_depth(path, depth)
    identity = id(value)
    if identity in active:
        raise ValueError(f"Reference cycle detected at {path}")
    active.add(identity)
    try:
        frozen: list[Any] = []
        for index, item in enumerate(value):
            if index >= MAX_CONTAINER_ITEMS:
                raise ValueError(
                    f"{path} exceeds the maximum container size "
                    f"of {MAX_CONTAINER_ITEMS}"
                )
            frozen.append(
                freeze_value(
                    item,
                    path=f"{path}[{index}]",
                    _active=active,
                    _depth=depth + 1,
                )
            )
        return tuple(frozen)
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
    if type(value) is list:
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
