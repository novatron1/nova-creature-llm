"""Optional local ComfyUI image/video job engine using only the standard library."""

from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import secrets
from threading import RLock
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .engines import NovaImageGenerationEngine, NovaVideoGenerationEngine
from .errors import (
    InvalidRequestError,
    PermissionDeniedError,
    ProviderUnavailableError,
    UnsupportedFeatureError,
)


COMFYUI_ENGINE_VERSION = "1.0"
COMFYUI_JOB_SCHEMA_VERSION = "1.0"
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_WORKFLOW_BYTES = 4 * 1024 * 1024
_MAX_OUTPUT_BYTES = 1024 * 1024 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_local_base_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("ComfyUI base URL must use http or https.")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ComfyUI base URL cannot contain credentials, a query, or a fragment.")
    if parsed.path not in {"", "/"}:
        raise ValueError("ComfyUI base URL must not contain an API path.")
    hostname = parsed.hostname.split("%", 1)[0].lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False
    if not is_loopback:
        raise ValueError("ComfyUI support is local-only; configure a loopback base URL.")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


def _replace_tokens(value: Any, replacements: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {str(key): _replace_tokens(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [_replace_tokens(item, replacements) for item in value]
    if not isinstance(value, str):
        return value
    if value in replacements:
        return replacements[value]
    output = value
    for token, replacement in replacements.items():
        output = output.replace(token, str(replacement))
    return output


def _contains_token(value: Any, token: str) -> bool:
    if isinstance(value, dict):
        return any(_contains_token(item, token) for item in value.values())
    if isinstance(value, list):
        return any(_contains_token(item, token) for item in value)
    return isinstance(value, str) and token in value


class ComfyUIEngine(NovaImageGenerationEngine, NovaVideoGenerationEngine):
    """Queue and inspect local ComfyUI API-format workflows."""

    engine_id = "comfyui-local"
    engine_type = "image_video_generation"
    local_or_remote = "local"
    cost_type = "free"

    def __init__(
        self,
        *,
        enabled: bool = False,
        base_url: str = "http://127.0.0.1:8188",
        image_workflow_path: str | Path | None = None,
        video_workflow_path: str | Path | None = None,
        job_store_path: str | Path | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        self.enabled = bool(enabled)
        self.timeout_seconds = _bounded_int(timeout_seconds, 15, 1, 120)
        self.image_workflow_path = Path(image_workflow_path).resolve() if image_workflow_path else None
        self.video_workflow_path = Path(video_workflow_path).resolve() if video_workflow_path else None
        self.job_store_path = Path(job_store_path).resolve() if job_store_path else None
        self.client_id = "nova-" + secrets.token_hex(12)
        self._lock = RLock()
        self._job_store_lock = RLock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._health_cache: tuple[float, dict[str, Any]] | None = None
        self._configuration_error = ""
        self._job_store_error = ""
        try:
            self.base_url = _validate_local_base_url(base_url)
        except ValueError as exc:
            self.base_url = str(base_url or "")
            self._configuration_error = str(exc)
        self._load_jobs()

    def _url(self, path: str) -> str:
        return self.base_url + "/" + str(path or "").lstrip("/")

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ProviderUnavailableError(
                f"ComfyUI rejected the request with HTTP {exc.code}."
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError(
                "Nova could not reach the configured local ComfyUI server."
            ) from exc
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ProviderUnavailableError("ComfyUI returned an oversized response.")
        if not raw.strip():
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailableError("ComfyUI returned invalid JSON.") from exc
        if not isinstance(parsed, dict):
            raise ProviderUnavailableError("ComfyUI returned an unexpected response shape.")
        return parsed

    def health_check(self) -> dict[str, Any]:
        now = time.monotonic()
        with self._lock:
            cached = self._health_cache
        if cached and now - cached[0] < 5.0:
            return dict(cached[1])
        base = {
            "engine_id": self.engine_id,
            "engine_version": COMFYUI_ENGINE_VERSION,
            "enabled": self.enabled,
            "local_only": True,
            "cost_type": self.cost_type,
            "image_workflow_configured": bool(
                self.image_workflow_path and self.image_workflow_path.is_file()
            ),
            "video_workflow_configured": bool(
                self.video_workflow_path and self.video_workflow_path.is_file()
            ),
            "job_store_enabled": self.job_store_path is not None,
            "job_store_status": "error" if self._job_store_error else "ready",
            "tracked_jobs": len(self._jobs),
        }
        if not self.enabled:
            result = {**base, "ok": False, "status": "disabled"}
        elif self._configuration_error:
            result = {
                **base,
                "ok": False,
                "status": "configuration_error",
                "error": self._configuration_error,
            }
        else:
            try:
                self._request("GET", "/system_stats")
                result = {**base, "ok": True, "status": "ready", "api_reachable": True}
            except ProviderUnavailableError:
                result = {
                    **base,
                    "ok": False,
                    "status": "unavailable",
                    "api_reachable": False,
                }
        with self._lock:
            self._health_cache = (now, dict(result))
        return result

    def capabilities(self) -> dict[str, Any]:
        health = self.health_check()
        return {
            "engine_id": self.engine_id,
            "available": bool(health.get("ok")),
            "text_to_image": bool(health.get("ok") and health.get("image_workflow_configured")),
            "text_to_video": bool(health.get("ok") and health.get("video_workflow_configured")),
            "image_edit": False,
            "upscale": False,
            "image_to_video": False,
            "async_jobs": True,
            "job_cancellation": True,
            "local_only": True,
            "cost_type": "free",
            "no_model_downloads": True,
        }

    def _load_workflow(self, operation: str) -> dict[str, Any]:
        path = self.image_workflow_path if operation == "text_to_image" else self.video_workflow_path
        if path is None:
            raise UnsupportedFeatureError(
                f"ComfyUI {operation.replace('_', ' ')} requires an API-format workflow path."
            )
        if not path.is_file():
            raise ProviderUnavailableError(f"Configured ComfyUI workflow is missing: {path.name}")
        if path.stat().st_size > _MAX_WORKFLOW_BYTES:
            raise InvalidRequestError("ComfyUI workflow exceeds the 4 MB safety limit.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidRequestError("Configured ComfyUI workflow is not valid JSON.") from exc
        if isinstance(payload, dict) and isinstance(payload.get("prompt"), dict):
            payload = payload["prompt"]
        if not isinstance(payload, dict) or not payload:
            raise InvalidRequestError("ComfyUI API workflow must be a non-empty JSON object.")
        if not _contains_token(payload, "{{NOVA_PROMPT}}"):
            raise InvalidRequestError(
                "ComfyUI workflow must contain the {{NOVA_PROMPT}} token."
            )
        return payload

    def _queue(self, operation: str, prompt: str, **options: Any) -> dict[str, Any]:
        health = self.health_check()
        if not health.get("ok"):
            raise ProviderUnavailableError(
                "Local ComfyUI is not ready. Start ComfyUI and check Nova engine health."
            )
        clean_prompt = " ".join(str(prompt or "").split()).strip()
        if not clean_prompt:
            raise InvalidRequestError("A non-empty generation prompt is required.", param="prompt")
        if len(clean_prompt) > 8000:
            raise InvalidRequestError("Generation prompt exceeds 8000 characters.", param="prompt")
        negative = " ".join(str(options.get("negative_prompt") or "").split()).strip()[:4000]
        replacements = {
            "{{NOVA_PROMPT}}": clean_prompt,
            "{{NOVA_NEGATIVE_PROMPT}}": negative,
            "{{NOVA_SEED}}": _bounded_int(
                options.get("seed"),
                secrets.randbelow(2**63 - 1),
                0,
                2**63 - 1,
            ),
            "{{NOVA_WIDTH}}": _bounded_int(options.get("width"), 1024, 64, 4096),
            "{{NOVA_HEIGHT}}": _bounded_int(options.get("height"), 1024, 64, 4096),
            "{{NOVA_STEPS}}": _bounded_int(options.get("steps"), 24, 1, 200),
            "{{NOVA_FRAMES}}": _bounded_int(options.get("frames"), 49, 1, 4096),
            "{{NOVA_FPS}}": _bounded_int(options.get("fps"), 8, 1, 120),
        }
        workflow = _replace_tokens(self._load_workflow(operation), replacements)
        response = self._request(
            "POST",
            "/prompt",
            {"prompt": workflow, "client_id": self.client_id},
        )
        job_id = str(response.get("prompt_id") or "").strip()
        if not job_id:
            details = response.get("error")
            message = "ComfyUI did not return a prompt ID."
            if isinstance(details, dict):
                message += " Check the configured workflow nodes and model names."
            raise ProviderUnavailableError(message)
        record = {
            "job_id": job_id,
            "operation": operation,
            "client_id": str(options.get("owner_id") or "local")[:160],
            "status": "queued",
            "created_at": _now(),
            "updated_at": _now(),
        }
        self._remember_job(record)
        return {
            "object": "nova.media_job",
            "job_id": job_id,
            "engine_id": self.engine_id,
            "operation": operation,
            "status": "queued",
            "created_at": record["created_at"],
            "poll_path": f"/nova/v1/jobs/{job_id}",
            "estimated_cost": 0.0,
            "cost_type": "free",
            "local": True,
        }

    def generate_image(self, prompt: str, **options: Any) -> dict[str, Any]:
        return self._queue("text_to_image", prompt, **options)

    def edit_image(self, image: Any, prompt: str, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError(
            "ComfyUI image editing is not enabled until a permission-safe input upload adapter is configured."
        )

    def upscale_image(self, image: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError(
            "ComfyUI upscaling is not enabled until a permission-safe input upload adapter is configured."
        )

    def text_to_video(self, prompt: str, **options: Any) -> dict[str, Any]:
        return self._queue("text_to_video", prompt, **options)

    def image_to_video(self, image: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError(
            "ComfyUI image-to-video awaits a permission-safe input upload adapter."
        )

    def extend_video(self, video: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError("ComfyUI video extension is not implemented.")

    def interpolate_video(self, video: Any, **options: Any) -> dict[str, Any]:
        raise UnsupportedFeatureError("ComfyUI video interpolation is not implemented.")

    @staticmethod
    def _queue_contains(queue: Any, job_id: str) -> bool:
        if not isinstance(queue, list):
            return False
        for item in queue:
            if isinstance(item, (list, tuple)) and len(item) > 1 and str(item[1]) == job_id:
                return True
        return False

    def _job_record(self, job_id: str, owner_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            record = dict(self._jobs.get(job_id) or {})
        if not record:
            raise InvalidRequestError("Unknown Nova ComfyUI job ID.", param="job_id")
        if owner_id is not None and record.get("client_id") != str(owner_id)[:160]:
            raise PermissionDeniedError("This client does not own the requested ComfyUI job.")
        return record

    def _outputs(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for node_id, node_output in (entry.get("outputs") or {}).items():
            if not isinstance(node_output, dict):
                continue
            for media_key in ("images", "gifs", "audio"):
                for item in node_output.get(media_key) or []:
                    if not isinstance(item, dict):
                        continue
                    filename = str(item.get("filename") or "")
                    subfolder = str(item.get("subfolder") or "")
                    media_type = str(item.get("type") or "output")
                    if not filename or Path(filename).name != filename or ".." in Path(subfolder).parts:
                        continue
                    params = urlencode(
                        {
                            "filename": filename,
                            "subfolder": subfolder,
                            "type": media_type,
                        }
                    )
                    output.append(
                        {
                            "node_id": str(node_id)[:80],
                            "media_kind": media_key,
                            "filename": filename,
                            "subfolder": subfolder,
                            "type": media_type,
                            "_view_url": self._url("/view?" + params),
                        }
                    )
        return output[:64]

    def job_status(self, job_id: str, *, owner_id: str | None = None) -> dict[str, Any]:
        record = self._job_record(str(job_id), owner_id)
        history = self._request("GET", "/history/" + quote(str(job_id), safe=""))
        entry = history.get(str(job_id))
        status = str(record.get("status") or "queued")
        outputs: list[dict[str, Any]] = []
        error: str | None = None
        if isinstance(entry, dict):
            outputs = self._outputs(entry)
            details = entry.get("status") if isinstance(entry.get("status"), dict) else {}
            completed = bool(details.get("completed")) or bool(outputs)
            status = "completed" if completed else "failed"
            if not completed:
                error = "ComfyUI completed the job without a usable output."
        else:
            queue = self._request("GET", "/queue")
            if self._queue_contains(queue.get("queue_running"), str(job_id)):
                status = "running"
            elif self._queue_contains(queue.get("queue_pending"), str(job_id)):
                status = "queued"
            elif status not in {"cancelled", "completed", "failed"}:
                status = "unknown"
        if status != record.get("status"):
            record["status"] = status
            record["updated_at"] = _now()
            self._remember_job(record)
        safe_outputs = [
            {
                key: value
                for key, value in item.items()
                if not key.startswith("_")
            }
            | {
                "output_index": index,
                "download_path": f"/nova/v1/jobs/{job_id}/outputs/{index}",
            }
            for index, item in enumerate(outputs)
        ]
        return {
            "object": "nova.media_job",
            "job_id": str(job_id),
            "engine_id": self.engine_id,
            "operation": record.get("operation"),
            "status": status,
            "outputs": safe_outputs,
            "error": error,
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "local": True,
            "estimated_cost": 0.0,
        }

    def list_jobs(
        self,
        *,
        owner_id: str,
        limit: int = 25,
    ) -> dict[str, Any]:
        """List bounded, content-free job metadata owned by one Nova client."""
        safe_owner = str(owner_id or "")[:160]
        safe_limit = _bounded_int(limit, 25, 1, 100)
        with self._lock:
            records = [
                dict(record)
                for record in reversed(list(self._jobs.values()))
                if record.get("client_id") == safe_owner
            ][:safe_limit]
        return {
            "object": "list",
            "engine_id": self.engine_id,
            "data": [
                {
                    "object": "nova.media_job",
                    "job_id": record.get("job_id"),
                    "operation": record.get("operation"),
                    "status": record.get("status"),
                    "created_at": record.get("created_at"),
                    "updated_at": record.get("updated_at"),
                    "poll_path": f"/nova/v1/jobs/{record.get('job_id')}",
                    "local": True,
                    "estimated_cost": 0.0,
                }
                for record in records
            ],
            "privacy": {
                "prompt_content_returned": False,
                "workflow_content_returned": False,
                "other_clients_jobs_returned": False,
            },
        }

    def open_job_output(
        self,
        job_id: str,
        output_index: int,
        *,
        owner_id: str | None = None,
    ) -> dict[str, Any]:
        """Open one owned completed output for bounded streaming through Nova."""
        self._job_record(str(job_id), owner_id)
        history = self._request("GET", "/history/" + quote(str(job_id), safe=""))
        entry = history.get(str(job_id))
        if not isinstance(entry, dict):
            raise InvalidRequestError("The ComfyUI job has no completed outputs yet.")
        outputs = self._outputs(entry)
        if output_index < 0 or output_index >= len(outputs):
            raise InvalidRequestError("ComfyUI output index is out of range.", param="output_index")
        descriptor = outputs[output_index]
        request = Request(
            str(descriptor["_view_url"]),
            headers={"Accept": "image/*,video/*,audio/*,application/octet-stream"},
            method="GET",
        )
        try:
            response = urlopen(request, timeout=self.timeout_seconds)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ProviderUnavailableError("Nova could not retrieve the ComfyUI output.") from exc
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if not content_type.startswith(("image/", "video/", "audio/")):
            content_type = "application/octet-stream"
        try:
            content_length = int(response.headers.get("Content-Length") or 0)
        except (TypeError, ValueError):
            content_length = 0
        if content_length > _MAX_OUTPUT_BYTES:
            response.close()
            raise InvalidRequestError("ComfyUI output exceeds Nova's 1 GB streaming limit.")
        return {
            "response": response,
            "content_type": content_type,
            "content_length": content_length,
            "filename": descriptor["filename"],
            "max_bytes": _MAX_OUTPUT_BYTES,
        }

    def cancel_job(self, job_id: str, *, owner_id: str | None = None) -> bool:
        record = self._job_record(str(job_id), owner_id)
        status = self.job_status(str(job_id), owner_id=owner_id).get("status")
        if status in {"completed", "failed", "cancelled"}:
            return False
        if status == "queued":
            self._request("POST", "/queue", {"delete": [str(job_id)]})
        elif status == "running":
            self._request("POST", "/interrupt", {})
        else:
            return False
        record["status"] = "cancelled"
        record["updated_at"] = _now()
        self._remember_job(record)
        return True

    def _load_jobs(self) -> None:
        path = self.job_store_path
        if path is None or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != COMFYUI_JOB_SCHEMA_VERSION:
                return
            records = payload.get("jobs")
            if not isinstance(records, list):
                return
            with self._lock:
                self._jobs = {
                    str(item.get("job_id")): dict(item)
                    for item in records[-256:]
                    if isinstance(item, dict) and item.get("job_id") and item.get("client_id")
                }
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._job_store_error = "invalid_job_store"
            return

    def _remember_job(self, record: dict[str, Any]) -> None:
        with self._job_store_lock:
            with self._lock:
                self._jobs[str(record["job_id"])] = dict(record)
                if len(self._jobs) > 256:
                    oldest = next(iter(self._jobs))
                    self._jobs.pop(oldest, None)
                payload = {
                    "schema_version": COMFYUI_JOB_SCHEMA_VERSION,
                    "privacy": {
                        "prompt_content_stored": False,
                        "workflow_content_stored": False,
                        "output_file_content_stored": False,
                    },
                    "jobs": list(self._jobs.values()),
                }
            path = self.job_store_path
            if path is None:
                return
            temporary = path.with_suffix(path.suffix + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, path)
                self._job_store_error = ""
            except OSError:
                self._job_store_error = "job_store_write_failed"
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass
            finally:
                with self._lock:
                    self._health_cache = None
