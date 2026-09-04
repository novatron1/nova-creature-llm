"""Safe, stable errors used by Nova compatibility boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NovaGatewayError(Exception):
    """An error that can be returned to an external client without a traceback."""

    message: str
    error_type: str = "internal_error"
    code: str = "internal_error"
    status: int = 500
    param: str | None = None
    request_id: str | None = None

    def __str__(self) -> str:
        return self.message

    def to_openai(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "message": self.message,
            "type": self.error_type,
            "param": self.param,
            "code": self.code,
        }
        if self.request_id:
            error["request_id"] = self.request_id
        return {"error": error}


class InvalidRequestError(NovaGatewayError):
    def __init__(self, message: str, *, param: str | None = None, request_id: str | None = None):
        super().__init__(message, "invalid_request_error", "invalid_request", 400, param, request_id)


class AuthenticationError(NovaGatewayError):
    def __init__(self, message: str = "A valid Nova API key is required.", *, request_id: str | None = None):
        super().__init__(message, "authentication_error", "invalid_api_key", 401, None, request_id)


class PermissionDeniedError(NovaGatewayError):
    def __init__(self, message: str, *, request_id: str | None = None):
        super().__init__(message, "permission_error", "insufficient_scope", 403, None, request_id)


class RateLimitError(NovaGatewayError):
    def __init__(self, message: str = "Nova API rate limit exceeded.", *, request_id: str | None = None):
        super().__init__(message, "rate_limit_error", "rate_limit_exceeded", 429, None, request_id)


class ProviderUnavailableError(NovaGatewayError):
    def __init__(self, message: str, *, request_id: str | None = None):
        super().__init__(message, "provider_unavailable", "provider_unavailable", 503, None, request_id)


class ModelUnavailableError(NovaGatewayError):
    def __init__(self, message: str, *, param: str | None = "model", request_id: str | None = None):
        super().__init__(message, "model_unavailable", "model_not_found", 404, param, request_id)


class UnsupportedFeatureError(NovaGatewayError):
    def __init__(self, message: str, *, param: str | None = None, request_id: str | None = None):
        super().__init__(message, "unsupported_feature", "unsupported_feature", 400, param, request_id)


class ToolValidationError(NovaGatewayError):
    def __init__(self, message: str, *, request_id: str | None = None):
        super().__init__(message, "tool_validation_error", "tool_validation_failed", 400, "tools", request_id)


class RequestTimeoutError(NovaGatewayError):
    def __init__(self, message: str = "Nova request timed out.", *, request_id: str | None = None):
        super().__init__(message, "timeout_error", "request_timeout", 504, None, request_id)

