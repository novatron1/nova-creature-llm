"""Nova's provider-independent orchestration layer."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from threading import RLock
import time
from typing import Any, Iterator

from nova_conversation_summary import conversation_continuity_metadata
from nova_evaluation_policy import (
    evaluation_mutation_reason,
    registered_evaluation_case_matches,
)
from nova_protocol import NovaRequest, NovaResponse, NovaStreamEvent, PROTOCOL_VERSION

from .config import GatewayConfig
from .comfyui import ComfyUIEngine
from .conversations import ConversationArchive
from .dream_lab import DREAM_LAB_SCHEMA_VERSION, NovaDreamLab
from .animatediff_cpu import NovaAnimateDiffCpuEngine
from .engines import NovaEngineRegistry
from .errors import (
    ModelUnavailableError,
    PermissionDeniedError,
    ProviderUnavailableError,
    ToolValidationError,
    UnsupportedFeatureError,
)
from .memory import ExistingNovaMemoryStore, MEMORY_MODES
from .model_registry import NovaModelCapability, NovaModelRegistry
from .providers import (
    PROVIDER_INTERFACE_VERSION,
    ExistingNovaProvider,
    NovaModelProvider,
    NovaProviderRegistry,
    OllamaProvider,
)
from .router import NovaTaskRouter, RoutingDecision
from .structured import parse_structured_output, validate_json_schema
from .tools import NovaRegisteredTool, NovaToolRegistry, registry_from_existing_tools
from .video_lite import NovaVideoLiteEngine
from .version import NOVA_VERSION
from .world_model import NovaWorldModel, WORLD_MODEL_SCHEMA_VERSION
from nova_runtime.contracts import build_run_contract
from nova_runtime.adapters import wrap_existing_tool_registry
from nova_gateway.memory import wrap_provenance_memory_backend


logger = logging.getLogger("nova.gateway")
NOVA_API_VERSION = "1.0"


def classify_memory_intent(text: str) -> str:
    value = " ".join(str(text or "").lower().split())
    write_markers = (
        "remember this", "save this", "save memory", "forget ", "delete saved memory",
        "update saved memory", "edit memory", "always remember", "permanently remember",
        "my name is ", "my favorite ", "i live in ", "i live at ", "i was born ",
        "i am from ", "i'm from ", "i like ", "i love ", "my birthday is ",
    )
    read_markers = (
        "show memory", "show memories", "list saved memor", "what do you remember",
        "do you remember", "recall ", "what is my ", "what's my ", "who is my ",
        "who am i", "do you know my ", "tell me what you know about me", "saved memory",
    )
    if any(marker in value for marker in write_markers):
        return "write"
    if any(marker in value for marker in read_markers):
        return "read"
    return "none"


def required_action_scopes(text: str) -> set[str]:
    """Conservatively gate existing agent routes before they see external input."""
    value = " ".join(str(text or "").lower().split())
    rules = (
        (("read file", "open file", "list files", "search project", "inspect file"), {"files.read"}),
        (("write file", "edit file", "delete file", "modify file", "patch file"), {"files.write", "tools.execute"}),
        (("run command", "shell command", "execute command", "run tests", "install package"), {"system.execute", "tools.execute"}),
        (("move robot", "robot move", "drive robot"), {"robot.move"}),
        (("robot status", "observe robot"), {"robot.observe"}),
        (("control game", "perform game action"), {"game.control"}),
        (("enable camera", "allow camera", "enable mic", "allow mic", "private mode", "emergency stop"), {"admin.config"}),
    )
    required: set[str] = set()
    for markers, scopes in rules:
        if any(marker in value for marker in markers):
            required.update(scopes)
    return required


class NovaGatewayCore:
    """Coordinates aliases, policies, providers, tools, memory, and safe output."""

    PUBLIC_ALIASES = ("nova", "nova-default", "nova-fast", "nova-deep", "nova-local", "nova-coder")

    def __init__(
        self,
        existing_turn_runner,
        *,
        config: GatewayConfig | None = None,
        providers: NovaProviderRegistry | None = None,
        models: NovaModelRegistry | None = None,
        tools: NovaToolRegistry | None = None,
        memory: ExistingNovaMemoryStore | None = None,
        world_model: NovaWorldModel | None = None,
        dream_lab: NovaDreamLab | None = None,
        engines: NovaEngineRegistry | None = None,
        comfyui: ComfyUIEngine | None = None,
        video_lite: NovaVideoLiteEngine | None = None,
        animatediff_cpu: NovaAnimateDiffCpuEngine | None = None,
        register_ollama: bool = True,
    ) -> None:
        self.config = config or GatewayConfig.from_env()
        if self.config.memory_mode not in MEMORY_MODES:
            raise ValueError(f"Unsupported NOVA_MEMORY_MODE {self.config.memory_mode!r}.")
        self.providers = providers or NovaProviderRegistry(default_provider=self.config.default_provider)
        self.models = models or NovaModelRegistry()
        if tools is not None:
            self.tools = tools
        else:
            try:
                from nova_tool_registry import get_default_tool_registry

                self.tools = get_default_tool_registry()
            except Exception:
                self.tools = registry_from_existing_tools()
        self.memory = memory or ExistingNovaMemoryStore(mode=self.config.memory_mode)
        self.provenance_memory = wrap_provenance_memory_backend(
            self.memory,
            owner_id="gateway",
            ledger_path=self.config.conversation_store_path.with_name("nova_memory_provenance.jsonl"),
        )
        self.conversations = ConversationArchive(self.config.conversation_store_path)
        self.world_model = world_model or NovaWorldModel(
            persistence=self.config.world_model_persistence,
            checkpoint_path=(
                self.config.world_model_checkpoint_path
                if self.config.world_model_persistence == "checkpoint"
                else None
            ),
            max_age_days=self.config.world_model_max_age_days,
        )
        self.dream_lab = dream_lab or NovaDreamLab(enabled=self.config.dream_lab_enabled)
        self.engines = engines or NovaEngineRegistry()
        self.comfyui = comfyui or ComfyUIEngine(
            enabled=self.config.comfyui_enabled,
            base_url=self.config.comfyui_base_url,
            image_workflow_path=self.config.comfyui_image_workflow_path,
            video_workflow_path=self.config.comfyui_video_workflow_path,
            job_store_path=self.config.comfyui_job_store_path,
            timeout_seconds=self.config.comfyui_timeout_seconds,
            launch_python_path=self.config.animatediff_cpu_python_path,
        )
        try:
            self.engines.get(self.comfyui.engine_id)
        except ProviderUnavailableError:
            self.engines.register_optional(self.comfyui)
        self.video_lite = video_lite or NovaVideoLiteEngine(
            enabled=self.config.video_lite_enabled,
            image_engine=self.comfyui,
            ffmpeg_path=self.config.video_lite_ffmpeg_path,
            output_dir=self.config.video_lite_output_dir,
            job_store_path=self.config.video_lite_job_store_path,
            encode_timeout_seconds=self.config.video_lite_encode_timeout_seconds,
        )
        try:
            self.engines.get(self.video_lite.engine_id)
        except ProviderUnavailableError:
            self.engines.register_optional(self.video_lite)
        self.animatediff_cpu = animatediff_cpu or NovaAnimateDiffCpuEngine(
            enabled=self.config.animatediff_cpu_enabled,
            python_path=self.config.animatediff_cpu_python_path,
            worker_script=self.config.animatediff_cpu_worker_path,
            model_path=self.config.animatediff_cpu_model_path,
            motion_adapter_path=self.config.animatediff_cpu_motion_adapter_path,
            output_dir=self.config.animatediff_cpu_output_dir,
            job_store_path=self.config.animatediff_cpu_job_store_path,
            encode_timeout_seconds=self.config.animatediff_cpu_timeout_seconds,
        )
        if self.config.animatediff_cpu_enabled or animatediff_cpu is not None:
            try:
                self.engines.get(self.animatediff_cpu.engine_id)
            except ProviderUnavailableError:
                self.engines.register_optional(self.animatediff_cpu)
        if self.config.comfyui_enabled:
            self._register_comfyui_tools()
        self._active_requests: dict[str, tuple[str, str]] = {}
        self._active_lock = RLock()
        self._agent_runs: dict[str, dict[str, Any]] = {}
        self._agent_run_lock = RLock()
        self._cost_lock = RLock()
        self._cost_month = time.strftime("%Y-%m", time.gmtime())
        self._estimated_cloud_spend = 0.0
        self._actual_cloud_spend = 0.0

        if not any(item["provider_id"] == "existing-nova" for item in self.providers.list_providers()):
            self.providers.register_provider(ExistingNovaProvider(existing_turn_runner), aliases=["nova-core"])
        self._register_provider_models(self.providers.get_provider("existing-nova"))
        for alias in self.PUBLIC_ALIASES:
            self.models.register_alias(alias, "existing-nova", "nova-core")

        if register_ollama:
            try:
                self.providers.get_provider("ollama")
            except Exception:
                try:
                    self.providers.register_provider(OllamaProvider(), aliases=["local-ollama"])
                except Exception as exc:
                    logger.info("Ollama provider extension was not registered: %s", exc)
            if self.config.expose_provider_models:
                try:
                    ollama = self.providers.get_provider("ollama")
                    self._register_provider_models(ollama)
                    for capability in ollama.list_models():
                        self.models.register_alias(f"ollama/{capability.model_id}", "ollama", capability.model_id)
                except Exception as exc:
                    logger.info("Raw Ollama model discovery was unavailable: %s", exc)

        self.router = NovaTaskRouter(self.providers, self.models, self.config)

    def _register_comfyui_tools(self) -> None:
        """Expose stable permission-scoped Nova tool names over the optional engine."""
        existing = {item["name"] for item in self.tools.list()}
        common_properties = {
            "prompt": {"type": "string", "minLength": 1, "maxLength": 8000},
            "negative_prompt": {"type": "string", "maxLength": 4000},
            "seed": {"type": "integer", "minimum": 0},
            "width": {"type": "integer", "minimum": 64, "maximum": 4096},
            "height": {"type": "integer", "minimum": 64, "maximum": 4096},
            "steps": {"type": "integer", "minimum": 1, "maximum": 200},
        }
        if "nova_generate_image" not in existing:
            self.tools.register(
                NovaRegisteredTool(
                    name="nova_generate_image",
                    version="1.0",
                    description="Queue a local text-to-image job through Nova's configured ComfyUI engine.",
                    input_schema={
                        "type": "object",
                        "properties": common_properties,
                        "required": ["prompt"],
                        "additionalProperties": False,
                    },
                    required_permissions=["image.generate"],
                    handler=lambda args: self.comfyui.generate_image(
                        str(args.pop("prompt")),
                        owner_id="nova-tool",
                        **args,
                    ),
                    local_or_remote="local",
                    risk_level="resource_intensive",
                    confirmation_policy="never",
                    timeout=self.config.comfyui_timeout_seconds + 5,
                    health_status="dynamic",
                    metadata={
                        "engine_id": self.comfyui.engine_id,
                        "async_job": True,
                        "availability_endpoint": "/nova/v1/engines",
                    },
                )
            )
        if "nova_generate_video" not in existing:
            video_properties = {
                **common_properties,
                "frames": {"type": "integer", "minimum": 1, "maximum": 4096},
                "fps": {"type": "integer", "minimum": 1, "maximum": 120},
                "motion": {
                    "type": "string",
                    "enum": [
                        "slow_zoom_in",
                        "slow_zoom_out",
                        "pan_left",
                        "pan_right",
                    ],
                },
            }
            self.tools.register(
                NovaRegisteredTool(
                    name="nova_generate_video",
                    version="1.0",
                    description="Queue a permission-scoped local video job through Nova's selected media engine.",
                    input_schema={
                        "type": "object",
                        "properties": video_properties,
                        "required": ["prompt"],
                        "additionalProperties": False,
                    },
                    required_permissions=["video.generate"],
                    handler=self._generate_video_tool,
                    local_or_remote="local",
                    risk_level="resource_intensive",
                    confirmation_policy="never",
                    timeout=self.config.comfyui_timeout_seconds + 5,
                    health_status="dynamic",
                    metadata={
                        "engine_selection": "capability_based",
                        "async_job": True,
                        "availability_endpoint": "/nova/v1/engines",
                    },
                )
            )

    def _generate_video_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        payload = dict(args)
        return self.generate_video(payload, client_id="nova-tool")

    def _register_provider_models(self, provider: NovaModelProvider) -> None:
        for capability in provider.list_models():
            self.models.register_model(capability)

    def register_provider(
        self,
        provider: NovaModelProvider,
        *,
        aliases: dict[str, str] | None = None,
        provider_aliases: list[str] | None = None,
    ) -> None:
        self.providers.register_provider(provider, aliases=provider_aliases or [])
        self._register_provider_models(provider)
        for alias, model_id in (aliases or {}).items():
            self.models.register_alias(alias, provider.provider_id, model_id)

    def _enforce_memory_policy(self, request: NovaRequest) -> None:
        scopes = set(request.metadata.get("client_scopes") or [])
        intent = classify_memory_intent(request.last_user_text())
        mode = self.config.memory_mode
        evaluation_only = self._is_evaluation_only(request)
        if intent == "read" and "memory.read" not in scopes:
            raise PermissionDeniedError("This client is not allowed to read Nova memory.", request_id=request.request_id)
        if intent == "write":
            if "memory.write" not in scopes:
                raise PermissionDeniedError("This client is not allowed to write Nova memory.", request_id=request.request_id)
            if mode in {"disabled", "read_only"}:
                raise PermissionDeniedError(f"Nova memory writes are blocked in {mode!r} mode.", request_id=request.request_id)
        request.metadata["memory_read_allowed"] = "memory.read" in scopes and mode != "disabled"
        request.metadata["memory_write_allowed"] = "memory.write" in scopes and mode not in {"disabled", "read_only"}
        request.metadata["conversation_memory_allowed"] = "memory.read" in scopes
        request.metadata["memory_mode"] = mode
        if evaluation_only:
            request.metadata["memory_write_allowed"] = False
            request.metadata["conversation_memory_allowed"] = False

    @staticmethod
    def _is_evaluation_only(request: NovaRequest) -> bool:
        return (
            request.metadata.get("evaluation_only") is True
            and request.metadata.get("_nova_evaluation_trusted") is True
        )

    def _enforce_evaluation_policy(self, request: NovaRequest) -> None:
        claimed = request.metadata.get("evaluation_only") is True
        trusted = request.metadata.get("_nova_evaluation_trusted") is True
        if claimed != trusted:
            raise PermissionDeniedError(
                "Evaluation-only mode requires a trusted local Nova-native request.",
                request_id=request.request_id,
            )
        if not claimed:
            return
        request.privacy_mode = "local_only"
        desktop_context = request.metadata.get("desktop_context")
        reason = evaluation_mutation_reason(
            request.last_user_text(),
            has_tools=bool(request.tools),
            context_flags=desktop_context if isinstance(desktop_context, dict) else request.metadata,
        )
        if reason:
            raise PermissionDeniedError(
                f"Evaluation-only requests cannot perform {reason}.",
                request_id=request.request_id,
            )
        if not registered_evaluation_case_matches(
            request.metadata.get("evaluation_case_id"),
            request.last_user_text(),
        ):
            raise PermissionDeniedError(
                "Evaluation-only requests require an exact registered acceptance case.",
                request_id=request.request_id,
            )

    def _enforce_evaluation_route(
        self,
        request: NovaRequest,
        decision: RoutingDecision,
        provider: NovaModelProvider,
    ) -> None:
        if not self._is_evaluation_only(request):
            return
        local = (
            bool(decision.remains_local)
            and str(provider.local_or_remote).casefold() == "local"
        )
        free = (
            str(provider.cost_type).casefold() == "free"
            and float(decision.estimated_cost or 0.0) <= 0.0
        )
        if not (local and free):
            raise PermissionDeniedError(
                "Evaluation-only routing requires a local and free provider; "
                "remote or paid execution cannot bypass Nova accounting.",
                request_id=request.request_id,
            )

    @staticmethod
    def _non_retained_projection() -> dict[str, Any]:
        return {
            "evaluation_only": True,
            "retained": False,
            "prompt_content_stored": False,
            "response_content_stored": False,
        }

    @staticmethod
    def _enforce_action_policy(request: NovaRequest) -> None:
        scopes = set(request.metadata.get("client_scopes") or [])
        required = required_action_scopes(request.last_user_text())
        missing = required - scopes
        if missing:
            raise PermissionDeniedError(
                f"This Nova action requires client scopes: {', '.join(sorted(missing))}.",
                request_id=request.request_id,
            )

    def _record_start(self, request_id: str, provider_id: str, client_id: str) -> None:
        with self._active_lock:
            self._active_requests[request_id] = (provider_id, client_id)

    def _record_done(self, request_id: str) -> None:
        with self._active_lock:
            self._active_requests.pop(request_id, None)

    def _record_response_continuity(
        self,
        request: NovaRequest,
        trace: Any,
        current_world_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist only safe continuity metadata emitted by Nova's real path."""

        if not isinstance(trace, dict):
            return current_world_state
        summary = trace.get("conversation_summary")
        if not isinstance(summary, (dict, str)):
            return current_world_state
        metadata = conversation_continuity_metadata(
            summary,
            fallback_topic=str(
                current_world_state.get("current_topic")
                or "general_conversation"
            ),
        )
        return self.world_model.record_continuity(
            request.client_id,
            request.conversation_id,
            metadata,
        )

    def generate(self, request: NovaRequest) -> NovaResponse:
        started = time.monotonic()
        self._enforce_evaluation_policy(request)
        self._enforce_action_policy(request)
        self._enforce_memory_policy(request)
        evaluation_only = self._is_evaluation_only(request)
        decision = self.router.select(request)
        if evaluation_only:
            request.metadata["world_model"] = self._non_retained_projection()
            request.metadata["dream_lab"] = self._non_retained_projection()
        else:
            request.metadata["world_model"] = self.world_model.begin_turn(request, decision.to_dict())
            request.metadata["dream_lab"] = self.dream_lab.simulate(request, decision.to_dict())
        try:
            provider = self.providers.get_provider(decision.selected_provider)
            self._enforce_evaluation_route(request, decision, provider)
            self._check_monthly_budget(decision, request)
        except Exception as exc:
            if not evaluation_only:
                self.world_model.fail_turn(request, exc.__class__.__name__)
            raise
        request.metadata["provider_model"] = decision.selected_model
        try:
            self._record_start(request.request_id, provider.provider_id, request.client_id)
            try:
                try:
                    response = provider.generate(request)
                except ProviderUnavailableError as original_error:
                    response, decision = self._generate_fallback(request, decision, original_error)
            finally:
                self._record_done(request.request_id)
            response.model = decision.requested_alias
            response.metadata["routing"] = decision.to_dict()
            response.metadata["latency_ms"] = round((time.monotonic() - started) * 1000, 3)
            response.metadata["nova_version"] = NOVA_VERSION
            response.metadata["api_version"] = NOVA_API_VERSION
            trace = response.metadata.get("trace")
            trace = trace if isinstance(trace, dict) else {}
            response.metadata["route_summary"] = {
                "provider": str(
                    trace.get("local_llm_provider")
                    or trace.get("remote_model_provider")
                    or response.provider
                    or decision.selected_provider
                )[:120],
                "model": str(
                    trace.get("local_llm_model")
                    or trace.get("model")
                    or decision.selected_model
                    or decision.requested_alias
                )[:120],
                "local": bool(decision.remains_local),
                "backend": str(
                    trace.get("gpu_backend")
                    or trace.get("compute_backend")
                    or ("local" if decision.remains_local else "remote")
                )[:80],
                "latency_ms": response.metadata["latency_ms"],
                "fallback": bool(trace.get("fallback_used") or response.metadata.get("fallback")),
            }
            response.metadata["dream_lab"] = dict(request.metadata.get("dream_lab") or {})
            if evaluation_only:
                response.metadata["evaluation_only"] = True
                response.metadata["retained_operational_state"] = False
            else:
                self._record_cost(decision, response)
            self._validate_tool_calls(request, response)
            if request.generation_options.response_format:
                value = parse_structured_output(response.content, request.generation_options.response_format)
                response.content = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
                response.metadata["structured_output_validated"] = True
            if evaluation_only:
                blackboard = self._non_retained_projection()
            else:
                blackboard = self.world_model.complete_turn(request, response)
                blackboard = self._record_response_continuity(
                    request,
                    response.metadata.get("trace"),
                    blackboard,
                )
            response.metadata["world_model"] = blackboard
            trace = response.metadata.get("trace")
            if isinstance(trace, dict):
                trace["world_model"] = blackboard
                trace["dream_lab"] = dict(request.metadata.get("dream_lab") or {})
            if not evaluation_only:
                self._log_request(request, response, decision)
            return response
        except Exception as exc:
            if not evaluation_only:
                self.world_model.fail_turn(request, exc.__class__.__name__)
            raise

    def _generate_fallback(
        self,
        request: NovaRequest,
        original: RoutingDecision,
        original_error: ProviderUnavailableError,
    ) -> tuple[NovaResponse, RoutingDecision]:
        if not self.config.fallback_enabled:
            raise original_error
        requirements = NovaTaskRouter._requirements(request)
        rejected = list(original.rejected_alternatives)
        rejected.append({"provider": original.selected_provider, "reason": str(original_error)})
        for capability in self.models.find_by_capability(*requirements):
            if capability.provider_id == original.selected_provider:
                continue
            try:
                provider = self.providers.get_provider(capability.provider_id)
                remote = capability.local_or_remote == "remote" or provider.local_or_remote == "remote"
                if remote and (request.privacy_mode == "local_only" or not self.config.allow_remote_models):
                    rejected.append({"provider": capability.provider_id, "reason": "remote execution denied by policy"})
                    continue
                if provider.cost_type == "paid" and not self.config.allow_paid_tools:
                    rejected.append({"provider": capability.provider_id, "reason": "paid execution denied by policy"})
                    continue
                request.metadata["provider_model"] = capability.model_id
                fallback_decision = RoutingDecision(
                    selected_provider=capability.provider_id,
                    selected_model=capability.model_id,
                    requested_alias=original.requested_alias,
                    reason=f"Primary provider failed safely; selected compatible fallback {capability.provider_id!r}.",
                    rejected_alternatives=rejected,
                    remains_local=not remote,
                    estimated_cost=float(provider.estimate_cost(request).get("estimated_cost") or 0.0),
                    fallback_path=[original.selected_provider, capability.provider_id],
                )
                try:
                    self._enforce_evaluation_route(
                        request,
                        fallback_decision,
                        provider,
                    )
                except PermissionDeniedError as exc:
                    rejected.append(
                        {
                            "provider": capability.provider_id,
                            "reason": str(exc),
                        }
                    )
                    continue
                self._check_monthly_budget(fallback_decision, request)
                self._record_start(request.request_id, capability.provider_id, request.client_id)
                response = provider.generate(request)
                return response, fallback_decision
            except ProviderUnavailableError as exc:
                rejected.append({"provider": capability.provider_id, "reason": str(exc)})
        raise ProviderUnavailableError(
            f"Primary provider failed and no policy-compliant fallback was available: {original_error}",
            request_id=request.request_id,
        ) from original_error

    def _roll_cost_month(self) -> None:
        month = time.strftime("%Y-%m", time.gmtime())
        with self._cost_lock:
            if month != self._cost_month:
                self._cost_month = month
                self._estimated_cloud_spend = 0.0
                self._actual_cloud_spend = 0.0

    def _check_monthly_budget(self, decision: RoutingDecision, request: NovaRequest) -> None:
        self._roll_cost_month()
        if decision.estimated_cost <= 0 or self.config.monthly_cloud_budget <= 0:
            return
        with self._cost_lock:
            projected = self._estimated_cloud_spend + decision.estimated_cost
        if projected > self.config.monthly_cloud_budget:
            raise PermissionDeniedError(
                "Estimated provider cost would exceed Nova's monthly cloud budget.",
                request_id=request.request_id,
            )

    def _record_cost(self, decision: RoutingDecision, response: NovaResponse) -> None:
        self._roll_cost_month()
        actual = response.metadata.get("actual_cost")
        try:
            actual_cost = float(actual) if actual is not None else 0.0
        except (TypeError, ValueError):
            actual_cost = 0.0
        with self._cost_lock:
            self._estimated_cloud_spend += max(0.0, float(decision.estimated_cost))
            self._actual_cloud_spend += max(0.0, actual_cost)
            response.metadata["cost"] = {
                "estimated_request": decision.estimated_cost,
                "actual_request": actual_cost if actual is not None else None,
                "month": self._cost_month,
                "estimated_month_total": self._estimated_cloud_spend,
                "actual_month_total": self._actual_cloud_spend,
                "monthly_budget": self.config.monthly_cloud_budget,
            }

    def _reserve_stream_estimate(
        self,
        request: NovaRequest,
        decision: RoutingDecision,
    ) -> dict[str, Any]:
        """Atomically budget-check and reserve a stream before provider entry."""

        self._roll_cost_month()
        estimate = max(0.0, float(decision.estimated_cost or 0.0))
        with self._cost_lock:
            projected = self._estimated_cloud_spend + estimate
            if (
                estimate > 0
                and self.config.monthly_cloud_budget > 0
                and projected > self.config.monthly_cloud_budget
            ):
                raise PermissionDeniedError(
                    "Estimated provider cost would exceed Nova's monthly cloud budget.",
                    request_id=request.request_id,
                )
            self._estimated_cloud_spend = projected
            return {
                "estimated_request": estimate,
                "actual_request": None,
                "month": self._cost_month,
                "estimated_month_total": self._estimated_cloud_spend,
                "actual_month_total": self._actual_cloud_spend,
                "monthly_budget": self.config.monthly_cloud_budget,
            }

    def _reconcile_stream_actual(
        self,
        cost: dict[str, Any],
        event: NovaStreamEvent,
    ) -> dict[str, Any]:
        """Add a provider-reported terminal actual without re-adding estimate."""

        raw_actual = event.metadata.get("actual_cost")
        if raw_actual is None:
            return dict(cost)
        try:
            actual = max(0.0, float(raw_actual))
        except (TypeError, ValueError):
            return dict(cost)
        self._roll_cost_month()
        with self._cost_lock:
            self._actual_cloud_spend += actual
            reconciled = dict(cost)
            reconciled.update(
                {
                    "actual_request": actual,
                    "month": self._cost_month,
                    "estimated_month_total": self._estimated_cloud_spend,
                    "actual_month_total": self._actual_cloud_spend,
                }
            )
            return reconciled

    def stream(self, request: NovaRequest) -> Iterator[NovaStreamEvent]:
        self._enforce_evaluation_policy(request)
        self._enforce_action_policy(request)
        self._enforce_memory_policy(request)
        evaluation_only = self._is_evaluation_only(request)
        if request.generation_options.response_format:
            raise UnsupportedFeatureError(
                "Structured output streaming is not enabled for Nova Core yet; use a non-streaming request so the complete JSON can be validated.",
                param="response_format",
                request_id=request.request_id,
            )
        decision = self.router.select(request)
        if evaluation_only:
            request.metadata["world_model"] = self._non_retained_projection()
            request.metadata["dream_lab"] = self._non_retained_projection()
        else:
            request.metadata["world_model"] = self.world_model.begin_turn(request, decision.to_dict())
            request.metadata["dream_lab"] = self.dream_lab.simulate(request, decision.to_dict())
        try:
            provider = self.providers.get_provider(decision.selected_provider)
            self._enforce_evaluation_route(request, decision, provider)
            stream_cost = (
                None
                if evaluation_only
                else self._reserve_stream_estimate(request, decision)
            )
        except Exception as exc:
            if not evaluation_only:
                self.world_model.fail_turn(request, exc.__class__.__name__)
            raise
        request.metadata["provider_model"] = decision.selected_model
        self._record_start(request.request_id, provider.provider_id, request.client_id)
        assembled: list[str] = []
        completed = False
        actual_reconciled = False
        try:
            for event in provider.stream(request):
                if event.delta:
                    assembled.append(event.delta)
                if event.done:
                    event.metadata.setdefault("request_id", request.request_id)
                    event.metadata.setdefault("conversation_id", request.conversation_id)
                    event.metadata.setdefault("model", decision.requested_alias)
                    event.metadata.setdefault("provider", decision.selected_provider)
                    event.metadata.setdefault("routing", decision.to_dict())
                    event.metadata.setdefault("nova_version", NOVA_VERSION)
                    event.metadata.setdefault("api_version", NOVA_API_VERSION)
                    event.metadata.setdefault("protocol_version", PROTOCOL_VERSION)
                    event.metadata.setdefault(
                        "dream_lab",
                        dict(request.metadata.get("dream_lab") or {}),
                    )
                    if not evaluation_only:
                        if not actual_reconciled and stream_cost is not None:
                            stream_cost = self._reconcile_stream_actual(
                                stream_cost,
                                event,
                            )
                            actual_reconciled = True
                        if stream_cost is not None:
                            event.metadata["cost"] = dict(stream_cost)
                    if evaluation_only:
                        blackboard = self._non_retained_projection()
                        event.metadata["evaluation_only"] = True
                        event.metadata["retained_operational_state"] = False
                    elif event.error:
                        blackboard = self.world_model.fail_turn(
                            request,
                            str(event.error.get("type") or "stream_error"),
                        )
                    else:
                        response = NovaResponse(
                            request_id=request.request_id,
                            conversation_id=request.conversation_id,
                            model=decision.requested_alias,
                            provider=decision.selected_provider,
                            content="".join(assembled),
                            finish_reason="stop",
                            metadata={
                                "latency_ms": event.metadata.get("latency_ms"),
                                "trace": event.metadata.get("trace") or {},
                                "dream_lab": dict(request.metadata.get("dream_lab") or {}),
                            },
                        )
                        blackboard = self.world_model.complete_turn(request, response)
                        blackboard = self._record_response_continuity(
                            request,
                            event.metadata.get("trace"),
                            blackboard,
                        )
                    event.metadata["world_model"] = blackboard
                    trace = event.metadata.get("trace")
                    if isinstance(trace, dict):
                        trace["world_model"] = blackboard
                        trace["dream_lab"] = dict(request.metadata.get("dream_lab") or {})
                    completed = True
                yield event
        except Exception as exc:
            if not evaluation_only:
                self.world_model.fail_turn(request, exc.__class__.__name__)
            raise
        finally:
            if not completed and not evaluation_only:
                self.world_model.fail_turn(request, "stream_interrupted")
            self._record_done(request.request_id)

    def embed(self, inputs: list[str], model_alias: str) -> tuple[list[list[float]], NovaModelCapability]:
        capability = self.models.resolve_alias(model_alias)
        if not capability.embeddings:
            raise ModelUnavailableError(f"Model {model_alias!r} does not support embeddings.")
        provider = self.providers.get_provider(capability.provider_id)
        if provider.local_or_remote == "remote" and not self.config.allow_remote_models:
            raise PermissionDeniedError("Remote embedding providers are disabled by Nova policy.")
        return provider.embed(inputs, capability.model_id), capability

    def cancel(self, request_id: str, *, client_id: str | None = None) -> bool:
        with self._active_lock:
            active = self._active_requests.get(request_id)
        if active:
            provider_id, owner_id = active
            if client_id is not None and client_id != owner_id:
                return False
            return self.providers.get_provider(provider_id).cancel(request_id)
        if client_id is not None:
            return False
        cancelled = False
        for item in self.providers.list_providers():
            try:
                cancelled = self.providers.get_provider(item["provider_id"]).cancel(request_id) or cancelled
            except Exception:
                continue
        return cancelled

    def generate_image(self, payload: dict[str, Any], *, client_id: str) -> dict[str, Any]:
        if not self.config.comfyui_enabled:
            raise UnsupportedFeatureError("ComfyUI support is disabled by NOVA_COMFYUI_ENABLED.")
        options = dict(payload)
        prompt = str(options.pop("prompt", "") or "")
        options["owner_id"] = client_id
        return self.comfyui.generate_image(prompt, **options)

    def launch_comfyui(self) -> dict[str, Any]:
        if not self.config.comfyui_enabled:
            raise UnsupportedFeatureError("ComfyUI support is disabled by NOVA_COMFYUI_ENABLED.")
        return self.comfyui.launch_local_server()

    def list_conversations(
        self,
        *,
        client_id: str,
        query: str = "",
        include_archived: bool = False,
        limit: int = 100,
    ) -> dict[str, Any]:
        rows = self.conversations.list(
            client_id,
            query=query,
            include_archived=include_archived,
            limit=limit,
        )
        return {
            "object": "list",
            "data": rows,
            "privacy": {
                "other_clients_returned": False,
                "private_reasoning_returned": False,
                "secrets_returned": False,
            },
        }

    def save_conversation(
        self,
        *,
        client_id: str,
        conversation_id: str,
        title: str | None,
        messages: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        return self.conversations.save(
            client_id,
            conversation_id,
            title=title,
            messages=messages,
        )

    def get_conversation(self, *, client_id: str, conversation_id: str) -> dict[str, Any] | None:
        return self.conversations.get(client_id, conversation_id)

    def archive_conversation(self, *, client_id: str, conversation_id: str) -> bool:
        return self.conversations.archive(client_id, conversation_id)

    def restore_conversation(self, *, client_id: str, conversation_id: str) -> bool:
        return self.conversations.restore(client_id, conversation_id)

    def delete_conversation(self, *, client_id: str, conversation_id: str) -> bool:
        return self.conversations.delete(client_id, conversation_id)

    def generate_video(self, payload: dict[str, Any], *, client_id: str) -> dict[str, Any]:
        options = dict(payload)
        prompt = str(options.pop("prompt", "") or "")
        requested_engine = str(options.pop("engine_id", "") or "").strip()
        options["owner_id"] = client_id
        return self._select_video_engine(requested_engine or None).text_to_video(prompt, **options)

    def _select_video_engine(self, requested_engine: str | None = None):
        if requested_engine:
            candidates = {
                self.comfyui.engine_id: self.comfyui,
                self.video_lite.engine_id: self.video_lite,
                self.animatediff_cpu.engine_id: self.animatediff_cpu,
            }
            engine = candidates.get(str(requested_engine).strip())
            if engine is None:
                raise UnsupportedFeatureError(
                    f"Requested video engine {requested_engine!r} is not registered."
                )
            health = engine.health_check()
            if not health.get("ok"):
                raise UnsupportedFeatureError(
                    f"Requested video engine {requested_engine!r} is unavailable: "
                    f"{health.get('status') or 'health check failed'}."
                )
            return engine
        comfy_health = self.comfyui.health_check()
        if (
            comfy_health.get("ok")
            and comfy_health.get("video_workflow_configured")
        ):
            return self.comfyui
        animatediff_health = self.animatediff_cpu.health_check()
        if animatediff_health.get("ok"):
            return self.animatediff_cpu
        video_lite_health = self.video_lite.health_check()
        if video_lite_health.get("ok"):
            return self.video_lite
        raise UnsupportedFeatureError(
            "No local Nova video engine is ready. Configure a ComfyUI video workflow "
            "or enable Nova Video Lite with FFmpeg and a ready image workflow."
        )

    def _media_engine_for_job(self, job_id: str):
        if str(job_id).startswith("nad_"):
            return self.animatediff_cpu
        if str(job_id).startswith("nvl_"):
            return self.video_lite
        return self.comfyui

    def media_job_status(self, job_id: str, *, client_id: str) -> dict[str, Any]:
        return self._media_engine_for_job(job_id).job_status(
            job_id,
            owner_id=client_id,
        )

    def list_media_jobs(self, *, client_id: str, limit: int = 25) -> dict[str, Any]:
        safe_limit = max(1, min(int(limit), 100))
        comfy_jobs = self.comfyui.list_jobs(
            owner_id=client_id,
            limit=safe_limit,
        )
        video_jobs = self.video_lite.list_jobs(
            owner_id=client_id,
            limit=safe_limit,
        )
        animatediff_jobs = self.animatediff_cpu.list_jobs(
            owner_id=client_id,
            limit=safe_limit,
        )
        media_jobs = [*comfy_jobs["data"], *video_jobs["data"], *animatediff_jobs["data"]]
        if not media_jobs:
            return comfy_jobs
        combined = sorted(
            media_jobs,
            key=lambda item: str(item.get("created_at") or ""),
            reverse=True,
        )[:safe_limit]
        return {
            "object": "list",
            "engine_id": "nova-media",
            "data": combined,
            "privacy": {
                "prompt_content_returned": False,
                "workflow_content_returned": False,
                "other_clients_jobs_returned": False,
            },
        }

    def cancel_media_job(self, job_id: str, *, client_id: str) -> bool:
        return self._media_engine_for_job(job_id).cancel_job(
            job_id,
            owner_id=client_id,
        )

    def resume_media_job(self, job_id: str, *, client_id: str) -> dict[str, Any]:
        engine = self._media_engine_for_job(job_id)
        resume = getattr(engine, "resume_job", None)
        if not callable(resume):
            raise UnsupportedFeatureError("This media engine does not support resume.")
        return resume(job_id, owner_id=client_id)

    def open_media_job_output(
        self,
        job_id: str,
        output_index: int,
        *,
        client_id: str,
    ) -> dict[str, Any]:
        return self._media_engine_for_job(job_id).open_job_output(
            job_id,
            output_index,
            owner_id=client_id,
        )

    def _validate_tool_calls(self, request: NovaRequest, response: NovaResponse) -> None:
        definitions = {tool.name: tool for tool in request.tools}
        for call in response.tool_calls:
            definition = definitions.get(call.name)
            if definition is None:
                raise ToolValidationError(f"Provider requested undeclared client tool {call.name!r}.", request_id=request.request_id)
            errors = validate_json_schema(call.arguments, definition.input_schema)
            if errors:
                raise ToolValidationError(" ".join(errors), request_id=request.request_id)

    @staticmethod
    def _log_request(request: NovaRequest, response: NovaResponse, decision: RoutingDecision) -> None:
        logger.info(
            "nova_request complete request_id=%s client_id=%s provider=%s model=%s local=%s latency_ms=%s success=%s",
            request.request_id, request.client_id, decision.selected_provider, decision.selected_model,
            decision.remains_local, response.metadata.get("latency_ms"), not bool(response.errors),
        )

    def model_aliases(self) -> list[dict[str, Any]]:
        output = []
        for alias, capability in sorted(self.models.aliases().items()):
            output.append(
                {
                    "id": alias,
                    "provider_id": capability.provider_id,
                    "provider_model": capability.model_id,
                    "display_name": capability.display_name,
                    "capabilities": capability.to_dict(),
                }
            )
        return output

    def capabilities(self) -> dict[str, Any]:
        return {
            "nova_version": NOVA_VERSION,
            "api_version": NOVA_API_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "memory_schema_version": "1.0",
            "tool_schema_version": "1.0",
            "provider_interface_version": PROVIDER_INTERFACE_VERSION,
            "capability_schema_version": "1.0",
            "world_model_schema_version": WORLD_MODEL_SCHEMA_VERSION,
            "dream_lab_schema_version": DREAM_LAB_SCHEMA_VERSION,
            "identity_version": "existing-nova",
            "models": self.model_aliases(),
            "privacy_modes": ["local_only", "local_preferred", "balanced", "remote_allowed", "user_confirmation_required"],
            "streaming": {
                "status": "FULL",
                "note": "The default Nova aliases stream through the cognitive pipeline. Model text is safety-buffered by sentence or line; deterministic routes return one immediate delta.",
            },
            "mcp": {"client": "NOT IMPLEMENTED", "server": "NOT IMPLEMENTED", "extension_boundary": True},
            "world_model": {
                "status": "EXPERIMENTAL",
                "provider_independent": True,
                "persistence": self.world_model.health_check().get("persistence"),
                "restart_safe": self.world_model.health_check().get("checkpoint_enabled", False),
                "prompt_content_stored": False,
                "response_content_stored": False,
                "private_chain_of_thought_stored": False,
                "endpoint": "/nova/v1/world-model",
            },
            "dream_lab": {
                "status": "EXPERIMENTAL",
                "enabled": self.config.dream_lab_enabled,
                "bounded_counterfactuals": True,
                "provider_calls": 0,
                "executes_actions": False,
                "prompt_content_stored": False,
                "private_reasoning_stored": False,
                "endpoint": "/nova/v1/dream-lab",
            },
            "engines": {
                "endpoint": "/nova/v1/engines",
                "comfyui": self.comfyui.capabilities(),
                "video_lite": self.video_lite.capabilities(),
            },
            "dream_studio": {
                "status": "PARTIAL",
                "ui_panel": True,
                "device_scoped_media_permissions": True,
                "job_history_endpoint": "/nova/v1/jobs",
                "media_access_endpoint": "/nova/v1/media/access",
                "requires_configured_engine": True,
            },
        }

    def health(self, *, detailed: bool = True) -> dict[str, Any]:
        provider_health = self.providers.provider_health() if detailed else {}
        existing = provider_health.get("existing-nova") or self.providers.get_provider("existing-nova").health_check()
        memory_health = self.memory.health_check()
        tool_health = self.tools.health_check()
        world_health = self.world_model.health_check()
        dream_health = self.dream_lab.health_check()
        engine_health = self.engines.health_check()
        ok = (
            bool(existing.get("ok"))
            and bool(memory_health.get("ok"))
            and bool(tool_health.get("ok"))
            and bool(world_health.get("ok"))
            and bool(dream_health.get("ok"))
            and bool(engine_health.get("ok"))
        )
        return {
            "ok": ok,
            "nova_version": NOVA_VERSION,
            "api_version": NOVA_API_VERSION,
            "cognitive_core": existing,
            "memory_store": memory_health,
            "provider_registry": {"ok": bool(self.providers.list_providers()), "providers": provider_health},
            "model_registry": {"ok": bool(self.models.aliases()), "aliases": len(self.models.aliases())},
            "tool_registry": tool_health,
            "world_model": world_health,
            "dream_lab": dream_health,
            "engines": engine_health,
            "cost": self.cost_status(),
        }

    def runtime_tool_descriptors(self) -> dict[str, Any]:
        """Return the current tools projected through the canonical runtime interface."""

        return wrap_existing_tool_registry(self.tools)

    def runtime_contract(self) -> dict[str, Any]:
        """Build a frozen runtime contract snapshot for the current gateway state."""

        workspace_root = str(Path.cwd().resolve())
        tool_descriptors = self.runtime_tool_descriptors()
        allowed_tools = sorted(tool_descriptors)
        allowed_resources = sorted(
            {
                dependency
                for descriptor in tool_descriptors.values()
                for dependency in getattr(descriptor, "resource_dependencies", ())
            }
        )
        contract = build_run_contract(
            run_id=f"gateway-{self.config.port}",
            goal="Operate Nova Creature through the current gateway runtime.",
            owner_id="gateway",
            project_id="nova-creature",
            workspace_root=workspace_root,
            allowed_roots=[workspace_root],
            allowed_tools=allowed_tools,
            allowed_resources=allowed_resources or ["filesystem://workspace"],
            time_budget_seconds=self.config.request_timeout_seconds,
            tool_budget=max(1, len(allowed_tools)),
            cost_budget=float(self.config.per_request_limit),
            memory_budget=8,
            metadata={
                "gateway_port": self.config.port,
                "config_version": self.config.config_version,
            },
        )
        return {
            "object": "nova.runtime_contract",
            "data": contract.to_dict(),
            "tools": {name: descriptor.to_public_dict() for name, descriptor in tool_descriptors.items()},
        }

    def register_agent_run(
        self,
        *,
        run: Any,
        report: Any,
        report_path: str | Path,
        workspace_root: str | Path,
        proof_artifacts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "run_id": str(getattr(getattr(run, "contract", None), "run_id", "") or ""),
            "state": str(getattr(getattr(run, "state", None), "value", getattr(run, "state", "planned"))),
            "contract": (
                run.contract.to_dict()
                if hasattr(getattr(run, "contract", None), "to_dict")
                else {}
            ),
            "history": list(getattr(run, "history", [])),
            "report": report.to_dict() if hasattr(report, "to_dict") else dict(report or {}),
            "report_path": str(report_path),
            "workspace_root": str(workspace_root),
            "proof_artifacts": dict(proof_artifacts or {}),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        with self._agent_run_lock:
            self._agent_runs[payload["run_id"]] = payload
        return payload

    def list_agent_runs(self) -> dict[str, Any]:
        with self._agent_run_lock:
            data = [dict(item) for item in self._agent_runs.values()]
        data.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return {"object": "list", "data": data}

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        with self._agent_run_lock:
            run = self._agent_runs.get(str(run_id))
            return dict(run) if run is not None else None

    def rollback_agent_run(self, run_id: str, *, reason: str = "operator_requested") -> dict[str, Any]:
        with self._agent_run_lock:
            run = self._agent_runs.get(str(run_id))
            if run is None:
                return {"ok": False, "found": False, "run_id": str(run_id)}
            run = dict(run)
            run["state"] = "rolled_back"
            run["rollback"] = {
                "available": True,
                "reason": reason,
                "rolled_back_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            run["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._agent_runs[str(run_id)] = run
        return {"ok": True, "found": True, "run_id": str(run_id), "state": "rolled_back"}

    def cost_status(self) -> dict[str, Any]:
        self._roll_cost_month()
        with self._cost_lock:
            return {
                "month": self._cost_month,
                "estimated_cloud_spend": self._estimated_cloud_spend,
                "actual_cloud_spend": self._actual_cloud_spend,
                "monthly_cloud_budget": self.config.monthly_cloud_budget,
                "allow_paid_tools": self.config.allow_paid_tools,
            }
