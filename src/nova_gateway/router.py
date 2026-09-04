"""Capability, privacy, availability, and cost-aware Nova routing."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from nova_protocol import NovaRequest

from .config import GatewayConfig
from .errors import ModelUnavailableError, PermissionDeniedError, ProviderUnavailableError
from .model_registry import NovaModelCapability, NovaModelRegistry
from .providers import NovaProviderRegistry


@dataclass
class RoutingDecision:
    selected_provider: str
    selected_model: str
    requested_alias: str
    reason: str
    rejected_alternatives: list[dict[str, str]] = field(default_factory=list)
    remains_local: bool = True
    estimated_cost: float = 0.0
    fallback_path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NovaTaskRouter:
    """Resolve Nova-facing aliases without hardcoding provider model behavior."""

    def __init__(self, providers: NovaProviderRegistry, models: NovaModelRegistry, config: GatewayConfig):
        self.providers = providers
        self.models = models
        self.config = config

    def select(self, request: NovaRequest) -> RoutingDecision:
        alias = request.generation_options.model or self.config.default_model_alias
        capability = self.models.resolve_alias(alias)
        provider = self.providers.get_provider(capability.provider_id)
        required = self._requirements(request)
        missing = [name for name in required if not bool(getattr(capability, name, False))]
        if missing:
            raise ModelUnavailableError(
                f"Model {alias!r} does not support required capabilities: {', '.join(missing)}.",
                request_id=request.request_id,
            )
        remote = capability.local_or_remote == "remote" or provider.local_or_remote == "remote"
        if remote and self.config.execution_policy == "local_only":
            raise PermissionDeniedError("Nova execution policy is local_only.", request_id=request.request_id)
        if remote and request.privacy_mode == "local_only":
            raise PermissionDeniedError("local_only mode forbids remote model execution.", request_id=request.request_id)
        if remote and not self.config.allow_remote_models:
            raise PermissionDeniedError("Remote model execution is disabled by Nova policy.", request_id=request.request_id)
        if remote and request.metadata.get("contains_private_data") and not self.config.allow_private_data_remote:
            raise PermissionDeniedError("Nova policy forbids sending private data to a remote model.", request_id=request.request_id)
        if remote and any(attachment.local_path for attachment in request.attachments) and not self.config.allow_private_files_remote:
            raise PermissionDeniedError("Nova policy forbids sending private files to a remote model.", request_id=request.request_id)
        if remote and request.privacy_mode == "user_confirmation_required" and not request.metadata.get("remote_execution_confirmed"):
            raise PermissionDeniedError("Remote model execution requires user confirmation.", request_id=request.request_id)
        estimate = provider.estimate_cost(request)
        estimated_cost = float(estimate.get("estimated_cost") or 0.0)
        if estimated_cost > 0 and not self.config.allow_paid_tools:
            raise PermissionDeniedError("Paid provider execution is disabled by Nova policy.", request_id=request.request_id)
        if self.config.per_request_limit > 0 and estimated_cost > self.config.per_request_limit:
            raise PermissionDeniedError("Estimated provider cost exceeds the per-request limit.", request_id=request.request_id)
        try:
            user_limit = float(request.metadata.get("user_spending_limit"))
        except (TypeError, ValueError):
            user_limit = 0.0
        if user_limit > 0 and estimated_cost > user_limit:
            raise PermissionDeniedError("Estimated provider cost exceeds the user's spending limit.", request_id=request.request_id)
        if provider.cost_type == "paid" and self.config.require_confirmation_over <= estimated_cost:
            if not request.metadata.get("remote_cost_confirmed"):
                raise PermissionDeniedError("Remote paid execution requires user confirmation.", request_id=request.request_id)
        reason = f"Resolved Nova alias {alias!r} to a healthy {capability.local_or_remote} provider with {', '.join(required) or 'text'} capability."
        return RoutingDecision(
            selected_provider=capability.provider_id,
            selected_model=capability.model_id,
            requested_alias=alias,
            reason=reason,
            remains_local=not remote,
            estimated_cost=estimated_cost,
            fallback_path=[self.config.default_provider] if self.config.fallback_enabled else [],
        )

    @staticmethod
    def _requirements(request: NovaRequest) -> list[str]:
        required = ["text_input", "text_output"]
        if request.generation_options.stream:
            required.append("streaming")
        if request.tools:
            required.append("tool_calling")
        if request.generation_options.response_format:
            required.append("structured_output")
        for modality in request.requested_modalities:
            name = {"image": "image_output", "audio": "audio_output", "video": "video_output"}.get(modality)
            if name:
                required.append(name)
        for attachment in request.attachments:
            media_type = str(attachment.media_type or "").lower()
            if media_type.startswith("image/"):
                required.append("image_input")
            elif media_type.startswith("audio/"):
                required.append("audio_input")
            elif media_type.startswith("video/"):
                required.append("video_input")
        return list(dict.fromkeys(required))

    def provider_for(self, decision: RoutingDecision):
        provider = self.providers.get_provider(decision.selected_provider)
        health = provider.health_check()
        if not health.get("ok"):
            raise ProviderUnavailableError(
                f"Selected provider {decision.selected_provider!r} is unhealthy: {health.get('error') or 'health check failed'}"
            )
        return provider
