"""Provider-neutral semantic model interface used inside Nova.

External clients still connect to Nova's API.  This module only standardizes
the replaceable model component behind Nova's identity, memory, tools, policy,
and verification layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
import ipaddress
import json
import os
from typing import Any, Callable, Iterator, Mapping
import urllib.request
from urllib.parse import urlparse

try:
    from .nova_http_security import (
        exact_host_allowlist,
        open_without_redirects,
        validate_worker_url,
    )
except ImportError:  # pragma: no cover - direct src/ import compatibility
    from nova_http_security import (
        exact_host_allowlist,
        open_without_redirects,
        validate_worker_url,
    )


MODEL_PROVIDER_INTERFACE_VERSION = "1.0"


@dataclass(frozen=True)
class ModelCapabilities:
    provider_id: str
    model_id: str
    context_limit: int
    tools: bool = False
    reasoning: bool = False
    structured_output: bool = False
    vision: bool = False
    streaming: bool = True
    local_or_remote: str = "local"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ModelGenerationRequest:
    prompt: str
    model: str | None = None
    max_tokens: int = 512
    temperature: float = 0.3
    reasoning_enabled: bool = False
    reasoning_budget: int | None = None
    reasoning_mode: str = "fast"
    stop: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelGenerationResult:
    text: str
    provider_id: str
    model_id: str
    finish_reason: str = "stop"
    usage: dict[str, Any] = field(default_factory=dict)
    reasoning_used: bool = False
    reasoning_summary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class NovaModelProvider(ABC):
    provider_id = "provider"
    interface_version = MODEL_PROVIDER_INTERFACE_VERSION

    @abstractmethod
    def list_models(self) -> list[str]: ...

    @abstractmethod
    def get_capabilities(self, model_id: str | None = None) -> ModelCapabilities: ...

    @abstractmethod
    def count_tokens(self, text: str, model_id: str | None = None) -> int: ...

    @abstractmethod
    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult: ...

    @abstractmethod
    def stream_generate(
        self,
        request: ModelGenerationRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[str]: ...

    def supports_tools(self, model_id: str | None = None) -> bool:
        return self.get_capabilities(model_id).tools

    def supports_reasoning(self, model_id: str | None = None) -> bool:
        return self.get_capabilities(model_id).reasoning

    def supports_structured_output(self, model_id: str | None = None) -> bool:
        return self.get_capabilities(model_id).structured_output

    def supports_vision(self, model_id: str | None = None) -> bool:
        return self.get_capabilities(model_id).vision

    def get_context_limit(self, model_id: str | None = None) -> int:
        return self.get_capabilities(model_id).context_limit


class MockModelProvider(NovaModelProvider):
    """Deterministic test provider with no network or model dependency."""

    provider_id = "mock"

    def __init__(self, text: str = "Mock Nova semantic result.", model_id: str = "mock-local") -> None:
        self.text = text
        self.model_id = model_id
        self.requests: list[ModelGenerationRequest] = []

    def list_models(self) -> list[str]:
        return [self.model_id]

    def get_capabilities(self, model_id: str | None = None) -> ModelCapabilities:
        return ModelCapabilities(
            provider_id=self.provider_id,
            model_id=model_id or self.model_id,
            context_limit=32768,
            tools=True,
            reasoning=True,
            structured_output=True,
        )

    def count_tokens(self, text: str, model_id: str | None = None) -> int:
        return max(1, (len(str(text or "").encode("utf-8")) + 3) // 4)

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        self.requests.append(request)
        return ModelGenerationResult(
            text=self.text,
            provider_id=self.provider_id,
            model_id=request.model or self.model_id,
            reasoning_used=bool(request.reasoning_enabled),
            metadata={"deterministic": True},
        )

    def stream_generate(
        self,
        request: ModelGenerationRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        self.requests.append(request)
        for word in self.text.split(" "):
            if is_cancelled and is_cancelled():
                return
            yield word + " "


class ExistingConnectorProvider(NovaModelProvider):
    """Adapter over Nova's installed local model connector."""

    provider_id = "nova-local-connector"

    def __init__(self, connector: Any | None = None, *, force_cpu: bool = False) -> None:
        if connector is None:
            from nova_local_llm_connector import LocalLLMConnector

            connector = LocalLLMConnector()
        self.connector = connector
        self.force_cpu = bool(force_cpu)

    def list_models(self) -> list[str]:
        config = self.connector.config
        return list(dict.fromkeys([config.fast_model, config.deep_model, config.model]))

    def get_capabilities(self, model_id: str | None = None) -> ModelCapabilities:
        model = str(model_id or self.connector.config.model)
        lowered = model.lower()
        return ModelCapabilities(
            provider_id=self.provider_id,
            model_id=model,
            context_limit=int(self.connector.config.context_window),
            tools=False,
            reasoning="qwen3" in lowered or "deepseek" in lowered,
            structured_output=True,
            vision=any(marker in lowered for marker in ("vision", "llava", "moondream")),
            streaming=True,
            metadata={"connector_provider": self.connector.config.provider},
        )

    def count_tokens(self, text: str, model_id: str | None = None) -> int:
        # The connector has no tokenizer contract, so use a conservative UTF-8
        # estimate and mark exact counts unavailable in result metadata.
        return max(1, (len(str(text or "").encode("utf-8")) + 3) // 4)

    def _context(self, request: ModelGenerationRequest) -> dict[str, Any]:
        options = {
            "temperature": request.temperature,
            "num_predict": request.max_tokens,
            **({"stop": request.stop} if request.stop else {}),
        }
        if self.force_cpu:
            options["num_gpu"] = 0
        return {
            "raw_prompt": request.prompt,
            "user_message": request.metadata.get("user_message", ""),
            "selected_route": request.metadata.get("route", request.reasoning_mode),
            "local_llm_model": request.model,
            "reasoning_enabled": request.reasoning_enabled,
            "reasoning_budget": request.reasoning_budget,
            "reasoning_mode": request.reasoning_mode,
            "ollama_options": options,
        }

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        response = self.connector.generate(self._context(request))
        if not response or not getattr(response, "local_llm_used", False):
            raise RuntimeError(
                str(getattr(response, "fallback_reason", "") or "Local model generation failed.")
            )
        return ModelGenerationResult(
            text=str(getattr(response, "raw_output", "") or ""),
            provider_id=str(getattr(response, "provider", "") or self.provider_id),
            model_id=str(getattr(response, "model", "") or request.model or ""),
            finish_reason=str(getattr(response, "finish_reason", "") or "stop"),
            usage={"estimated": True},
            reasoning_used=bool(request.reasoning_enabled),
            metadata={"reasoning_content_stored": False},
        )

    def stream_generate(
        self,
        request: ModelGenerationRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        chunks: list[str] = []
        response = self.connector.generate_stream(
            self._context(request),
            lambda delta: chunks.append(str(delta)) or True,
            is_cancelled,
        )
        if not response or not getattr(response, "local_llm_used", False):
            raise RuntimeError(
                str(getattr(response, "fallback_reason", "") or "Local model stream failed.")
            )
        yield from chunks


class OpenAICompatibleLocalProvider(NovaModelProvider):
    """Internal adapter for local OpenAI-compatible servers such as vLLM/SGLang."""

    provider_id = "openai-compatible-local"

    def __init__(
        self,
        *,
        base_url: str,
        model_id: str,
        api_key: str | None = None,
        provider_id: str = "openai-compatible-local",
        context_limit: int = 8192,
        timeout_seconds: int = 120,
        allow_remote: bool = False,
        allowed_hosts: str | list[str] | tuple[str, ...] | set[str] | None = None,
        capabilities: dict[str, bool] | None = None,
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.model_id = str(model_id)
        self.api_key = str(api_key or "")
        self.provider_id = str(provider_id)
        self.context_limit = max(1024, int(context_limit))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.allow_remote = bool(allow_remote)
        configured_hosts = (
            os.environ.get("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", "")
            if allowed_hosts is None
            else allowed_hosts
        )
        self.allowed_hosts = exact_host_allowlist(configured_hosts)
        self.capability_flags = dict(capabilities or {})
        self._validate_endpoint()

    def _validate_endpoint(self) -> None:
        self._validate_request_url(self.base_url)

    def _validate_request_url(self, value: str) -> None:
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            raise ValueError("A valid HTTP(S) provider base URL is required.")
        if self.allow_remote:
            try:
                validate_worker_url(value, allowed_hosts=self.allowed_hosts)
                return
            except ValueError as error:
                raise ValueError(
                    "Remote model provider host is not approved for private GPU traffic."
                ) from error
        hostname = parsed.hostname.lower()
        if hostname == "localhost":
            return
        try:
            if ipaddress.ip_address(hostname).is_loopback:
                return
        except ValueError:
            pass
        raise ValueError(
            "Remote model providers are disabled. Use loopback or explicitly authorize remote use."
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request_url = self.base_url + path
        self._validate_request_url(request_url)
        request = urllib.request.Request(
            request_url,
            data=data,
            headers=self._headers(),
            method=method,
        )
        response = open_without_redirects(request, timeout=self.timeout_seconds)
        final_url = response.geturl() if callable(getattr(response, "geturl", None)) else request_url
        try:
            self._validate_request_url(final_url)
        except Exception:
            close = getattr(response, "close", None)
            if callable(close):
                close()
            raise
        return response

    def list_models(self) -> list[str]:
        try:
            with self._request("GET", "/v1/models") as response:
                payload = json.loads(response.read().decode("utf-8"))
            models = [
                str(item["id"])
                for item in payload.get("data", [])
                if isinstance(item, dict) and item.get("id")
            ]
            return models or [self.model_id]
        except Exception:
            return [self.model_id]

    def get_capabilities(self, model_id: str | None = None) -> ModelCapabilities:
        return ModelCapabilities(
            provider_id=self.provider_id,
            model_id=model_id or self.model_id,
            context_limit=self.context_limit,
            tools=bool(self.capability_flags.get("tools", False)),
            reasoning=bool(self.capability_flags.get("reasoning", False)),
            structured_output=bool(self.capability_flags.get("structured_output", True)),
            vision=bool(self.capability_flags.get("vision", False)),
            streaming=True,
            local_or_remote="remote" if self.allow_remote else "local",
            metadata={"protocol": "openai-compatible", "client_bypass": False},
        )

    def count_tokens(self, text: str, model_id: str | None = None) -> int:
        return max(1, (len(str(text or "").encode("utf-8")) + 3) // 4)

    def _payload(self, request: ModelGenerationRequest, *, stream: bool) -> dict[str, Any]:
        prompt = request.prompt
        selected_model = request.model or self.model_id
        if (
            "qwen3" in str(selected_model).lower()
            or self.capability_flags.get("qwen_thinking_directives", False)
        ):
            prompt = ("/think\n" if request.reasoning_enabled else "/no_think\n") + prompt
        payload: dict[str, Any] = {
            "model": selected_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": stream,
        }
        if request.stop:
            payload["stop"] = list(request.stop)
        return payload

    def generate(self, request: ModelGenerationRequest) -> ModelGenerationResult:
        with self._request(
            "POST",
            "/v1/chat/completions",
            self._payload(request, stream=False),
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError("The local provider returned no completion choices.")
        choice = choices[0]
        message = choice.get("message") or {}
        from nova_local_llm_connector import clean_local_llm_output

        text = clean_local_llm_output(str(message.get("content") or ""))
        return ModelGenerationResult(
            text=text,
            provider_id=self.provider_id,
            model_id=str(payload.get("model") or request.model or self.model_id),
            finish_reason=str(choice.get("finish_reason") or "stop"),
            usage=dict(payload.get("usage") or {}),
            reasoning_used=bool(request.reasoning_enabled),
            metadata={
                "protocol": "openai-compatible",
                "reasoning_content_stored": False,
            },
        )

    def stream_generate(
        self,
        request: ModelGenerationRequest,
        *,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> Iterator[str]:
        from nova_local_llm_connector import _VisibleReasoningFilter

        pending: list[str] = []
        filter_ = _VisibleReasoningFilter(lambda delta: pending.append(delta) or True)
        with self._request(
            "POST",
            "/v1/chat/completions",
            self._payload(request, stream=True),
        ) as response:
            for raw_line in response:
                if is_cancelled and is_cancelled():
                    return
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    payload = json.loads(data)
                    delta = str(
                        (((payload.get("choices") or [{}])[0].get("delta") or {}).get("content"))
                        or ""
                    )
                except (json.JSONDecodeError, IndexError, AttributeError):
                    continue
                if delta:
                    filter_.feed(delta)
                    while pending:
                        yield pending.pop(0)
        filter_.finish()
        while pending:
            yield pending.pop(0)


class NovaModelProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, NovaModelProvider] = {}
        self._active: str | None = None

    def register(self, provider: NovaModelProvider, *, default: bool = False) -> None:
        self._providers[provider.provider_id] = provider
        if default or self._active is None:
            self._active = provider.provider_id

    def unregister(self, provider_id: str) -> None:
        self._providers.pop(provider_id, None)
        if self._active == provider_id:
            self._active = next(iter(self._providers), None)

    def set_active(self, provider_id: str) -> None:
        if provider_id not in self._providers:
            raise KeyError(f"Unknown Nova model provider: {provider_id}")
        self._active = provider_id

    def get(self, provider_id: str | None = None) -> NovaModelProvider:
        selected = provider_id or self._active
        if not selected or selected not in self._providers:
            raise KeyError("No Nova model provider is configured.")
        return self._providers[selected]

    def list_models(self) -> dict[str, list[str]]:
        return {provider_id: provider.list_models() for provider_id, provider in self._providers.items()}


def build_gpu_hub_provider_settings(
    state: Mapping[str, Any],
    ordinary_settings: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an opt-in GPU Hub provider overlay without mutating normal settings.

    A GPU Hub route may only replace Nova's existing provider after a selected
    GPU endpoint has been explicitly verified.  CPU and unverified automatic
    modes deliberately return the ordinary settings exactly as supplied.
    """

    settings = dict(ordinary_settings or {})
    mode = str(state.get("mode") or "auto")
    effective_mode = str(state.get("effective_mode") or state.get("effective_backend") or mode)
    verified_backend = str(state.get("verified_backend") or "")
    if (
        mode not in {"auto", "local_gpu", "vast_gpu"}
        or effective_mode not in {"local_gpu", "vast_gpu"}
        or verified_backend != effective_mode
        or not bool(state.get("available"))
        or not bool(state.get("verified"))
    ):
        return settings

    endpoint = state.get("endpoint")
    if not isinstance(endpoint, Mapping):
        return settings
    base_url = str(endpoint.get("url") or "").strip().rstrip("/")
    model = str(endpoint.get("model") or "").strip()
    provider = str(endpoint.get("provider") or "openai-compatible").strip().lower()
    parsed = urlparse(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not model
        or provider not in {"openai-compatible", "vllm", "sglang"}
    ):
        return settings
    if effective_mode == "local_gpu":
        hostname = str(parsed.hostname).lower()
        try:
            loopback = hostname == "localhost" or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            loopback = hostname == "localhost"
        if not loopback:
            return settings

    settings.update(
        {
            "NOVA_MODEL_PROVIDER": provider,
            "NOVA_MODEL_PROVIDER_BASE_URL": base_url,
            "NOVA_MODEL_PROVIDER_MODEL": model,
            "NOVA_ALLOW_REMOTE_MODEL_PROVIDER": effective_mode == "vast_gpu",
        }
    )
    # A browser-supplied API key is intentionally not part of this bridge.
    settings.pop("NOVA_MODEL_PROVIDER_API_KEY", None)
    return settings


def provider_registry_from_environment(
    *,
    connector: Any | None = None,
    settings: Mapping[str, Any] | None = None,
    gpu_hub_state: Mapping[str, Any] | None = None,
) -> NovaModelProviderRegistry:
    """Build Nova's internal semantic-provider registry from configuration."""

    from nova_local_llm_connector import LocalLLMConfig

    resolved_settings = dict(LocalLLMConfig().config if settings is None else settings)
    force_cpu = False
    if gpu_hub_state is not None:
        mode = str(gpu_hub_state.get("mode") or "auto")
        effective_mode = str(
            gpu_hub_state.get("effective_mode")
            or gpu_hub_state.get("effective_backend")
            or mode
        )
        if mode in {"local_gpu", "vast_gpu"} and not bool(gpu_hub_state.get("available")):
            reason = str(gpu_hub_state.get("reason") or mode + " is unavailable.")
            raise RuntimeError(f"GPU Hub {mode} is unavailable: {reason}")
        if effective_mode == "cpu":
            force_cpu = True
            resolved_settings["NOVA_MODEL_PROVIDER"] = "existing"
        else:
            resolved_settings = build_gpu_hub_provider_settings(
                gpu_hub_state,
                resolved_settings,
            )
    registry = NovaModelProviderRegistry()
    existing = ExistingConnectorProvider(connector, force_cpu=force_cpu)
    registry.register(existing, default=True)
    provider_type = str(resolved_settings.get("NOVA_MODEL_PROVIDER", "existing")).strip().lower()
    if provider_type in {"openai-compatible", "vllm", "sglang"}:
        compatible = OpenAICompatibleLocalProvider(
            base_url=str(
                resolved_settings.get(
                    "NOVA_MODEL_PROVIDER_BASE_URL",
                    "http://127.0.0.1:8000",
                )
            ),
            model_id=str(resolved_settings.get("NOVA_MODEL_PROVIDER_MODEL") or "local-model"),
            api_key=os.environ.get("NOVA_MODEL_PROVIDER_API_KEY"),
            provider_id=provider_type,
            context_limit=int(resolved_settings.get("NOVA_MODEL_PROVIDER_CONTEXT", 8192)),
            timeout_seconds=int(resolved_settings.get("NOVA_MODEL_PROVIDER_TIMEOUT", 120)),
            allow_remote=bool(resolved_settings.get("NOVA_ALLOW_REMOTE_MODEL_PROVIDER", False)),
            allowed_hosts=resolved_settings.get(
                "NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST",
                os.environ.get("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", ""),
            ),
        )
        registry.register(compatible, default=True)
    return registry
