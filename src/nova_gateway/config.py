"""Environment-backed gateway policy with secure local-first defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Mapping


CONFIG_VERSION = "1.3"


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _int(env: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(env.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _float(env: Mapping[str, str], name: str, default: float, minimum: float = 0.0) -> float:
    try:
        return max(minimum, float(env.get(name, default)))
    except (TypeError, ValueError):
        return default


def _csv(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in str(env.get(name, "")).split(",") if item.strip())


def _choice(env: Mapping[str, str], name: str, default: str, allowed: set[str]) -> str:
    value = str(env.get(name, default) or default).strip().lower()
    return value if value in allowed else default


@dataclass(frozen=True)
class GatewayConfig:
    """Validated settings for the HTTP compatibility gateway."""

    enabled: bool = True
    host: str = "127.0.0.1"
    port: int = 8765
    enable_remote_access: bool = False
    allow_local_no_auth: bool = True
    allowed_origins: tuple[str, ...] = ()
    trust_proxy_headers: bool = False
    trust_tailscale_serve: bool = False
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60
    max_request_size_bytes: int = 16 * 1024 * 1024
    request_timeout_seconds: int = 120
    expose_provider_models: bool = False
    default_provider: str = "existing-nova"
    default_model_alias: str = "nova"
    execution_policy: str = "local_preferred"
    fallback_enabled: bool = True
    allow_remote_models: bool = False
    allow_private_data_remote: bool = False
    allow_private_files_remote: bool = False
    allow_paid_tools: bool = False
    monthly_cloud_budget: float = 0.0
    per_request_limit: float = 0.0
    require_confirmation_over: float = 0.0
    memory_mode: str = "automatic_safe_write"
    client_registry_path: Path = field(default_factory=lambda: Path("data") / "nova_gateway_clients.json")
    world_model_persistence: str = "session"
    world_model_checkpoint_path: Path = field(default_factory=lambda: Path("data") / "nova_world_model.json")
    world_model_max_age_days: int = 30
    dream_lab_enabled: bool = True
    comfyui_enabled: bool = False
    comfyui_base_url: str = "http://127.0.0.1:8188"
    comfyui_image_workflow_path: Path | None = None
    comfyui_video_workflow_path: Path | None = None
    comfyui_job_store_path: Path = field(default_factory=lambda: Path("data") / "nova_comfyui_jobs.json")
    comfyui_timeout_seconds: int = 15
    video_lite_enabled: bool = True
    video_lite_ffmpeg_path: Path | None = None
    video_lite_output_dir: Path = field(
        default_factory=lambda: Path("data") / "nova_video_lite"
    )
    video_lite_job_store_path: Path = field(
        default_factory=lambda: Path("data") / "nova_video_lite_jobs.json"
    )
    video_lite_encode_timeout_seconds: int = 180
    config_version: str = CONFIG_VERSION

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        root: str | Path | None = None,
        default_port: int = 8765,
    ) -> "GatewayConfig":
        source = env or os.environ
        root_path = Path(root or Path.cwd()).resolve()
        host = str(source.get("NOVA_API_HOST") or source.get("NOVA_HOST") or "127.0.0.1").strip()
        port = _int(source, "NOVA_API_PORT", _int(source, "NOVA_PORT", default_port, 1, 65535), 1, 65535)
        registry_value = str(source.get("NOVA_CLIENT_REGISTRY_PATH") or "data/nova_gateway_clients.json")
        registry_path = Path(registry_value)
        if not registry_path.is_absolute():
            registry_path = root_path / registry_path
        world_model_value = str(source.get("NOVA_WORLD_MODEL_PATH") or "data/nova_world_model.json")
        world_model_path = Path(world_model_value)
        if not world_model_path.is_absolute():
            world_model_path = root_path / world_model_path
        configured_image_value = str(source.get("NOVA_COMFYUI_IMAGE_WORKFLOW") or "").strip()
        local_image_workflow = root_path / "config" / "comfyui_text_to_image_workflow.local.json"
        comfyui_image_value = configured_image_value or (
            str(local_image_workflow) if local_image_workflow.is_file() else ""
        )
        comfyui_image_path = Path(comfyui_image_value) if comfyui_image_value else None
        if comfyui_image_path is not None and not comfyui_image_path.is_absolute():
            comfyui_image_path = root_path / comfyui_image_path
        comfyui_video_value = str(source.get("NOVA_COMFYUI_VIDEO_WORKFLOW") or "").strip()
        comfyui_video_path = Path(comfyui_video_value) if comfyui_video_value else None
        if comfyui_video_path is not None and not comfyui_video_path.is_absolute():
            comfyui_video_path = root_path / comfyui_video_path
        comfyui_jobs_value = str(
            source.get("NOVA_COMFYUI_JOB_STORE") or "data/nova_comfyui_jobs.json"
        ).strip()
        comfyui_jobs_path = Path(comfyui_jobs_value)
        if not comfyui_jobs_path.is_absolute():
            comfyui_jobs_path = root_path / comfyui_jobs_path
        video_lite_ffmpeg_value = str(source.get("NOVA_FFMPEG_PATH") or "").strip()
        video_lite_ffmpeg_path = (
            Path(video_lite_ffmpeg_value) if video_lite_ffmpeg_value else None
        )
        if (
            video_lite_ffmpeg_path is not None
            and not video_lite_ffmpeg_path.is_absolute()
        ):
            video_lite_ffmpeg_path = root_path / video_lite_ffmpeg_path
        video_lite_output_value = str(
            source.get("NOVA_VIDEO_LITE_OUTPUT_DIR") or "data/nova_video_lite"
        ).strip()
        video_lite_output_dir = Path(video_lite_output_value)
        if not video_lite_output_dir.is_absolute():
            video_lite_output_dir = root_path / video_lite_output_dir
        video_lite_jobs_value = str(
            source.get("NOVA_VIDEO_LITE_JOB_STORE")
            or "data/nova_video_lite_jobs.json"
        ).strip()
        video_lite_jobs_path = Path(video_lite_jobs_value)
        if not video_lite_jobs_path.is_absolute():
            video_lite_jobs_path = root_path / video_lite_jobs_path
        return cls(
            enabled=_bool(source, "NOVA_API_ENABLED", True),
            host=host,
            port=port,
            enable_remote_access=_bool(source, "NOVA_ENABLE_REMOTE_ACCESS", False),
            allow_local_no_auth=_bool(source, "NOVA_ALLOW_LOCAL_NO_AUTH", True),
            allowed_origins=_csv(source, "NOVA_ALLOWED_ORIGINS"),
            trust_proxy_headers=_bool(source, "NOVA_TRUST_PROXY_HEADERS", False),
            trust_tailscale_serve=_bool(
                source, "NOVA_TRUST_TAILSCALE_SERVE", False
            ),
            rate_limit_enabled=_bool(source, "NOVA_RATE_LIMIT_ENABLED", True),
            rate_limit_per_minute=_int(source, "NOVA_RATE_LIMIT_PER_MINUTE", 60, 1, 100_000),
            max_request_size_bytes=_int(source, "NOVA_MAX_REQUEST_SIZE", 16 * 1024 * 1024, 1024, 1024**3),
            request_timeout_seconds=_int(source, "NOVA_REQUEST_TIMEOUT", 120, 1, 3600),
            expose_provider_models=_bool(source, "NOVA_EXPOSE_PROVIDER_MODELS", False),
            default_provider=str(source.get("NOVA_DEFAULT_PROVIDER") or "existing-nova").strip(),
            default_model_alias=str(source.get("NOVA_DEFAULT_MODEL_ALIAS") or "nova").strip(),
            execution_policy=str(source.get("NOVA_EXECUTION_POLICY") or "local_preferred").strip(),
            fallback_enabled=_bool(source, "NOVA_PROVIDER_FALLBACK", True),
            allow_remote_models=_bool(source, "NOVA_ALLOW_REMOTE_MODELS", False),
            allow_private_data_remote=_bool(source, "NOVA_ALLOW_PRIVATE_DATA_REMOTE", False),
            allow_private_files_remote=_bool(source, "NOVA_ALLOW_PRIVATE_FILES_REMOTE", False),
            allow_paid_tools=_bool(source, "NOVA_ALLOW_PAID_TOOLS", False),
            monthly_cloud_budget=_float(source, "NOVA_MONTHLY_CLOUD_BUDGET", 0.0),
            per_request_limit=_float(source, "NOVA_PER_REQUEST_LIMIT", 0.0),
            require_confirmation_over=_float(source, "NOVA_REQUIRE_CONFIRMATION_OVER", 0.0),
            memory_mode=str(source.get("NOVA_MEMORY_MODE") or "automatic_safe_write").strip(),
            client_registry_path=registry_path,
            world_model_persistence=_choice(
                source,
                "NOVA_WORLD_MODEL_PERSISTENCE",
                "checkpoint",
                {"session", "checkpoint"},
            ),
            world_model_checkpoint_path=world_model_path,
            world_model_max_age_days=_int(source, "NOVA_WORLD_MODEL_MAX_AGE_DAYS", 30, 1, 3650),
            dream_lab_enabled=_bool(source, "NOVA_DREAM_LAB_ENABLED", True),
            comfyui_enabled=_bool(source, "NOVA_COMFYUI_ENABLED", True),
            comfyui_base_url=str(
                source.get("NOVA_COMFYUI_BASE_URL") or "http://127.0.0.1:8188"
            ).strip(),
            comfyui_image_workflow_path=comfyui_image_path,
            comfyui_video_workflow_path=comfyui_video_path,
            comfyui_job_store_path=comfyui_jobs_path,
            comfyui_timeout_seconds=_int(source, "NOVA_COMFYUI_TIMEOUT", 15, 1, 120),
            video_lite_enabled=_bool(source, "NOVA_VIDEO_LITE_ENABLED", True),
            video_lite_ffmpeg_path=video_lite_ffmpeg_path,
            video_lite_output_dir=video_lite_output_dir,
            video_lite_job_store_path=video_lite_jobs_path,
            video_lite_encode_timeout_seconds=_int(
                source,
                "NOVA_VIDEO_LITE_ENCODE_TIMEOUT",
                180,
                30,
                1800,
            ),
        )

    def public_dict(self) -> dict[str, object]:
        """Return non-secret operational settings for diagnostics."""
        return {
            "enabled": self.enabled,
            "host": self.host,
            "port": self.port,
            "remote_access": self.enable_remote_access,
            "allow_local_no_auth": self.allow_local_no_auth,
            "trust_tailscale_serve": self.trust_tailscale_serve,
            "rate_limit_enabled": self.rate_limit_enabled,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "max_request_size_bytes": self.max_request_size_bytes,
            "request_timeout_seconds": self.request_timeout_seconds,
            "expose_provider_models": self.expose_provider_models,
            "execution_policy": self.execution_policy,
            "memory_mode": self.memory_mode,
            "world_model_persistence": self.world_model_persistence,
            "world_model_max_age_days": self.world_model_max_age_days,
            "dream_lab_enabled": self.dream_lab_enabled,
            "comfyui_enabled": self.comfyui_enabled,
            "comfyui_endpoint_configured": bool(self.comfyui_base_url),
            "comfyui_image_workflow_configured": self.comfyui_image_workflow_path is not None,
            "comfyui_video_workflow_configured": self.comfyui_video_workflow_path is not None,
            "comfyui_timeout_seconds": self.comfyui_timeout_seconds,
            "video_lite_enabled": self.video_lite_enabled,
            "video_lite_ffmpeg_configured": self.video_lite_ffmpeg_path is not None,
            "video_lite_encode_timeout_seconds": self.video_lite_encode_timeout_seconds,
            "config_version": self.config_version,
        }
