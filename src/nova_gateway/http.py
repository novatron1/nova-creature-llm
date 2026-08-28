"""Standard-library HTTP controller for OpenAI and Nova-native routes."""

from __future__ import annotations

from itertools import chain
import ipaddress
import json
import time
from typing import Any, Iterable
from urllib.parse import parse_qs

from nova_evaluation_policy import RESERVED_EVALUATION_METADATA_FIELDS
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest, ProtocolValidationError, new_id

from .adapters import (
    nova_to_openai_chat,
    nova_to_openai_response,
    openai_chat_stream_chunks,
    openai_chat_to_nova,
    openai_response_to_nova,
)
from .auth import AuthContext, LOCAL_SAFE_SCOPES, NovaAuthenticator
from .config import GatewayConfig
from .core import NovaGatewayCore
from .errors import InvalidRequestError, NovaGatewayError, PermissionDeniedError, RateLimitError
from nova_proxy_identity import trusted_tailscale_client_key
from nova_runtime.verification_playwright import verify_playwright_page
from .video_lite import VIDEO_LITE_MOTIONS


OPENAI_GET_PATHS = {"/v1/models", "/health"}
NOVA_GET_PATHS = {
    "/nova/v1/capabilities", "/nova/v1/providers", "/nova/v1/models", "/nova/v1/tools",
    "/nova/v1/health", "/nova/v1/world-model", "/nova/v1/dream-lab", "/nova/v1/engines",
    "/nova/v1/runtime/contract",
    "/nova/v1/media/access", "/nova/v1/jobs", "/nova/v1/conversations",
}
POST_PATHS = {
    "/v1/chat/completions",
    "/v1/responses",
    "/v1/embeddings",
    "/nova/v1/chat",
    "/nova/v1/conversations",
    "/nova/v1/images/generations",
    "/nova/v1/videos/generations",
    "/nova/v1/engines/comfyui-local/launch",
    "/nova/v1/runtime/verification/playwright",
}
PAIRED_DEVICE_OPTIONAL_SCOPES = frozenset({"image.generate", "video.generate"})
DESKTOP_BOOLEAN_CONTEXT_KEYS = frozenset(
    {
        "adapter_only_mode",
        "trained_adapter_only",
        "trained_adapter_only_mode",
        "use_lora_runtime",
        "dolphin_adapter_only",
        "dolphin_lora_only",
        "allow_slow_dolphin_cpu",
        "allow_slow_adapter_cpu",
        "conversation_summary_write_allowed",
    }
)
DESKTOP_STRING_CONTEXT_KEYS = frozenset(
    {
        "lora_adapter_id",
        "lora_adapter_path",
        "lora_base_model",
        "nova_model_mode",
    }
)


class NovaGatewayHttpController:
    """Translate external HTTP requests without embedding provider vocabulary in Nova Core."""

    def __init__(self, core: NovaGatewayCore, authenticator: NovaAuthenticator, config: GatewayConfig):
        self.core = core
        self.authenticator = authenticator
        self.config = config

    @staticmethod
    def _parse_range_header(value: str | None, length: int) -> tuple[int, int] | None:
        """Parse one RFC 7233 byte range; multiple ranges are intentionally refused."""
        if not value or int(length) <= 0:
            return None
        raw = str(value).strip()
        if not raw.lower().startswith("bytes="):
            return None
        spec = raw[6:].strip()
        if not spec or "," in spec:
            return None
        start_text, separator, end_text = spec.partition("-")
        if not separator:
            return None
        try:
            size = int(length)
            if not start_text:
                suffix = int(end_text)
                if suffix <= 0:
                    return None
                return (max(0, size - suffix), size - 1)
            start = int(start_text)
            if start < 0 or start >= size:
                return None
            end = size - 1 if not end_text else min(int(end_text), size - 1)
            if end < start:
                return None
            return (start, end)
        except (TypeError, ValueError):
            return None

    def recognizes(self, path: str) -> bool:
        return (
            path in OPENAI_GET_PATHS | NOVA_GET_PATHS | POST_PATHS
            or path.startswith("/nova/v1/cancel/")
            or path.startswith("/nova/v1/jobs/")
            or path.startswith("/nova/v1/conversations/")
        )

    def _client_ip(self, handler: Any) -> str:
        direct = str((getattr(handler, "client_address", None) or ("",))[0])
        headers = getattr(handler, "headers", {})
        tailscale = trusted_tailscale_client_key(
            handler,
            enabled=self.config.trust_tailscale_serve,
        )
        if tailscale:
            return tailscale
        # Quick tunnels connect to Nova from loopback. Cloudflare's own client
        # header must win in that narrow case or an internet request would be
        # mistaken for trusted localhost. A non-loopback direct peer cannot
        # activate this shortcut by spoofing the header.
        cloudflare = str(headers.get("CF-Connecting-IP") or "").strip()
        if self.authenticator.is_local_address(direct) and cloudflare and headers.get("CF-Ray"):
            try:
                return str(ipaddress.ip_address(cloudflare.split("%", 1)[0]))
            except ValueError:
                pass
        if self.config.trust_proxy_headers:
            forwarded = str(headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
            if forwarded:
                try:
                    return str(ipaddress.ip_address(forwarded.split("%", 1)[0]))
                except ValueError:
                    pass
        return direct

    def client_is_local(self, handler: Any) -> bool:
        return self.authenticator.is_local_address(self._client_ip(handler))

    def _authorize(self, handler: Any, required_scope: str | None) -> AuthContext:
        paired_device = getattr(handler, "_paired_device", None)
        if isinstance(paired_device, dict):
            paired_device_local = bool(getattr(handler, "_paired_device_local", False))
            # A one-time Foundation pairing grants the safe base scopes plus
            # optional owner-approved device scopes stored by Foundation.
            # Generic remote API keys remain controlled separately.
            client_id = "paired-device:" + str(paired_device.get("device_id") or paired_device.get("id") or "unknown")
            optional_scopes = paired_device.get("scopes")
            if not isinstance(optional_scopes, (list, tuple, set, frozenset)):
                optional_scopes = ()
            paired_scopes = frozenset(
                set(LOCAL_SAFE_SCOPES)
                | {
                    str(scope)
                    for scope in optional_scopes
                    if str(scope) in PAIRED_DEVICE_OPTIONAL_SCOPES
                }
            )
            if required_scope and required_scope not in paired_scopes:
                raise PermissionDeniedError(f"Client {client_id!r} lacks required scope {required_scope!r}.")
            if self.config.rate_limit_enabled and not self.authenticator.rate_limiter.check(client_id):
                raise RateLimitError()
            return AuthContext(client_id, paired_scopes, paired_device_local, True)
        return self.authenticator.authorize(
            self._client_ip(handler), handler.headers.get("Authorization"), required_scope,
        )

    def _read_json(self, handler: Any) -> dict[str, Any]:
        try:
            length = handler._content_length(self.config.max_request_size_bytes)
        except AttributeError:
            raw_length = handler.headers.get("Content-Length")
            if raw_length is None:
                raise InvalidRequestError("Content-Length is required.")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise InvalidRequestError("Content-Length must be an integer.") from exc
            if length > self.config.max_request_size_bytes:
                raise NovaGatewayError("Request body is too large.", "invalid_request_error", "request_too_large", 413)
        if not length:
            return {}
        try:
            payload = json.loads(handler.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InvalidRequestError("Invalid JSON request body.") from exc
        if not isinstance(payload, dict):
            raise InvalidRequestError("JSON request body must be an object.")
        return payload

    def _send_error(self, handler: Any, error: Exception) -> None:
        if isinstance(error, NovaGatewayError):
            gateway_error = error
        elif isinstance(error, ProtocolValidationError):
            gateway_error = InvalidRequestError(str(error))
        elif error.__class__.__name__ == "RequestBodyTooLarge":
            gateway_error = NovaGatewayError(str(error), "invalid_request_error", "request_too_large", 413)
        elif error.__class__.__name__ == "RequestBodyError":
            gateway_error = InvalidRequestError(str(error))
        else:
            gateway_error = NovaGatewayError("Nova hit an internal gateway error.")
        handler._send_json(gateway_error.to_openai(), status=gateway_error.status)

    def handle_get(self, handler: Any, parsed: Any) -> bool:
        path = parsed.path
        media_job_path = path.startswith("/nova/v1/jobs/") and not path.endswith("/cancel")
        if not self.config.enabled or (
            path not in OPENAI_GET_PATHS | NOVA_GET_PATHS and not media_job_path
        ):
            return False
        try:
            if path == "/v1/models":
                self._authorize(handler, "chat.generate")
                now = int(time.time())
                data = [
                    {
                        "id": item["id"], "object": "model", "created": now, "owned_by": "nova",
                        "nova_capabilities": {
                            key: value
                            for key, value in item["capabilities"].items()
                            if key not in {"metadata"}
                        },
                    }
                    for item in self.core.model_aliases()
                ]
                handler._send_json({"object": "list", "data": data})
                return True
            if path == "/health":
                self._authorize(handler, None)
                health = self.core.health(detailed=False)
                handler._send_json(health, status=200 if health.get("ok") else 503)
                return True
            if path == "/nova/v1/capabilities":
                self._authorize(handler, "chat.generate")
                handler._send_json(self.core.capabilities())
                return True
            if path == "/nova/v1/providers":
                self._authorize(handler, "admin.models")
                handler._send_json({"object": "list", "data": self.core.providers.list_providers()})
                return True
            if path == "/nova/v1/models":
                self._authorize(handler, "admin.models")
                handler._send_json({"object": "list", "data": self.core.model_aliases()})
                return True
            if path == "/nova/v1/tools":
                self._authorize(handler, "tools.list")
                handler._send_json({"object": "list", "data": self.core.tools.list()})
                return True
            if path == "/nova/v1/health":
                self._authorize(handler, "chat.generate")
                health = self.core.health(detailed=True)
                handler._send_json(health, status=200 if health.get("ok") else 503)
                return True
            if path == "/nova/v1/world-model":
                auth = self._authorize(handler, "chat.generate")
                query = parse_qs(str(getattr(parsed, "query", "") or ""))
                conversation_id = str((query.get("conversation_id") or [""])[0]).strip()[:160] or None
                handler._send_json(self.core.world_model.view(auth.client_id, conversation_id))
                return True
            if path == "/nova/v1/dream-lab":
                auth = self._authorize(handler, "chat.generate")
                query = parse_qs(str(getattr(parsed, "query", "") or ""))
                conversation_id = str((query.get("conversation_id") or [""])[0]).strip()[:160] or None
                handler._send_json(self.core.dream_lab.view(auth.client_id, conversation_id))
                return True
            if path == "/nova/v1/engines":
                self._authorize(handler, "tools.list")
                handler._send_json({"object": "list", "data": self.core.engines.list()})
                return True
            if path == "/nova/v1/runtime/contract":
                self._authorize(handler, "tools.list")
                handler._send_json(self.core.runtime_contract())
                return True
            if path == "/nova/v1/media/access":
                auth = self._authorize(handler, "tools.list")
                handler._send_json(
                    {
                        "object": "nova.media_access",
                        "client_id": auth.client_id,
                        "image_generate": "image.generate" in auth.scopes,
                        "video_generate": "video.generate" in auth.scopes,
                        "local_client": auth.local,
                        "authenticated": auth.authenticated,
                    }
                )
                return True
            if path == "/nova/v1/conversations" or path.startswith("/nova/v1/conversations/"):
                auth = self._authorize(handler, "chat.generate")
                suffix = path[len("/nova/v1/conversations") :].strip("/")
                conversation_id = suffix[:160] if suffix and "/" not in suffix else None
                if suffix and conversation_id is None:
                    raise InvalidRequestError("A valid conversation ID is required.", param="conversation_id")
                if conversation_id:
                    record = self.core.get_conversation(
                        client_id=auth.client_id,
                        conversation_id=conversation_id,
                    )
                    if record is None:
                        handler._send_json({"error": {"message": "Conversation not found.", "type": "not_found"}}, status=404)
                    else:
                        handler._send_json({"object": "nova.conversation", "data": record})
                    return True
                query = parse_qs(str(getattr(parsed, "query", "") or ""))
                raw_limit = (query.get("limit") or ["100"])[0]
                try:
                    limit = int(raw_limit)
                except (TypeError, ValueError):
                    limit = 100
                include_archived = str((query.get("include_archived") or [""])[0]).lower() in {"1", "true", "yes"}
                handler._send_json(self.core.list_conversations(
                    client_id=auth.client_id,
                    query=(query.get("query") or [""])[0],
                    include_archived=include_archived,
                    limit=limit,
                ))
                return True
            if path == "/nova/v1/jobs":
                auth = self._authorize(handler, "tools.list")
                query = parse_qs(str(getattr(parsed, "query", "") or ""))
                try:
                    limit = int((query.get("limit") or ["25"])[0])
                except (TypeError, ValueError):
                    limit = 25
                handler._send_json(
                    self.core.list_media_jobs(
                        client_id=auth.client_id,
                        limit=max(1, min(limit, 100)),
                    )
                )
                return True
            if media_job_path and "/outputs/" in path:
                auth = self._authorize(handler, None)
                suffix = path[len("/nova/v1/jobs/") :]
                job_id, marker, raw_index = suffix.partition("/outputs/")
                if (
                    not marker
                    or not job_id
                    or "/" in job_id
                    or not raw_index.isdigit()
                ):
                    raise InvalidRequestError("A valid media output path is required.")
                opened = self.core.open_media_job_output(
                    job_id[:200],
                    int(raw_index),
                    client_id=auth.client_id,
                )
                upstream = opened["response"]
                try:
                    total_length = int(opened.get("content_length") or 0)
                    range_header = handler.headers.get("Range")
                    selected_range = self._parse_range_header(range_header, total_length)
                    if range_header and selected_range is None:
                        handler.send_response(416)
                        handler.send_header("Content-Range", f"bytes */{total_length}")
                        handler.send_header("Content-Length", "0")
                        handler._send_cors_headers()
                        handler.end_headers()
                        return True
                    status = 206 if selected_range else 200
                    start, end = selected_range if selected_range else (0, max(0, total_length - 1))
                    content_length = (end - start + 1) if total_length else 0
                    handler.send_response(status)
                    handler.send_header("Content-Type", opened["content_type"])
                    if total_length:
                        handler.send_header("Content-Length", str(content_length))
                    if selected_range:
                        handler.send_header("Content-Range", f"bytes {start}-{end}/{total_length}")
                    handler.send_header("Accept-Ranges", "bytes")
                    if opened.get("sha256"):
                        handler.send_header("X-Nova-Output-SHA256", str(opened["sha256"]))
                        handler.send_header("ETag", '"' + str(opened["sha256"]) + '"')
                    handler.send_header("Content-Disposition", "inline")
                    handler._send_cors_headers()
                    handler.end_headers()
                    if selected_range and hasattr(upstream, "seek"):
                        upstream.seek(start)
                    streamed = 0
                    remaining = content_length
                    while remaining > 0 or not total_length:
                        chunk = upstream.read(min(64 * 1024, remaining) if remaining > 0 else 64 * 1024)
                        if not chunk:
                            break
                        streamed += len(chunk)
                        remaining -= len(chunk)
                        if streamed > int(opened["max_bytes"]):
                            break
                        if not handler._write_bytes(chunk):
                            break
                finally:
                    upstream.close()
                return True
            if media_job_path:
                auth = self._authorize(handler, None)
                job_id = path[len("/nova/v1/jobs/") :].strip()
                if not job_id or "/" in job_id:
                    raise InvalidRequestError("A valid media job ID is required.", param="job_id")
                handler._send_json(
                    self.core.media_job_status(job_id[:200], client_id=auth.client_id)
                )
                return True
        except Exception as exc:
            self._send_error(handler, exc)
            return True
        return False

    def handle_post(self, handler: Any, parsed: Any) -> bool:
        path = parsed.path
        media_cancel_path = path.startswith("/nova/v1/jobs/") and path.endswith("/cancel")
        media_resume_path = path.startswith("/nova/v1/jobs/") and path.endswith("/resume")
        if not self.config.enabled or (
            path not in POST_PATHS
            and not path.startswith("/nova/v1/cancel/")
            and not media_cancel_path
            and not media_resume_path
            and not path.startswith("/nova/v1/conversations/")
        ):
            return False
        try:
            if media_cancel_path:
                auth = self._authorize(handler, None)
                job_id = path[len("/nova/v1/jobs/") : -len("/cancel")].strip("/")
                if not job_id or "/" in job_id:
                    raise InvalidRequestError("A valid media job ID is required.", param="job_id")
                handler._send_json(
                    {
                        "ok": self.core.cancel_media_job(
                            job_id[:200],
                            client_id=auth.client_id,
                        ),
                        "job_id": job_id[:200],
                    }
                )
                return True
            if media_resume_path:
                auth = self._authorize(handler, None)
                job_id = path[len("/nova/v1/jobs/") : -len("/resume")].strip("/")
                if not job_id or "/" in job_id:
                    raise InvalidRequestError("A valid media job ID is required.", param="job_id")
                handler._send_json(
                    self.core.resume_media_job(job_id[:200], client_id=auth.client_id),
                    status=202,
                )
                return True
            if path.startswith("/nova/v1/cancel/"):
                auth = self._authorize(handler, "chat.generate")
                request_id = path.rsplit("/", 1)[-1].strip()
                if not request_id:
                    raise InvalidRequestError("A request ID is required.")
                handler._send_json({
                    "ok": self.core.cancel(request_id, client_id=auth.client_id),
                    "request_id": request_id,
                })
                return True

            if path == "/nova/v1/conversations" or path.startswith("/nova/v1/conversations/"):
                auth = self._authorize(handler, "chat.generate")
                suffix = path[len("/nova/v1/conversations") :].strip("/")
                action = "save"
                conversation_id = ""
                if suffix:
                    parts = suffix.split("/")
                    if len(parts) != 2 or parts[1] not in {"archive", "restore", "delete"}:
                        raise InvalidRequestError("Conversation action must be archive, restore, or delete.")
                    conversation_id, action = parts[0][:160], parts[1]
                body = self._read_json(handler)
                if action == "save":
                    conversation_id = str(body.get("conversation_id") or "").strip()[:160]
                    if not conversation_id:
                        raise InvalidRequestError("conversation_id is required.", param="conversation_id")
                    title = body.get("title")
                    if title is not None and not isinstance(title, str):
                        raise InvalidRequestError("title must be a string.", param="title")
                    messages = body.get("messages", [])
                    if not isinstance(messages, list):
                        raise InvalidRequestError("messages must be an array.", param="messages")
                    record = self.core.save_conversation(
                        client_id=auth.client_id,
                        conversation_id=conversation_id,
                        title=title,
                        messages=messages,
                    )
                    handler._send_json({"object": "nova.conversation", "data": record}, status=201)
                    return True
                if "/" in conversation_id:
                    raise InvalidRequestError("A valid conversation ID is required.", param="conversation_id")
                changed = {
                    "archive": self.core.archive_conversation,
                    "restore": self.core.restore_conversation,
                    "delete": self.core.delete_conversation,
                }[action](client_id=auth.client_id, conversation_id=conversation_id)
                handler._send_json({"ok": changed, "conversation_id": conversation_id, "action": action})
                return True

            if path == "/nova/v1/images/generations":
                auth = self._authorize(handler, "image.generate")
                body = self._media_payload(self._read_json(handler), video=False)
                handler._send_json(self.core.generate_image(body, client_id=auth.client_id), status=202)
                return True
            if path == "/nova/v1/videos/generations":
                auth = self._authorize(handler, "video.generate")
                body = self._media_payload(self._read_json(handler), video=True)
                handler._send_json(self.core.generate_video(body, client_id=auth.client_id), status=202)
                return True
            if path == "/nova/v1/engines/comfyui-local/launch":
                self._authorize(handler, "tools.list")
                result = self.core.launch_comfyui()
                handler._send_json(result, status=202 if result.get("started") or result.get("launching") else 200)
                return True
            if path == "/nova/v1/runtime/verification/playwright":
                self._authorize(handler, "tools.list")
                body = self._read_json(handler)
                url = str(body.get("url") or "").strip()
                if not url:
                    raise InvalidRequestError("url is required.", param="url")
                assertions = body.get("assertions") or []
                if not isinstance(assertions, list):
                    raise InvalidRequestError("assertions must be an array.", param="assertions")
                timeout_seconds = int(body.get("timeout_seconds") or 30)
                output_dir = body.get("output_dir")
                result = verify_playwright_page(
                    url,
                    [dict(item) for item in assertions if isinstance(item, dict)],
                    timeout_seconds=timeout_seconds,
                    output_dir=output_dir,
                )
                handler._send_json(result.to_dict(), status=200 if result.passed else 422)
                return True

            auth = self._authorize(handler, "chat.generate")
            body = self._read_json(handler)
            if path == "/v1/chat/completions":
                request = openai_chat_to_nova(body, auth)
                if request.generation_options.stream:
                    self._require_stream_scope(auth)
                    self._stream_chat(handler, request)
                else:
                    handler._send_json(nova_to_openai_chat(self.core.generate(request)))
                return True
            if path == "/v1/responses":
                request = openai_response_to_nova(body, auth)
                if request.generation_options.stream:
                    self._require_stream_scope(auth)
                    self._stream_response(handler, request)
                else:
                    handler._send_json(nova_to_openai_response(self.core.generate(request)))
                return True
            if path == "/v1/embeddings":
                self._handle_embeddings(handler, body)
                return True
            if path == "/nova/v1/chat":
                request = self._native_request(body, auth)
                if request.generation_options.stream:
                    self._require_stream_scope(auth)
                    self._stream_native(handler, request)
                else:
                    handler._send_json(self.core.generate(request).to_dict())
                return True
        except Exception as exc:
            self._send_error(handler, exc)
            return True
        return False

    @staticmethod
    def _media_payload(body: dict[str, Any], *, video: bool) -> dict[str, Any]:
        allowed = {
            "prompt",
            "negative_prompt",
            "seed",
            "width",
            "height",
            "steps",
        }
        if video:
            allowed.update({"frames", "fps", "motion", "engine_id"})
        unknown = set(body) - allowed
        if unknown:
            name = sorted(unknown)[0]
            raise InvalidRequestError(f"Unsupported media-generation field {name!r}.", param=name)
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise InvalidRequestError("A non-empty string prompt is required.", param="prompt")
        if len(prompt.strip()) > 8000:
            raise InvalidRequestError("prompt exceeds 8000 characters.", param="prompt")
        if body.get("negative_prompt") is not None and not isinstance(body["negative_prompt"], str):
            raise InvalidRequestError("negative_prompt must be a string.", param="negative_prompt")
        if len(str(body.get("negative_prompt") or "")) > 4000:
            raise InvalidRequestError(
                "negative_prompt exceeds 4000 characters.",
                param="negative_prompt",
            )
        limits = {
            "seed": (0, 2**63 - 1),
            "width": (64, 4096),
            "height": (64, 4096),
            "steps": (1, 200),
            "frames": (1, 4096),
            "fps": (1, 120),
        }
        for name in ("seed", "width", "height", "steps", "frames", "fps"):
            if name in body and (
                isinstance(body[name], bool) or not isinstance(body[name], int)
            ):
                raise InvalidRequestError(f"{name} must be an integer.", param=name)
            if name in body and not limits[name][0] <= body[name] <= limits[name][1]:
                lower, upper = limits[name]
                raise InvalidRequestError(
                    f"{name} must be between {lower} and {upper}.",
                    param=name,
                )
        if "motion" in body:
            if not isinstance(body["motion"], str):
                raise InvalidRequestError("motion must be a string.", param="motion")
            body["motion"] = body["motion"].strip().lower()
            if body["motion"] not in VIDEO_LITE_MOTIONS:
                raise InvalidRequestError(
                    "motion must be slow_zoom_in, slow_zoom_out, pan_left, or pan_right.",
                    param="motion",
                )
        return dict(body)

    @staticmethod
    def _require_stream_scope(auth: AuthContext) -> None:
        if "chat.stream" not in auth.scopes:
            raise PermissionDeniedError("This client lacks required scope 'chat.stream'.")

    def _native_request(self, body: dict[str, Any], auth: AuthContext) -> NovaRequest:
        evaluation_only: bool | None = None
        evaluation_case_id: str | None = None
        if "evaluation_only" in body:
            if not isinstance(body["evaluation_only"], bool):
                raise InvalidRequestError(
                    "Nova-native field 'evaluation_only' must be a boolean.",
                    param="evaluation_only",
                )
            evaluation_only = body["evaluation_only"]
            if evaluation_only and not auth.local:
                raise PermissionDeniedError(
                    "Nova evaluation-only requests are restricted to trusted local clients."
                )
        if "evaluation_case_id" in body:
            if not isinstance(body["evaluation_case_id"], str):
                raise InvalidRequestError(
                    "Nova-native field 'evaluation_case_id' must be a string.",
                    param="evaluation_case_id",
                )
            evaluation_case_id = body["evaluation_case_id"].strip()
            if not evaluation_case_id or len(evaluation_case_id) > 80:
                raise InvalidRequestError(
                    "Nova-native field 'evaluation_case_id' must be 1 to 80 characters.",
                    param="evaluation_case_id",
                )
            if evaluation_only is not True:
                raise InvalidRequestError(
                    "evaluation_case_id is valid only with evaluation_only=true.",
                    param="evaluation_case_id",
                )
        if body.get("messages") and body.get("generation_options") is not None:
            request = NovaRequest.from_dict(body)
            request.client_id = auth.client_id
            request.metadata["client_scopes"] = sorted(auth.scopes)
            request.metadata.pop("memory_mode", None)
            for field in RESERVED_EVALUATION_METADATA_FIELDS:
                request.metadata.pop(field, None)
            if evaluation_only is not None:
                request.metadata["evaluation_only"] = evaluation_only
            if evaluation_case_id is not None:
                request.metadata["evaluation_case_id"] = evaluation_case_id
            if evaluation_only:
                request.metadata["_nova_evaluation_trusted"] = True
                request.privacy_mode = "local_only"
            return request
        text = str(body.get("text") or body.get("message") or "").strip()
        if not text:
            raise InvalidRequestError("Nova-native chat requires text or messages.", param="text")
        raw_metadata = body.get("metadata")
        if raw_metadata is not None and not isinstance(raw_metadata, dict):
            raise InvalidRequestError("metadata must be an object.", param="metadata")
        metadata = dict(raw_metadata or {})
        metadata["client_scopes"] = sorted(auth.scopes)
        metadata.pop("memory_mode", None)
        for field in RESERVED_EVALUATION_METADATA_FIELDS:
            metadata.pop(field, None)
        if evaluation_only is not None:
            metadata["evaluation_only"] = evaluation_only
        if evaluation_case_id is not None:
            metadata["evaluation_case_id"] = evaluation_case_id
        if evaluation_only:
            metadata["_nova_evaluation_trusted"] = True
        desktop_context: dict[str, Any] = {}
        for key in DESKTOP_BOOLEAN_CONTEXT_KEYS:
            if key in body:
                if not isinstance(body[key], bool):
                    raise InvalidRequestError(f"Nova-native field {key!r} must be a boolean.", param=key)
                desktop_context[key] = body[key]
        for key in DESKTOP_STRING_CONTEXT_KEYS:
            if body.get(key) is not None:
                if not isinstance(body[key], str):
                    raise InvalidRequestError(
                        f"Nova-native field {key!r} must be a string.",
                        param=key,
                    )
                desktop_context[key] = body[key][:500]
        if isinstance(body.get("sensor_snapshot"), dict):
            desktop_context["sensor_snapshot"] = dict(body["sensor_snapshot"])
        if body.get("conversation_summary") is not None:
            raw_summary = body.get("conversation_summary")
            if not isinstance(raw_summary, (dict, str)):
                raise InvalidRequestError(
                    "conversation_summary must be an object or JSON string.",
                    param="conversation_summary",
                )
            try:
                serialized_summary = json.dumps(raw_summary, ensure_ascii=False)
            except (TypeError, ValueError):
                raise InvalidRequestError(
                    "conversation_summary must be JSON serializable.",
                    param="conversation_summary",
                )
            if len(serialized_summary.encode("utf-8")) > 12_000:
                raise InvalidRequestError(
                    "conversation_summary exceeds the 12000-byte limit.",
                    param="conversation_summary",
                )
            desktop_context["conversation_summary"] = raw_summary
        if body.get("conversation_history") is not None:
            raw_history = body.get("conversation_history")
            if not isinstance(raw_history, list):
                raise InvalidRequestError("conversation_history must be an array.", param="conversation_history")
            conversation_history = []
            for index, item in enumerate(raw_history[-8:]):
                if not isinstance(item, dict):
                    raise InvalidRequestError(
                        "Each conversation_history item must be an object.",
                        param=f"conversation_history[{index}]",
                    )
                role = str(item.get("role") or "").strip().lower()
                content = item.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    raise InvalidRequestError(
                        "conversation_history supports text user and assistant turns only.",
                        param=f"conversation_history[{index}]",
                    )
                conversation_history.append({"role": role, "content": content[:4000]})
            desktop_context["conversation_history"] = conversation_history
        if body.get("conversation_summary_history") is not None:
            raw_summary_history = body.get("conversation_summary_history")
            if not isinstance(raw_summary_history, list):
                raise InvalidRequestError(
                    "conversation_summary_history must be an array.",
                    param="conversation_summary_history",
                )
            conversation_summary_history = []
            for index, item in enumerate(raw_summary_history[-8:]):
                if not isinstance(item, dict):
                    raise InvalidRequestError(
                        "Each conversation_summary_history item must be an object.",
                        param=f"conversation_summary_history[{index}]",
                    )
                role = str(item.get("role") or "").strip().lower()
                content = item.get("content")
                if role not in {"user", "assistant"} or not isinstance(content, str):
                    raise InvalidRequestError(
                        "conversation_summary_history supports text user and assistant turns only.",
                        param=f"conversation_summary_history[{index}]",
                    )
                conversation_summary_history.append(
                    {"role": role, "content": content[:4000]}
                )
            desktop_context["conversation_summary_history"] = conversation_summary_history
        if desktop_context:
            metadata["desktop_context"] = desktop_context
        return NovaRequest(
            request_id=str(body.get("request_id") or new_id("req")),
            user_id=str(body.get("user_id") or "anonymous"), client_id=auth.client_id,
            conversation_id=str(body.get("conversation_id") or new_id("conv")),
            session_id=str(body.get("session_id") or new_id("sess")),
            messages=[NovaMessage(role="user", content=text)],
            generation_options=NovaGenerationOptions(
                model=str(body.get("model") or "nova"), stream=bool(body.get("stream", False)),
                temperature=body.get("temperature"), max_tokens=body.get("max_tokens"),
                response_format=body.get("response_format"),
            ),
            privacy_mode=(
                "local_only"
                if evaluation_only
                else str(body.get("privacy_mode") or "local_preferred")
            ),
            metadata=metadata,
            api_source="nova_native", api_version="nova/v1",
        )

    def _handle_embeddings(self, handler: Any, body: dict[str, Any]) -> None:
        value = body.get("input")
        if isinstance(value, str):
            inputs = [value]
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            inputs = value
        else:
            raise InvalidRequestError("Embeddings input must be text or an array of text.", param="input")
        if not inputs:
            raise InvalidRequestError("Embeddings input cannot be empty.", param="input")
        model = str(body.get("model") or "nova")
        vectors, capability = self.core.embed(inputs, model)
        handler._send_json(
            {
                "object": "list", "model": model,
                "data": [{"object": "embedding", "index": index, "embedding": vector} for index, vector in enumerate(vectors)],
                "usage": None,
                "nova_metadata": {"provider": capability.provider_id, "token_usage_available": False},
            }
        )

    def _preflight_events(self, request: NovaRequest):
        iterator = iter(self.core.stream(request))
        try:
            first = next(iterator)
        except StopIteration as exc:
            raise NovaGatewayError("Streaming provider returned no events.", "provider_unavailable", "empty_stream", 503) from exc
        return chain([first], iterator)

    def _begin_sse(self, handler: Any) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-store")
        handler.send_header("X-Accel-Buffering", "no")
        handler._send_cors_headers()
        handler.end_headers()

    @staticmethod
    def _sse_write(handler: Any, payload: dict[str, Any] | str, *, event: str | None = None) -> bool:
        data = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        prefix = f"event: {event}\n" if event else ""
        if not handler._write_bytes((prefix + f"data: {data}\n\n").encode("utf-8")):
            return False
        try:
            handler.wfile.flush()
        except (BrokenPipeError, ConnectionError):
            return False
        return True

    def _stream_chat(self, handler: Any, request: NovaRequest) -> None:
        events = self._preflight_events(request)
        self._begin_sse(handler)
        try:
            for chunk in openai_chat_stream_chunks(request, events):
                if not self._sse_write(handler, chunk):
                    self.core.cancel(request.request_id, client_id=request.client_id)
                    return
            self._sse_write(handler, "[DONE]")
        finally:
            close = getattr(events, "close", None)
            if callable(close):
                close()

    def _stream_native(self, handler: Any, request: NovaRequest) -> None:
        events = self._preflight_events(request)
        self._begin_sse(handler)
        try:
            for event in events:
                if not self._sse_write(handler, event.to_dict(), event=event.event_type):
                    self.core.cancel(request.request_id, client_id=request.client_id)
                    return
            self._sse_write(handler, "[DONE]")
        finally:
            close = getattr(events, "close", None)
            if callable(close):
                close()

    def _stream_response(self, handler: Any, request: NovaRequest) -> None:
        events = self._preflight_events(request)
        self._begin_sse(handler)
        sequence = 0
        response_id = None
        assembled: list[str] = []
        try:
            for item in events:
                response_id = response_id or item.response_id
                if sequence == 0:
                    created = {
                        "type": "response.created", "sequence_number": sequence,
                        "response": {"id": response_id, "object": "response", "status": "in_progress", "model": request.generation_options.model},
                    }
                    if not self._sse_write(handler, created, event="response.created"):
                        self.core.cancel(request.request_id, client_id=request.client_id)
                        return
                    sequence += 1
                if item.delta:
                    assembled.append(item.delta)
                    delta = {
                        "type": "response.output_text.delta", "sequence_number": sequence,
                        "response_id": response_id, "output_index": 0, "content_index": 0, "delta": item.delta,
                    }
                    if not self._sse_write(handler, delta, event="response.output_text.delta"):
                        self.core.cancel(request.request_id, client_id=request.client_id)
                        return
                    sequence += 1
                if item.done:
                    completed = {
                        "type": "response.completed", "sequence_number": sequence,
                        "response": {
                            "id": response_id, "object": "response", "status": "completed", "model": request.generation_options.model,
                            "output_text": "".join(assembled),
                        },
                    }
                    self._sse_write(handler, completed, event="response.completed")
            self._sse_write(handler, "[DONE]")
        finally:
            close = getattr(events, "close", None)
            if callable(close):
                close()
