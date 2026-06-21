from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from types import MappingProxyType
from typing import Any, Literal

ExecutionTier = Literal["avatar", "simulation", "shadow", "physical"]


class FrozenDict(Mapping[str, Any]):
    __slots__ = ("_data",)

    def __init__(self, values: Mapping[str, Any] | None = None) -> None:
        source = {} if values is None else values
        if not isinstance(source, Mapping):
            raise TypeError("FrozenDict values must be a mapping")
        frozen = {key: freeze_value(value) for key, value in source.items()}
        object.__setattr__(self, "_data", MappingProxyType(frozen))

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"FrozenDict({dict(self._data)!r})"

    def __deepcopy__(self, memo: dict[int, Any]) -> FrozenDict:
        memo[id(self)] = self
        return self

    def to_dict(self) -> dict[str, Any]:
        return thaw_value(self)


def freeze_value(value: Any) -> Any:
    if isinstance(value, FrozenDict):
        return value
    if isinstance(value, Mapping):
        return FrozenDict(value)
    if isinstance(value, (set, frozenset)):
        return frozenset(freeze_value(item) for item in value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(freeze_value(item) for item in value)
    return value


def thaw_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: thaw_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_value(item) for item in value]
    if isinstance(value, frozenset):
        try:
            ordered = sorted(value)
        except TypeError:
            ordered = sorted(value, key=repr)
        return [thaw_value(item) for item in ordered]
    return value


def _freeze_mapping(value: Mapping[str, Any], field_name: str) -> FrozenDict:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return FrozenDict(value)


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
