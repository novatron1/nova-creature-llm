from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
import math
from typing import Any, Literal

ExecutionTier = Literal["avatar", "simulation", "shadow", "physical"]


class FrozenDict(dict[str, Any]):
    def __init__(
        self,
        values: Mapping[str, Any]
        | Iterable[tuple[str, Any]]
        | None = None,
        *,
        _path: str = "value",
        _active: set[int] | None = None,
    ) -> None:
        if values is None:
            source: Mapping[Any, Any] = {}
        elif isinstance(values, Mapping):
            source = values
        else:
            try:
                source = dict(values)
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"{_path} must be a mapping or iterable of key/value pairs"
                ) from exc

        active = set() if _active is None else _active
        identity = id(source)
        if identity in active:
            raise ValueError(f"Reference cycle detected at {_path}")
        active.add(identity)
        try:
            frozen: dict[str, Any] = {}
            for key, value in source.items():
                if not isinstance(key, str):
                    raise TypeError(
                        f"{_path} mappings require string keys; got {key!r}"
                    )
                frozen[key] = freeze_value(
                    value,
                    path=f"{_path}.{key}",
                    _active=active,
                )
        finally:
            active.remove(identity)
        dict.__init__(self, frozen)

    def _immutable(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def __hash__(self) -> int:
        return hash(tuple((key, self[key]) for key in sorted(self)))

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenDict:
        memo[id(self)] = self
        return self

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(self)


def _freeze_sequence(
    value: list[Any] | tuple[Any, ...] | range | bytearray,
    path: str,
    active: set[int],
) -> tuple[Any, ...]:
    identity = id(value)
    if identity in active:
        raise ValueError(f"Reference cycle detected at {path}")
    active.add(identity)
    try:
        return tuple(
            freeze_value(item, path=f"{path}[{index}]", _active=active)
            for index, item in enumerate(value)
        )
    finally:
        active.remove(identity)


def _freeze_set(
    value: set[Any] | frozenset[Any],
    path: str,
    active: set[int],
) -> tuple[Any, ...]:
    identity = id(value)
    if identity in active:
        raise ValueError(f"Reference cycle detected at {path}")
    active.add(identity)
    try:
        normalized = [
            freeze_value(item, path=f"{path}[{index}]", _active=active)
            for index, item in enumerate(value)
        ]
    finally:
        active.remove(identity)
    try:
        return tuple(sorted(normalized))
    except TypeError:
        return tuple(sorted(normalized, key=repr))


def freeze_value(
    value: Any,
    *,
    path: str = "value",
    _active: set[int] | None = None,
) -> Any:
    active = set() if _active is None else _active
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} must be a finite number")
        return value
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value, _path=path, _active=active)
    if isinstance(value, (set, frozenset)):
        return _freeze_set(value, path, active)
    if isinstance(value, (list, tuple, range, bytearray)):
        return _freeze_sequence(value, path, active)
    if isinstance(value, bytes):
        raise TypeError(f"{path} does not accept bytes")
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
    if isinstance(value, tuple):
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


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> FrozenDict:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return FrozenDict(value, _path=field_name)


@dataclass(frozen=True)
class MovementIntent:
    action: str
    source: Literal["owner", "task", "self", "safety"] = "owner"
    execution_tier: ExecutionTier = "avatar"
    target: str | None = None
    speed: float = 0.5
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
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


@dataclass(frozen=True)
class MovementPlan:
    intent: MovementIntent
    duration_ms: int
    targets: tuple[JointTarget, ...]
    expression: str
    recovery_action: str = "neutral"

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))


@dataclass(frozen=True)
class MovementResult:
    accepted: bool
    status: str
    reason: str
    body_state: dict[str, Any]
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
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
