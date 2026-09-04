"""Provider-neutral model capabilities and aliases."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import RLock
from typing import Any, Iterable

from .errors import ModelUnavailableError


CAPABILITY_SCHEMA_VERSION = "1.0"


@dataclass
class NovaModelCapability:
    model_id: str
    provider_id: str
    display_name: str
    text_input: bool = True
    text_output: bool = True
    image_input: bool = False
    image_output: bool = False
    audio_input: bool = False
    audio_output: bool = False
    video_input: bool = False
    video_output: bool = False
    embeddings: bool = False
    tool_calling: bool = False
    parallel_tool_calling: bool = False
    structured_output: bool = False
    streaming: bool = False
    reasoning: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None
    local_or_remote: str = "local"
    estimated_memory_requirement: str | None = None
    estimated_cost_type: str = "free"
    availability: str = "available"
    health_status: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_version: str = CAPABILITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def supports(self, requirements: Iterable[str]) -> bool:
        for name in requirements:
            if not bool(getattr(self, name, False)):
                return False
        return self.availability == "available"


class NovaModelRegistry:
    """Thread-safe registry that separates public aliases from provider model IDs."""

    def __init__(self) -> None:
        self._models: dict[tuple[str, str], NovaModelCapability] = {}
        self._aliases: dict[str, tuple[str, str]] = {}
        self._lock = RLock()

    def register_model(self, capability: NovaModelCapability) -> None:
        with self._lock:
            self._models[(capability.provider_id, capability.model_id)] = capability

    def remove_model(self, provider_id: str, model_id: str) -> None:
        key = (provider_id, model_id)
        with self._lock:
            self._models.pop(key, None)
            self._aliases = {alias: target for alias, target in self._aliases.items() if target != key}

    def register_alias(self, alias: str, provider_id: str, model_id: str) -> None:
        value = str(alias or "").strip()
        if not value:
            raise ValueError("Model alias cannot be empty.")
        key = (provider_id, model_id)
        with self._lock:
            if key not in self._models:
                raise ModelUnavailableError(f"Cannot alias unavailable model {provider_id}/{model_id}.")
            self._aliases[value] = key

    def resolve_alias(self, alias: str) -> NovaModelCapability:
        with self._lock:
            target = self._aliases.get(alias)
            if target is None:
                direct = [cap for (_provider, model), cap in self._models.items() if model == alias]
                if len(direct) == 1:
                    return direct[0]
                raise ModelUnavailableError(f"Nova model {alias!r} is not available.")
            capability = self._models.get(target)
            if capability is None or capability.availability != "available":
                reason = (capability.metadata or {}).get("unavailable_reason") if capability else None
                detail = f": {reason}" if reason else "."
                raise ModelUnavailableError(f"Nova model {alias!r} is unavailable{detail}")
            return capability

    def aliases(self) -> dict[str, NovaModelCapability]:
        with self._lock:
            return {
                alias: self._models[target]
                for alias, target in self._aliases.items()
                if target in self._models and self._models[target].availability == "available"
            }

    def list_models(self, *, available: bool | None = None) -> list[NovaModelCapability]:
        with self._lock:
            values = list(self._models.values())
        if available is True:
            return [item for item in values if item.availability == "available"]
        if available is False:
            return [item for item in values if item.availability != "available"]
        return values

    def find_by_capability(self, *requirements: str) -> list[NovaModelCapability]:
        return [item for item in self.list_models(available=True) if item.supports(requirements)]

    def refresh_provider_models(self, provider: Any) -> list[NovaModelCapability]:
        refreshed: list[NovaModelCapability] = []
        for item in provider.list_models():
            if isinstance(item, NovaModelCapability):
                capability = item
            else:
                capability = NovaModelCapability(provider_id=provider.provider_id, **dict(item))
            self.register_model(capability)
            refreshed.append(capability)
        return refreshed

