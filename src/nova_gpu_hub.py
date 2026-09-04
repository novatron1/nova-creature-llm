"""Standalone compute selection and Vast.ai client for Nova GPU Hub."""

from __future__ import annotations

import csv
import io
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

try:
    from .nova_http_security import open_without_redirects, validate_worker_url
except ImportError:  # pragma: no cover - direct src/ import compatibility
    from nova_http_security import open_without_redirects, validate_worker_url


VERIFIED_BACKENDS = frozenset(("local_gpu", "vast_gpu"))
DEFAULT_VERIFICATION_TTL_SECONDS = 900


class ComputeMode:
    AUTO = "auto"
    CPU = "cpu"
    LOCAL_GPU = "local_gpu"
    VAST_GPU = "vast_gpu"
    ALL = frozenset((AUTO, CPU, LOCAL_GPU, VAST_GPU))


class GpuHubError(RuntimeError):
    def __init__(self, code: str, message: str, status: int | None = None):
        self.code, self.status = code, status
        super().__init__(message)


def detect_local_gpu(*, runner: Callable[[list[str]], str] | None = None) -> dict[str, object]:
    runner = runner or _run_nvidia_smi
    base = {"available": False, "usable": False, "gpu_names": [], "memory_mb": 0, "driver": None, "backend": None, "reason": "No compatible GPU detected."}
    try:
        output = runner(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader,nounits"])
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        # CUDA may already be importable in an environment without nvidia-smi.
        try:
            import torch  # type: ignore
            if bool(torch.cuda.is_available()):
                names = [str(torch.cuda.get_device_name(i)) for i in range(torch.cuda.device_count())]
                return {**base, "available": True, "usable": True, "gpu_names": names, "backend": "torch.cuda", "reason": "CUDA GPU detected."}
        except Exception:
            pass
        return {**base, "reason": f"nvidia-smi unavailable: {type(exc).__name__}."}
    names, memories, drivers = [], [], []
    for row in csv.reader(io.StringIO(output or "")):
        if not row or not row[0].strip():
            continue
        names.append(row[0].strip())
        try:
            memories.append(int(float(row[1].strip())))
        except (IndexError, ValueError):
            memories.append(0)
        drivers.append(row[2].strip() if len(row) > 2 else "")
    if not names:
        return {**base, "reason": "nvidia-smi returned no GPUs."}
    return {"available": True, "usable": True, "gpu_names": names, "memory_mb": sum(memories), "driver": drivers[0] if drivers else None, "backend": "nvidia", "reason": "NVIDIA GPU detected."}


def _run_nvidia_smi(args: list[str]) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=15)


class GpuHubStateStore:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)

    def load(self) -> dict[str, object]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("mode") not in ComputeMode.ALL:
                raise ValueError
            return _safe_state(data)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {
                "mode": ComputeMode.AUTO,
                "selected_instance_id": None,
                "endpoint": {},
                "verified": False,
                "verified_backend": None,
                "verified_at": None,
                "updated_at": None,
            }

    def save(self, state: Mapping[str, object]) -> dict[str, object]:
        clean = _safe_state(state)
        clean["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(clean, handle, indent=2)
                handle.write("\n")
            os.replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return clean


def _safe_state(state: Mapping[str, object]) -> dict[str, object]:
    mode = state.get("mode", ComputeMode.AUTO)
    if mode not in ComputeMode.ALL:
        mode = ComputeMode.AUTO
    raw_endpoint = state.get("endpoint")
    raw_endpoint = raw_endpoint if isinstance(raw_endpoint, Mapping) else {}
    endpoint = {}
    for key, value in raw_endpoint.items():
        if key not in {"url", "model", "provider"} or not isinstance(value, (str, int, float, bool, type(None))):
            continue
        if key == "url":
            value = _sanitize_url(str(value))
        elif _looks_secret(key, value):
            continue
        endpoint[key] = value
    selected_instance_id = state.get("selected_instance_id")
    if not isinstance(selected_instance_id, (str, int, type(None))) or _looks_secret(
        "selected_instance_id", selected_instance_id
    ):
        selected_instance_id = None
    verified_at = state.get("verified_at")
    if not isinstance(verified_at, str) or _looks_secret("verified_at", verified_at):
        verified_at = None
    verified_backend = state.get("verified_backend")
    if verified_backend not in VERIFIED_BACKENDS:
        verified_backend = None
    verified = bool(state.get("verified")) and verified_backend is not None and all(
        str(endpoint.get(key) or "").strip() for key in ("url", "model", "provider")
    )
    return {
        "mode": mode,
        "selected_instance_id": selected_instance_id,
        "endpoint": endpoint,
        "verified": verified,
        "verified_backend": verified_backend if verified else None,
        "verified_at": verified_at if verified else None,
        "updated_at": state.get("updated_at"),
    }


def _looks_secret(key: object, value: object) -> bool:
    return bool(re.search(r"key|token|secret|password|credential", str(key), re.I)) or "SECRET" in str(value)


def _sanitize_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if ":" in host:
            host = f"[{host}]"
        if parsed.port:
            host += f":{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return ""


def _is_loopback_url(value: str) -> bool:
    try:
        hostname = urllib.parse.urlsplit(value).hostname
        if not hostname:
            return False
        if hostname.lower() == "localhost":
            return True
        import ipaddress

        return ipaddress.ip_address(hostname).is_loopback
    except (ValueError, TypeError):
        return False


class VastAIClient:
    OFFICIAL_API_BASE_URLS = frozenset(("https://console.vast.ai/api/v0",))

    def __init__(self, api_key: str, base_url: str = "https://console.vast.ai/api/v0", timeout: int = 15):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = min(max(int(timeout), 1), 15)

    @staticmethod
    def _normalized_base_url(value: object) -> str:
        try:
            parsed = urllib.parse.urlsplit(str(value or "").strip())
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                return ""
            hostname = parsed.hostname.lower().rstrip(".")
            if ":" in hostname:
                hostname = f"[{hostname}]"
            if parsed.port:
                hostname += f":{parsed.port}"
            return urllib.parse.urlunsplit(
                (parsed.scheme.lower(), hostname, parsed.path.rstrip("/"), "", "")
            )
        except ValueError:
            return ""

    def _approved_base_url(self) -> str:
        normalized = self._normalized_base_url(self.base_url)
        approved = {
            self._normalized_base_url(value)
            for value in self.OFFICIAL_API_BASE_URLS
        }
        if not normalized or normalized not in approved:
            raise GpuHubError(
                "vast_api_base_not_approved",
                "Vast.ai control requests only use the official API endpoint.",
                400,
            )
        return normalized

    @classmethod
    def _url_within_base(cls, value: object, base_url: str) -> bool:
        try:
            parsed = urllib.parse.urlsplit(str(value or ""))
            base = urllib.parse.urlsplit(base_url)
            if parsed.username or parsed.password:
                return False
            parsed_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            base_port = base.port or (443 if base.scheme == "https" else 80)
        except ValueError:
            return False
        base_path = base.path.rstrip("/")
        return bool(
            parsed.scheme.lower() == base.scheme.lower()
            and str(parsed.hostname or "").lower().rstrip(".")
            == str(base.hostname or "").lower().rstrip(".")
            and parsed_port == base_port
            and (parsed.path == base_path or parsed.path.startswith(base_path + "/"))
        )

    def _request(self, method: str, path: str, payload: object | None = None) -> object:
        if not self.api_key:
            raise GpuHubError("vast_unavailable", "Vast.ai is unavailable because NOVA_VAST_API_KEY is not configured.")
        base_url = self._approved_base_url()
        url = base_url + "/" + path.lstrip("/")
        if not self._url_within_base(url, base_url):
            raise GpuHubError(
                "vast_api_base_not_approved",
                "Vast.ai control requests only use the official API endpoint.",
                400,
            )
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with open_without_redirects(request, timeout=self.timeout) as response:
                final_url = response.geturl() if callable(getattr(response, "geturl", None)) else url
                if not self._url_within_base(final_url, base_url):
                    raise GpuHubError(
                        "vast_api_base_not_approved",
                        "Vast.ai control traffic left the official API endpoint.",
                    )
                data = json.loads(response.read().decode() or "{}")
                return data
        except urllib.error.HTTPError as exc:
            if 300 <= int(exc.code) < 400:
                raise GpuHubError(
                    "vast_redirect_rejected",
                    "Vast.ai control API redirects are not allowed.",
                    exc.code,
                ) from None
            raise GpuHubError("vast_http_error", f"Vast.ai request failed ({exc.code}).", exc.code) from None
        except GpuHubError:
            raise
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GpuHubError("vast_request_failed", _redact(str(exc), self.api_key)) from None

    def list_instances(self) -> list[dict[str, object]]:
        return _list_result(self._request("GET", "instances/"))

    def show_instance(self, instance_id: str) -> dict[str, object]:
        return _dict_result(self._request("GET", f"instances/{urllib.parse.quote(str(instance_id), safe='')}/"))

    def search_offers(self, filters: Mapping[str, object] | None) -> list[dict[str, object]]:
        result = self._request("POST", "bundles/", dict(filters or {}))
        return _list_result(result)

    def create_instance(self, offer_id: object, payload: Mapping[str, object], *, confirmed: bool = False) -> dict[str, object]:
        if not confirmed:
            raise GpuHubError("confirmation_required", "Starting a paid Vast.ai instance requires confirmation.")
        quoted_offer_id = urllib.parse.quote(str(offer_id), safe="")
        return _dict_result(self._request("PUT", f"asks/{quoted_offer_id}/", dict(payload)))

    def set_instance_state(self, instance_id: str, state: str, *, confirmed: bool = False) -> dict[str, object]:
        if not confirmed:
            raise GpuHubError("confirmation_required", "Changing a paid Vast.ai instance requires confirmation.")
        return _dict_result(self._request("PUT", f"instances/{urllib.parse.quote(str(instance_id), safe='')}/", {"state": state}))

    def destroy_instance(self, instance_id: str, *, confirmed: bool = False) -> dict[str, object]:
        if not confirmed:
            raise GpuHubError("confirmation_required", "Destroying a paid Vast.ai instance requires confirmation.")
        return _dict_result(self._request("DELETE", f"instances/{urllib.parse.quote(str(instance_id), safe='')}/"))


def _list_result(value: object) -> list[dict[str, object]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("instances", "offers", "asks", "data", "results"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


def _dict_result(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {"data": value}


def _redact(message: str, secret: str) -> str:
    return message.replace(secret, "[redacted]") if secret else message


class GpuHubController:
    def __init__(self, root: str | os.PathLike[str], env: Mapping[str, str] | None = None):
        self.root = Path(root)
        self.env = dict(os.environ if env is None else env)
        self.store = GpuHubStateStore(self.root / "data" / "nova_gpu_hub_state.json")

    def _verification_ttl_seconds(self) -> int:
        try:
            requested = int(
                self.env.get(
                    "NOVA_GPU_HUB_VERIFICATION_TTL_SECONDS",
                    DEFAULT_VERIFICATION_TTL_SECONDS,
                )
            )
        except (TypeError, ValueError):
            requested = DEFAULT_VERIFICATION_TTL_SECONDS
        return min(max(requested, 30), 86400)

    def _verification_health(self, state: Mapping[str, object]) -> tuple[bool, bool]:
        if not bool(state.get("verified")):
            return False, False
        raw_verified_at = state.get("verified_at")
        try:
            verified_at = datetime.fromisoformat(str(raw_verified_at).replace("Z", "+00:00"))
            if verified_at.tzinfo is None:
                verified_at = verified_at.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - verified_at.astimezone(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return False, True
        healthy = 0 <= age <= self._verification_ttl_seconds()
        return healthy, not healthy

    def _refresh_expired_private_vast_worker(self, state: Mapping[str, object]) -> dict[str, object]:
        """Renew an expired lease only after probing its already-approved private worker.

        This keeps a verified Tailscale/private worker usable across the lease
        boundary without turning arbitrary public URLs into an unattended
        outbound-probe mechanism.  Public hosts still require an explicit
        allowlist entry and continue to fail closed when the lease expires.
        """
        raw_endpoint = state.get("endpoint")
        endpoint = raw_endpoint if isinstance(raw_endpoint, Mapping) else {}
        url = str(endpoint.get("url") or "").strip()
        model = str(endpoint.get("model") or "").strip()
        if not url or not model:
            return dict(state)
        try:
            validated = validate_worker_url(
                url,
                allowed_hosts=self.env.get("NOVA_GPU_HUB_REMOTE_MODEL_ALLOWLIST", ""),
            )
            base = validated.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            request = urllib.request.Request(
                base + "/v1/models",
                headers={"Accept": "application/json"},
                method="GET",
            )
            with open_without_redirects(request, timeout=3) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
            models = payload.get("data", []) if isinstance(payload, dict) else []
            model_ids = {
                str(item.get("id"))
                for item in models
                if isinstance(item, Mapping) and item.get("id")
            }
            if model_ids and model not in model_ids:
                return dict(state)
        except (OSError, ValueError, TypeError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
            return dict(state)
        renewed = dict(state)
        renewed["verified"] = True
        renewed["verified_backend"] = ComputeMode.VAST_GPU
        renewed["verified_at"] = datetime.now(timezone.utc).isoformat()
        return self.store.save(renewed)

    def status(self) -> dict[str, object]:
        state = self.store.load()
        mode = str(state["mode"])
        local = detect_local_gpu()
        verification_healthy, verification_expired = self._verification_health(state)
        verified_backend = state.get("verified_backend")
        if (
            verification_expired
            and verified_backend == ComputeMode.VAST_GPU
            and mode in {ComputeMode.AUTO, ComputeMode.VAST_GPU}
        ):
            state = self._refresh_expired_private_vast_worker(state)
            verification_healthy, verification_expired = self._verification_health(state)
            verified_backend = state.get("verified_backend")
        if mode == ComputeMode.AUTO:
            if (
                verification_healthy
                and verified_backend == ComputeMode.LOCAL_GPU
                and bool(local.get("usable"))
            ):
                effective, available, reason = ComputeMode.LOCAL_GPU, True, "Local GPU selected automatically."
            elif verification_healthy and verified_backend == ComputeMode.VAST_GPU:
                effective, available, reason = ComputeMode.VAST_GPU, True, "Verified GPU endpoint selected automatically."
            else:
                effective, available, reason = ComputeMode.CPU, True, "No GPU configured; using CPU."
        elif mode == ComputeMode.CPU:
            effective, available, reason = ComputeMode.CPU, True, "CPU-only mode selected."
        elif mode == ComputeMode.LOCAL_GPU:
            available = (
                bool(local.get("usable"))
                and verification_healthy
                and verified_backend == ComputeMode.LOCAL_GPU
            )
            effective = mode
            reason = (
                "Verified local GPU endpoint is ready."
                if available
                else str(local.get("reason", "Local GPU unavailable."))
                if not bool(local.get("usable"))
                else "The verified endpoint belongs to a different GPU backend."
                if verification_healthy and verified_backend != ComputeMode.LOCAL_GPU
                else "Local GPU endpoint verification expired."
                if verification_expired
                else "Local GPU endpoint has not been verified."
            )
        else:
            effective = mode
            available = verification_healthy and verified_backend == ComputeMode.VAST_GPU
            reason = (
                "Verified Vast.ai model endpoint is ready."
                if available
                else "The verified endpoint belongs to a different GPU backend."
                if verification_healthy and verified_backend != ComputeMode.VAST_GPU
                else "Vast.ai model endpoint verification expired."
                if verification_expired
                else "Vast.ai model endpoint has not been verified."
            )
        active_verified = bool(
            verification_healthy
            and effective in VERIFIED_BACKENDS
            and verified_backend == effective
        )
        return {
            "mode": mode,
            "effective_mode": effective,
            "available": available,
            "reason": reason,
            "selected_instance_id": state.get("selected_instance_id"),
            "endpoint": state.get("endpoint", {}),
            "verified": active_verified,
            "verified_backend": verified_backend,
            "verified_at": state.get("verified_at"),
            "verification_expired": verification_expired,
        }

    def set_mode(self, mode: str) -> dict[str, object]:
        if mode not in ComputeMode.ALL:
            raise ValueError(f"invalid compute mode: {mode}")
        state = self.store.load()
        state["mode"] = mode
        self.store.save(state)
        return self.status()

    def local_status(self) -> dict[str, object]:
        return detect_local_gpu()

    def verify_remote_model(
        self,
        endpoint: str,
        model: str,
        *,
        provider: str = "openai-compatible",
        backend: str | None = None,
        selected_instance_id: object | None = None,
    ) -> dict[str, object]:
        clean_url = _sanitize_url(str(endpoint))
        clean_model = str(model or "").strip()
        clean_provider = str(provider or "openai-compatible").strip().lower()
        state = self.store.load()
        clean_backend = str(backend or "").strip().lower()
        if not clean_backend:
            current_mode = str(state.get("mode") or ComputeMode.AUTO)
            if current_mode in VERIFIED_BACKENDS:
                clean_backend = current_mode
            elif selected_instance_id is not None:
                clean_backend = ComputeMode.VAST_GPU
            elif _is_loopback_url(clean_url):
                clean_backend = ComputeMode.LOCAL_GPU
            else:
                clean_backend = ComputeMode.VAST_GPU
        if not clean_url or not clean_model or clean_provider not in {
            "openai-compatible",
            "vllm",
            "sglang",
        }:
            raise GpuHubError(
                "invalid_endpoint_metadata",
                "A supported verified endpoint, model, and provider are required.",
                400,
            )
        if clean_backend not in VERIFIED_BACKENDS:
            raise GpuHubError(
                "invalid_backend",
                "A verified endpoint must target local_gpu or vast_gpu.",
                400,
            )
        if clean_backend == ComputeMode.LOCAL_GPU and not _is_loopback_url(clean_url):
            raise GpuHubError(
                "invalid_local_endpoint",
                "Local GPU mode only accepts a loopback model endpoint.",
                400,
            )
        state.update(
            {
                "endpoint": {
                    "url": clean_url,
                    "model": clean_model,
                    "provider": clean_provider,
                },
                "selected_instance_id": selected_instance_id,
                "verified": True,
                "verified_backend": clean_backend,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return self.store.save(state)

    def _vast(self) -> VastAIClient:
        return VastAIClient(self.env.get("NOVA_VAST_API_KEY", ""), base_url=self.env.get("NOVA_VAST_API_BASE_URL", "https://console.vast.ai/api/v0"))

    def vast_status(self) -> dict[str, object]:
        state = self.store.load()
        verification_healthy, verification_expired = self._verification_health(state)
        if verification_healthy and state.get("verified_backend") == ComputeMode.VAST_GPU:
            return {"available": True, "reason": "Verified Vast.ai model endpoint is ready."}
        if verification_expired and state.get("verified_backend") == ComputeMode.VAST_GPU:
            return {"available": False, "reason": "Vast.ai model endpoint verification expired."}
        if self.env.get("NOVA_VAST_API_KEY"):
            return {"available": False, "reason": "Vast.ai credentials are configured, but no model endpoint is verified."}
        return {"available": False, "reason": "NOVA_VAST_API_KEY is not configured and no model endpoint is verified."}

    def vast_instances(self):
        return self._vast().list_instances()

    def vast_search(self, filters):
        return self._vast().search_offers(filters)

    def vast_create(self, offer_id, payload, *, confirmed=False):
        return self._vast().create_instance(offer_id, payload, confirmed=confirmed)

    def vast_set_state(self, instance_id, state, *, confirmed=False):
        return self._vast().set_instance_state(instance_id, state, confirmed=confirmed)

    def vast_destroy(self, instance_id, *, confirmed=False):
        return self._vast().destroy_instance(instance_id, confirmed=confirmed)
