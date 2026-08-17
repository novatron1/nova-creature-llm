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
            return {"mode": ComputeMode.AUTO, "selected_instance_id": None, "endpoint": {}, "updated_at": None}

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
        if key not in {"url", "model", "provider", "region"} or not isinstance(value, (str, int, float, bool, type(None))):
            continue
        if key == "url":
            value = _sanitize_url(str(value))
        elif _looks_secret(key, value):
            continue
        endpoint[key] = value
    return {"mode": mode, "selected_instance_id": state.get("selected_instance_id"), "endpoint": endpoint, "updated_at": state.get("updated_at")}


def _looks_secret(key: object, value: object) -> bool:
    return bool(re.search(r"key|token|secret|password|credential", str(key), re.I)) or "SECRET" in str(value)


def _sanitize_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return ""
        host = parsed.hostname
        if parsed.port:
            host += f":{parsed.port}"
        return urllib.parse.urlunsplit((parsed.scheme, host, parsed.path, "", ""))
    except ValueError:
        return ""


class VastAIClient:
    def __init__(self, api_key: str, base_url: str = "https://console.vast.ai/api/v0", timeout: int = 15):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = min(max(int(timeout), 1), 15)

    def _request(self, method: str, path: str, payload: object | None = None) -> object:
        if not self.api_key:
            raise GpuHubError("vast_unavailable", "Vast.ai is unavailable because NOVA_VAST_API_KEY is not configured.")
        url = self.base_url + "/" + path.lstrip("/")
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method, headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode() or "{}")
                return data
        except urllib.error.HTTPError as exc:
            raise GpuHubError("vast_http_error", f"Vast.ai request failed ({exc.code}).", exc.code) from None
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise GpuHubError("vast_request_failed", _redact(str(exc), self.api_key)) from None

    def list_instances(self) -> list[dict[str, object]]:
        return _list_result(self._request("GET", "instances/"))

    def show_instance(self, instance_id: str) -> dict[str, object]:
        return _dict_result(self._request("GET", f"instances/{urllib.parse.quote(str(instance_id), safe='')}/"))

    def search_offers(self, filters: Mapping[str, object] | None) -> list[dict[str, object]]:
        result = self._request("GET", "asks/" + (("?" + urllib.parse.urlencode(filters or {})) if filters else ""))
        return _list_result(result)

    def create_instance(self, offer_id: object, payload: Mapping[str, object], *, confirmed: bool = False) -> dict[str, object]:
        if not confirmed:
            raise GpuHubError("confirmation_required", "Starting a paid Vast.ai instance requires confirmation.")
        data = dict(payload)
        data.setdefault("ask_id", offer_id)
        return _dict_result(self._request("PUT", "asks/", data))

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

    def status(self) -> dict[str, object]:
        state = self.store.load()
        mode = str(state["mode"])
        local = detect_local_gpu()
        if mode == ComputeMode.AUTO:
            if bool(local.get("usable")):
                effective, available, reason = ComputeMode.LOCAL_GPU, True, "Local GPU selected automatically."
            elif self.env.get("NOVA_VAST_API_KEY"):
                effective, available, reason = ComputeMode.VAST_GPU, True, "Vast.ai GPU is configured for automatic use."
            else:
                effective, available, reason = ComputeMode.CPU, True, "No GPU configured; using CPU."
        elif mode == ComputeMode.CPU:
            effective, available, reason = ComputeMode.CPU, True, "CPU-only mode selected."
        elif mode == ComputeMode.LOCAL_GPU:
            effective, available, reason = mode, bool(local.get("usable")), str(local.get("reason", "Local GPU unavailable."))
        else:
            effective, available, reason = mode, bool(self.env.get("NOVA_VAST_API_KEY")), "Vast.ai credentials configured." if self.env.get("NOVA_VAST_API_KEY") else "NOVA_VAST_API_KEY is not configured."
        return {"mode": mode, "effective_mode": effective, "available": available, "reason": reason, "selected_instance_id": state.get("selected_instance_id"), "endpoint": state.get("endpoint", {})}

    def set_mode(self, mode: str) -> dict[str, object]:
        if mode not in ComputeMode.ALL:
            raise ValueError(f"invalid compute mode: {mode}")
        state = self.store.load()
        state["mode"] = mode
        self.store.save(state)
        return self.status()

    def local_status(self) -> dict[str, object]:
        return detect_local_gpu()

    def _vast(self) -> VastAIClient:
        return VastAIClient(self.env.get("NOVA_VAST_API_KEY", ""), base_url=self.env.get("NOVA_VAST_API_BASE_URL", "https://console.vast.ai/api/v0"))

    def vast_status(self) -> dict[str, object]:
        if not self.env.get("NOVA_VAST_API_KEY"):
            return {"available": False, "reason": "NOVA_VAST_API_KEY is not configured."}
        return {"available": True, "reason": "Vast.ai credentials configured."}

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
