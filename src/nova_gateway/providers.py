"""Replaceable text and embedding provider interface for Nova."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
from queue import Empty, Queue
from threading import Event, RLock
from threading import Thread
import time
from typing import Any, Callable, Iterable, Iterator
import urllib.error
import urllib.request

from nova_protocol import NovaRequest, NovaResponse, NovaStreamEvent, new_id

from .errors import ProviderUnavailableError, UnsupportedFeatureError
from .model_registry import NovaModelCapability


PROVIDER_INTERFACE_VERSION = "1.1"
PROVIDER_EXTENSION_POINTS = {
    "vllm": "documented_extension",
    "llama_cpp": "documented_extension",
    "openai": "documented_extension",
    "anthropic": "documented_extension",
    "vision": "documented_extension",
    "image_generation": "documented_extension",
    "video_generation": "documented_extension",
    "speech": "documented_extension",
}


class NovaModelProvider(ABC):
    """Synchronous provider contract matching Nova's current HTTP runtime."""

    provider_id = "provider"
    display_name = "Provider"
    local_or_remote = "local"
    cost_type = "free"
    interface_version = PROVIDER_INTERFACE_VERSION

    @abstractmethod
    def list_models(self) -> list[NovaModelCapability]:
        raise NotImplementedError

    def get_model_capabilities(self, model_id: str) -> NovaModelCapability:
        for model in self.list_models():
            if model.model_id == model_id:
                return model
        raise ProviderUnavailableError(f"{self.provider_id} model {model_id!r} is not available.")

    @abstractmethod
    def generate(self, request: NovaRequest) -> NovaResponse:
        raise NotImplementedError

    def stream(self, request: NovaRequest) -> Iterator[NovaStreamEvent]:
        raise UnsupportedFeatureError(f"Provider {self.provider_id!r} does not support true streaming.", param="stream")

    def embed(self, inputs: list[str], model: str | None = None) -> list[list[float]]:
        raise UnsupportedFeatureError(f"Provider {self.provider_id!r} does not support embeddings.")

    def health_check(self) -> dict[str, Any]:
        return {"ok": True, "provider_id": self.provider_id, "interface_version": self.interface_version}

    def estimate_cost(self, request: NovaRequest) -> dict[str, Any]:
        return {"estimated_cost": 0.0, "currency": "USD", "cost_type": self.cost_type, "estimated": True}

    def warm_up_model(
        self,
        model_id: str | None = None,
        *,
        keep_alive: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Optionally make one installed model ready without producing text."""

        return {
            "ok": False,
            "state": "unsupported",
            "provider": self.provider_id,
            "model": model_id,
        }

    def cancel(self, request_id: str) -> bool:
        return False


class ExistingNovaProvider(NovaModelProvider):
    """Adapter around Nova's real brain_route/cognitive/memory/tool path."""

    provider_id = "existing-nova"
    display_name = "Nova Cognitive Core"
    _stream_heartbeat_seconds = 10.0
    _DESKTOP_CONTEXT_KEYS = frozenset(
        {
            "adapter_only_mode",
            "trained_adapter_only",
            "trained_adapter_only_mode",
            "use_lora_runtime",
            "dolphin_adapter_only",
            "dolphin_lora_only",
            "allow_slow_dolphin_cpu",
            "allow_slow_adapter_cpu",
            "lora_adapter_id",
            "sensor_snapshot",
            "conversation_history",
            "conversation_summary",
            "conversation_summary_history",
            "conversation_summary_write_allowed",
            "nova_model_mode",
        }
    )

    def __init__(self, turn_runner: Callable[[str, dict[str, Any]], tuple[str, dict[str, Any]]]):
        self._turn_runner = turn_runner
        self._cancelled: set[str] = set()
        self._active_streams: dict[str, Event] = {}
        self._lock = RLock()

    def list_models(self) -> list[NovaModelCapability]:
        return [
            NovaModelCapability(
                model_id="nova-core",
                provider_id=self.provider_id,
                display_name="Nova Cognitive Core",
                reasoning=True,
                tool_calling=True,
                structured_output=True,
                streaming=True,
                local_or_remote="local",
                estimated_cost_type="free",
                availability="available",
                health_status="healthy",
                metadata={"identity_preserved": True, "memory_preserved": True},
            )
        ]

    def generate(self, request: NovaRequest) -> NovaResponse:
        with self._lock:
            if request.request_id in self._cancelled:
                raise ProviderUnavailableError("The Nova request was cancelled.", request_id=request.request_id)
        text = request.last_user_text()
        context = self._request_context(request)
        started = time.monotonic()
        content, trace = self._turn_runner(text, context)
        return NovaResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            model=request.generation_options.model,
            provider=self.provider_id,
            content=str(content or ""),
            finish_reason="stop",
            usage={"estimated": True},
            metadata={
                "nova_core": True,
                "identity_preserved": True,
                "route": (trace or {}).get("route") or (trace or {}).get("selected_route"),
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "trace": trace or {},
            },
        )

    @staticmethod
    def _request_context(request: NovaRequest) -> dict[str, Any]:
        """Build the gateway context consumed by Nova's existing brain path."""
        context = {
            "nova_gateway": True,
            "nova_request": request.to_dict(),
            "request_id": request.request_id,
            "user_id": request.user_id,
            "client_id": request.client_id,
            "conversation_id": request.conversation_id,
            "session_id": request.session_id,
            "privacy_mode": request.privacy_mode,
            "evaluation_only": (
                request.metadata.get("evaluation_only") is True
                and request.metadata.get("_nova_evaluation_trusted") is True
            ),
            "client_scopes": list(request.metadata.get("client_scopes") or []),
            "memory_mode": request.metadata.get("memory_mode"),
            "memory_read_allowed": bool(request.metadata.get("memory_read_allowed", False)),
            "memory_write_allowed": bool(request.metadata.get("memory_write_allowed", False)),
            "conversation_memory_allowed": bool(request.metadata.get("conversation_memory_allowed", False)),
            "world_model": dict(request.metadata.get("world_model") or {}),
            "dream_lab": dict(request.metadata.get("dream_lab") or {}),
        }
        desktop_context = request.metadata.get("desktop_context")
        if isinstance(desktop_context, dict):
            for key in ExistingNovaProvider._DESKTOP_CONTEXT_KEYS:
                if key in desktop_context:
                    context[key] = desktop_context[key]
        return context

    def stream(self, request: NovaRequest) -> Iterator[NovaStreamEvent]:
        """Stream the real Nova turn while its cognitive pipeline is running.

        Deterministic routes complete immediately as one delta. Language-model
        routes can publish safety-gated incremental deltas through the context
        callback without bypassing Nova identity, memory, tools, or permissions.
        """
        with self._lock:
            if request.request_id in self._cancelled:
                raise ProviderUnavailableError("The Nova request was cancelled.", request_id=request.request_id)
            cancel_event = Event()
            self._active_streams[request.request_id] = cancel_event

        response_id = new_id("resp")
        messages: Queue[tuple[str, Any]] = Queue()
        emitted_parts: list[str] = []
        latest_progress: dict[str, Any] = {}
        stream_started = time.monotonic()

        def emit(delta: str) -> bool:
            value = str(delta or "")
            if not value or cancel_event.is_set():
                return not cancel_event.is_set()
            messages.put(("delta", value))
            return True

        def emit_progress(stage: str, label: str, percent: int | float | None = None) -> bool:
            if cancel_event.is_set():
                return False
            safe_stage = str(stage or "working").strip().lower()[:48]
            safe_label = str(label or "Nova is working locally.").strip()[:160]
            safe_percent = None
            if percent is not None:
                try:
                    safe_percent = max(0, min(int(percent), 100))
                except (TypeError, ValueError):
                    safe_percent = None
            payload = {
                "stage": safe_stage,
                "label": safe_label,
                "percent": safe_percent,
            }
            latest_progress.clear()
            latest_progress.update(payload)
            messages.put(("progress", payload))
            return True

        context = self._request_context(request)
        context.update(
            {
                "stream_callback": emit,
                "progress_callback": emit_progress,
                "stream_cancelled": cancel_event.is_set,
                "native_streaming": True,
            }
        )

        def run_turn() -> None:
            started = time.monotonic()
            try:
                content, trace = self._turn_runner(request.last_user_text(), context)
                messages.put(
                    (
                        "done",
                        {
                            "content": str(content or ""),
                            "trace": trace or {},
                            "latency_ms": round((time.monotonic() - started) * 1000, 3),
                        },
                    )
                )
            except Exception as exc:  # The public event receives a safe category only.
                messages.put(("error", exc))

        worker = Thread(target=run_turn, name=f"nova-stream-{request.request_id[-12:]}", daemon=True)
        worker.start()
        sequence = 0
        completed = False
        last_event_at = time.monotonic()
        try:
            while not completed:
                if cancel_event.is_set() and not worker.is_alive() and messages.empty():
                    yield NovaStreamEvent(
                        "response.cancelled",
                        response_id,
                        sequence,
                        error={"type": "cancelled", "message": "The Nova request was cancelled."},
                        done=True,
                    )
                    return
                try:
                    poll_timeout = max(0.001, min(0.2, self._stream_heartbeat_seconds / 2.0))
                    kind, payload = messages.get(timeout=poll_timeout)
                except Empty:
                    now = time.monotonic()
                    if now - last_event_at >= self._stream_heartbeat_seconds:
                        heartbeat_metadata = {
                            "request_id": request.request_id,
                            "elapsed_seconds": max(0, int(now - stream_started)),
                        }
                        if latest_progress:
                            heartbeat_metadata.update(latest_progress)
                        yield NovaStreamEvent(
                            "response.heartbeat",
                            response_id,
                            sequence,
                            metadata=heartbeat_metadata,
                        )
                        sequence += 1
                        last_event_at = now
                    continue
                if kind == "progress":
                    yield NovaStreamEvent(
                        "response.progress",
                        response_id,
                        sequence,
                        metadata={
                            **payload,
                            "request_id": request.request_id,
                            "elapsed_seconds": max(0, int(time.monotonic() - stream_started)),
                            "content_logged": False,
                        },
                    )
                    sequence += 1
                    last_event_at = time.monotonic()
                    continue
                if kind == "delta":
                    emitted_parts.append(payload)
                    yield NovaStreamEvent("content.delta", response_id, sequence, delta=payload)
                    sequence += 1
                    last_event_at = time.monotonic()
                    continue
                if kind == "error":
                    raise ProviderUnavailableError(
                        "Nova's cognitive streaming turn failed safely.",
                        request_id=request.request_id,
                    ) from payload

                completed = True
                if cancel_event.is_set():
                    yield NovaStreamEvent(
                        "response.cancelled",
                        response_id,
                        sequence,
                        error={"type": "cancelled", "message": "The Nova request was cancelled."},
                        done=True,
                    )
                    return
                final_content = str(payload.get("content") or "")
                emitted = "".join(emitted_parts)
                if not emitted and final_content:
                    # Direct Nova routes are already complete and do not pretend
                    # to be token streams; they are returned as one immediate delta.
                    yield NovaStreamEvent("content.delta", response_id, sequence, delta=final_content)
                    sequence += 1
                    emitted = final_content
                elif final_content.startswith(emitted):
                    tail = final_content[len(emitted) :]
                    if tail:
                        yield NovaStreamEvent("content.delta", response_id, sequence, delta=tail)
                        sequence += 1
                        emitted += tail
                elif final_content != emitted:
                    yield NovaStreamEvent(
                        "error",
                        response_id,
                        sequence,
                        error={
                            "type": "stream_integrity_error",
                            "message": "Nova stopped because final safety processing changed already-streamed text.",
                        },
                        done=True,
                    )
                    return

                yield NovaStreamEvent(
                    "response.completed",
                    response_id,
                    sequence,
                    usage={"estimated": True},
                    metadata={
                        "request_id": request.request_id,
                        "conversation_id": request.conversation_id,
                        "provider": self.provider_id,
                        "model": request.generation_options.model,
                        "latency_ms": payload.get("latency_ms"),
                        "trace": payload.get("trace") or {},
                    },
                    done=True,
                )
        finally:
            cancel_event.set()
            with self._lock:
                self._active_streams.pop(request.request_id, None)
                self._cancelled.discard(request.request_id)
            worker.join(timeout=0.2)

    def health_check(self) -> dict[str, Any]:
        return {
            "ok": callable(self._turn_runner),
            "provider_id": self.provider_id,
            "identity_preserved": True,
            "memory_preserved": True,
            "streaming": True,
            "streaming_mode": "native_cognitive_pipeline",
            "interface_version": self.interface_version,
        }

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            self._cancelled.add(request_id)
            active = self._active_streams.get(request_id)
            if active is not None:
                active.set()
        return True


class MockProvider(NovaModelProvider):
    """Deterministic offline provider for compatibility and policy tests."""

    provider_id = "mock"
    display_name = "Nova Deterministic Mock"

    def __init__(self, response_text: str = "Mock Nova response.", *, chunks: Iterable[str] | None = None):
        self.response_text = response_text
        self.chunks = list(chunks) if chunks is not None else [response_text]
        self.calls: list[NovaRequest] = []
        self.cancelled: set[str] = set()

    def list_models(self) -> list[NovaModelCapability]:
        return [
            NovaModelCapability(
                model_id="mock-text",
                provider_id=self.provider_id,
                display_name="Mock Text Model",
                embeddings=True,
                tool_calling=True,
                structured_output=True,
                streaming=True,
                reasoning=True,
                context_window=32_768,
                max_output_tokens=4_096,
                health_status="healthy",
            )
        ]

    def generate(self, request: NovaRequest) -> NovaResponse:
        self.calls.append(request)
        if request.request_id in self.cancelled:
            raise ProviderUnavailableError("Mock request was cancelled.", request_id=request.request_id)
        content = str(request.metadata.get("mock_response") or self.response_text)
        return NovaResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            model=request.generation_options.model,
            provider=self.provider_id,
            content=content,
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated": False},
            metadata={"deterministic": True},
        )

    def stream(self, request: NovaRequest) -> Iterator[NovaStreamEvent]:
        self.calls.append(request)
        response_id = new_id("resp")
        for sequence, chunk in enumerate(self.chunks):
            if request.request_id in self.cancelled:
                yield NovaStreamEvent(
                    event_type="error",
                    response_id=response_id,
                    sequence=sequence,
                    error={"type": "cancelled", "message": "Request cancelled."},
                    done=True,
                )
                return
            yield NovaStreamEvent("content.delta", response_id, sequence, delta=str(chunk))
        yield NovaStreamEvent("response.completed", response_id, len(self.chunks), done=True)

    def embed(self, inputs: list[str], model: str | None = None) -> list[list[float]]:
        return [[float(len(value)), float(sum(value.encode("utf-8")) % 997) / 997.0] for value in inputs]

    def cancel(self, request_id: str) -> bool:
        self.cancelled.add(request_id)
        return True


class OllamaProvider(NovaModelProvider):
    """Adapter around Nova's current Ollama connector plus its native stream API."""

    provider_id = "ollama"
    display_name = "Ollama"

    def __init__(self, connector: Any = None, *, base_url: str | None = None, model: str | None = None, timeout: int | None = None):
        if connector is None:
            from nova_local_llm_connector import LocalLLMConfig, LocalLLMConnector

            connector = LocalLLMConnector(LocalLLMConfig())
        self.connector = connector
        configured_url = str(base_url or connector.config.url)
        self.generate_url = configured_url if "/api/" in configured_url else configured_url.rstrip("/") + "/api/generate"
        self.base_url = self.generate_url.split("/api/", 1)[0].rstrip("/")
        self.default_model = str(model or connector.config.model)
        self.timeout = int(timeout or connector.config.timeout)
        self._cancel_events: dict[str, Event] = {}
        self._lock = RLock()

    def _json_request(self, path: str, *, payload: dict[str, Any] | None = None, timeout: int | None = None) -> Any:
        url = self.base_url + path
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderUnavailableError(f"Ollama is unavailable: {exc}") from exc

    def list_models(self) -> list[NovaModelCapability]:
        data = self._json_request("/api/tags", timeout=min(self.timeout, 5))
        models: list[NovaModelCapability] = []
        for item in data.get("models") or []:
            model_id = str(item.get("name") or item.get("model") or "").strip()
            if not model_id:
                continue
            models.append(
                NovaModelCapability(
                    model_id=model_id,
                    provider_id=self.provider_id,
                    display_name=model_id,
                    streaming=True,
                    reasoning=True,
                    context_window=getattr(self.connector.config, "context_window", None),
                    local_or_remote="local",
                    estimated_cost_type="free",
                    health_status="healthy",
                    metadata={"size": item.get("size"), "digest": item.get("digest")},
                )
            )
        return models

    def generate(self, request: NovaRequest) -> NovaResponse:
        prompt = self._prompt(request)
        options: dict[str, Any] = {}
        generation = request.generation_options
        if generation.temperature is not None:
            options["temperature"] = generation.temperature
        if generation.top_p is not None:
            options["top_p"] = generation.top_p
        if generation.max_tokens is not None:
            options["num_predict"] = generation.max_tokens
        if generation.seed is not None:
            options["seed"] = generation.seed
        if generation.stop:
            options["stop"] = generation.stop
        requested_context = request.metadata.get("provider_context_window")
        if requested_context is not None:
            try:
                options["num_ctx"] = max(1024, min(int(requested_context), 32768))
            except (TypeError, ValueError):
                pass
        timeout = self.timeout
        requested_timeout = request.metadata.get("provider_timeout_seconds")
        if requested_timeout is not None:
            try:
                extended_internal_timeout = bool(
                    request.metadata.get("internal_nova_managed")
                    and request.metadata.get("candidate_retry")
                )
                maximum_timeout = 600 if extended_internal_timeout else 60
                timeout = max(1, min(int(requested_timeout), maximum_timeout))
            except (TypeError, ValueError):
                timeout = self.timeout
        result = self.connector._call_ollama(
            prompt,
            options_override=options,
            model_override=self._resolved_model(request),
            timeout_override=timeout,
            keep_alive_override=str(
                request.metadata.get("provider_keep_alive")
                or getattr(self.connector.config, "ollama_keep_alive", "30m")
            ),
        )
        if not result.local_llm_used:
            raise ProviderUnavailableError(result.error or result.fallback_reason or "Ollama generation failed.", request_id=request.request_id)
        provider_done_reason = str(getattr(result, "finish_reason", "") or "").strip().lower()
        finish_reason = "length" if provider_done_reason in {"length", "max_tokens"} else "stop"
        return NovaResponse(
            request_id=request.request_id,
            conversation_id=request.conversation_id,
            model=result.model or self._resolved_model(request),
            provider=self.provider_id,
            content=result.raw_output,
            finish_reason=finish_reason,
            usage={"estimated": True},
            metadata={
                "latency_ms": result.response_time_ms,
                "nova_core_bypassed": True,
                "timeout_seconds": timeout,
                "provider_done_reason": provider_done_reason or None,
            },
        )

    def stream(self, request: NovaRequest) -> Iterator[NovaStreamEvent]:
        response_id = new_id("resp")
        cancel_event = Event()
        with self._lock:
            self._cancel_events[request.request_id] = cancel_event
        payload = {
            "model": self._resolved_model(request),
            "prompt": self._prompt(request),
            "stream": True,
            "options": self._ollama_options(request),
            "keep_alive": str(
                request.metadata.get("provider_keep_alive")
                or getattr(self.connector.config, "ollama_keep_alive", "30m")
            ),
        }
        http_request = urllib.request.Request(
            self.generate_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        sequence = 0
        try:
            with urllib.request.urlopen(http_request, timeout=self.timeout) as response:
                for raw_line in response:
                    if cancel_event.is_set():
                        return
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    delta = str(item.get("response") or "")
                    if delta:
                        yield NovaStreamEvent("content.delta", response_id, sequence, delta=delta)
                        sequence += 1
                    if item.get("done"):
                        yield NovaStreamEvent(
                            "response.completed",
                            response_id,
                            sequence,
                            usage={
                                "prompt_tokens": item.get("prompt_eval_count"),
                                "completion_tokens": item.get("eval_count"),
                                "estimated": False,
                            },
                            done=True,
                        )
                        return
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise ProviderUnavailableError(f"Ollama streaming failed: {exc}", request_id=request.request_id) from exc
        finally:
            with self._lock:
                self._cancel_events.pop(request.request_id, None)

    def embed(self, inputs: list[str], model: str | None = None) -> list[list[float]]:
        data = self._json_request("/api/embed", payload={"model": model or self.default_model, "input": inputs})
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list):
            raise ProviderUnavailableError("Ollama returned no embeddings.")
        return embeddings

    def health_check(self) -> dict[str, Any]:
        try:
            models = self.list_models()
            return {"ok": True, "provider_id": self.provider_id, "models": len(models), "interface_version": self.interface_version}
        except ProviderUnavailableError as exc:
            return {"ok": False, "provider_id": self.provider_id, "error": str(exc), "interface_version": self.interface_version}

    def warm_up_model(
        self,
        model_id: str | None = None,
        *,
        keep_alive: str | None = None,
        timeout: int | None = None,
    ) -> dict[str, Any]:
        """Preload one installed Ollama model with no generated answer."""

        selected = str(model_id or self.default_model)
        self.get_model_capabilities(selected)
        keep_alive_value = str(
            keep_alive
            or getattr(self.connector.config, "ollama_keep_alive", "30m")
        )
        started = time.monotonic()
        self._json_request(
            "/api/generate",
            payload={
                "model": selected,
                "prompt": "",
                "stream": False,
                "keep_alive": keep_alive_value,
                "options": {"num_predict": 0},
            },
            timeout=timeout or self.timeout,
        )
        return {
            "ok": True,
            "state": "ready",
            "provider": self.provider_id,
            "model": selected,
            "keep_alive": keep_alive_value,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
        }

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            event = self._cancel_events.get(request_id)
        if not event:
            return False
        event.set()
        return True

    def _resolved_model(self, request: NovaRequest) -> str:
        requested = request.metadata.get("provider_model")
        return str(requested or self.default_model)

    def _ollama_options(self, request: NovaRequest) -> dict[str, Any]:
        generation = request.generation_options
        options: dict[str, Any] = {"num_ctx": getattr(self.connector.config, "context_window", 16384)}
        if generation.temperature is not None:
            options["temperature"] = generation.temperature
        if generation.top_p is not None:
            options["top_p"] = generation.top_p
        if generation.max_tokens is not None:
            options["num_predict"] = generation.max_tokens
        if generation.seed is not None:
            options["seed"] = generation.seed
        if generation.stop:
            options["stop"] = generation.stop
        return options

    @staticmethod
    def _prompt(request: NovaRequest) -> str:
        lines = [
            "You are a replaceable language provider inside Nova Creature. Nova remains the identity, memory, permissions, and tool authority."
        ]
        for message in request.messages:
            content = message.text_content()
            if content:
                lines.append(f"{message.role.upper()}: {content}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)


class NovaProviderRegistry:
    """Thread-safe provider registry with aliases, health, and discovery."""

    def __init__(self, *, default_provider: str | None = None) -> None:
        self._providers: dict[str, NovaModelProvider] = {}
        self._aliases: dict[str, str] = {}
        self._default_provider = default_provider
        self._lock = RLock()

    def register_provider(self, provider: NovaModelProvider, *, aliases: Iterable[str] = ()) -> None:
        with self._lock:
            self._providers[provider.provider_id] = provider
            for alias in aliases:
                self._aliases[str(alias)] = provider.provider_id
            if self._default_provider is None:
                self._default_provider = provider.provider_id

    def unregister_provider(self, provider_id: str) -> None:
        with self._lock:
            self._providers.pop(provider_id, None)
            self._aliases = {alias: target for alias, target in self._aliases.items() if target != provider_id}
            if self._default_provider == provider_id:
                self._default_provider = next(iter(self._providers), None)

    def get_provider(self, provider_id: str | None = None) -> NovaModelProvider:
        with self._lock:
            requested = provider_id or self._default_provider
            requested = self._aliases.get(str(requested), str(requested))
            provider = self._providers.get(requested)
        if provider is None:
            raise ProviderUnavailableError(f"Nova provider {requested!r} is not registered.")
        return provider

    def set_default_provider(self, provider_id: str) -> None:
        self.get_provider(provider_id)
        with self._lock:
            self._default_provider = provider_id

    @property
    def default_provider_id(self) -> str | None:
        return self._default_provider

    def list_providers(self) -> list[dict[str, Any]]:
        with self._lock:
            values = list(self._providers.values())
        return [
            {
                "provider_id": provider.provider_id,
                "display_name": provider.display_name,
                "local_or_remote": provider.local_or_remote,
                "cost_type": provider.cost_type,
                "default": provider.provider_id == self._default_provider,
                "interface_version": provider.interface_version,
            }
            for provider in values
        ]

    def provider_health(self) -> dict[str, dict[str, Any]]:
        results: dict[str, dict[str, Any]] = {}
        with self._lock:
            values = list(self._providers.values())
        for provider in values:
            try:
                results[provider.provider_id] = provider.health_check()
            except Exception as exc:
                results[provider.provider_id] = {"ok": False, "provider_id": provider.provider_id, "error": str(exc)}
        return results

    def discover_models(self) -> list[NovaModelCapability]:
        models: list[NovaModelCapability] = []
        with self._lock:
            values = list(self._providers.values())
        for provider in values:
            try:
                models.extend(provider.list_models())
            except ProviderUnavailableError:
                continue
        return models
