"""Safe runtime-memory controls for Nova's replaceable local model backends.

The controller releases only in-memory model instances. It never deletes model
files, adapters, checkpoints, registry entries, or training artifacts.
"""

from __future__ import annotations

from contextlib import contextmanager
import ctypes
import json
import os
from threading import RLock
from typing import Iterator
import urllib.request
from urllib.parse import urlparse


_ACTIVITY_LOCK = RLock()
_ACTIVITY_COUNTS: dict[str, int] = {}
_RESIDENCY_LOCK = RLock()
_LAST_RESIDENCY_DECISION: dict = {}
_RESIDENCY_TRANSITIONS = 0

ADAPTIVE_RESOURCE_MANAGER_VERSION = "1.1"
ADAPTIVE_RESOURCE_MANAGER_SCHEMA_VERSION = "1.0"


@contextmanager
def model_activity(model_family: str) -> Iterator[None]:
    """Mark a provider family busy so memory controls cannot interrupt it."""
    family = str(model_family or "unknown").strip().lower() or "unknown"
    with _ACTIVITY_LOCK:
        _ACTIVITY_COUNTS[family] = _ACTIVITY_COUNTS.get(family, 0) + 1
    try:
        yield
    finally:
        with _ACTIVITY_LOCK:
            remaining = max(0, _ACTIVITY_COUNTS.get(family, 1) - 1)
            if remaining:
                _ACTIVITY_COUNTS[family] = remaining
            else:
                _ACTIVITY_COUNTS.pop(family, None)


def model_activity_status() -> dict[str, int]:
    with _ACTIVITY_LOCK:
        return dict(_ACTIVITY_COUNTS)


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _environment_float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def adaptive_model_memory_enabled() -> bool:
    """Return whether safe automatic Ollama residency transitions are enabled."""

    return _environment_bool("NOVA_ADAPTIVE_MODEL_MEMORY", True)


def adaptive_model_memory_reserve_gb() -> float:
    """Return the RAM reserve Nova keeps outside a newly loaded local model."""

    return _environment_float("NOVA_MODEL_MEMORY_RESERVE_GB", 1.5, 0.5, 64.0)


def _normalize_model_name(value: str) -> str:
    return str(value or "").strip().lower().removesuffix(":latest")


def _configured_ollama_model_roles() -> dict[str, set[str]]:
    """Build model-role sets from configuration instead of hardcoded routing names."""

    roles = {
        "primary": set(),
        "middle": set(),
        "deep": set(),
        "vision": set(),
        "raw": set(),
    }
    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
        roles["primary"].add(_normalize_model_name(config.model))
        for task_type in ("general", "reasoning", "coding"):
            roles["middle"].update(
                _normalize_model_name(name)
                for name in config.middle_reviewer_model_preferences(task_type)
            )
            roles["deep"].update(
                _normalize_model_name(name)
                for name in config.escalation_model_preferences(task_type)
            )
    except Exception:
        pass
    roles["vision"].add(
        _normalize_model_name(os.environ.get("NOVA_VISION_MODEL", "moondream"))
    )
    roles["raw"].add(
        _normalize_model_name(
            os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_MODEL", "nova-dolphin3-lora")
        )
    )
    return {
        role: {name for name in names if name}
        for role, names in roles.items()
    }


def _model_role(model_name: str, roles: dict[str, set[str]]) -> str:
    normalized = _normalize_model_name(model_name)
    for role in ("raw", "vision", "primary", "middle", "deep"):
        if normalized in roles.get(role, set()):
            return role
    if "dolphin" in normalized:
        return "raw"
    return "managed"


def configured_ollama_model_role(model_name: str) -> str:
    """Return the configured operational role for one local Ollama model."""

    return _model_role(model_name, _configured_ollama_model_roles())


def _activity_family_for_role(role: str) -> str:
    return {
        "middle": "reviewer",
        "deep": "reviewer",
        "vision": "vision",
        "raw": "dolphin",
        "primary": "primary",
    }.get(role, role)


def _default_model_size_bytes(target_family: str) -> int:
    return {
        "primary": 1_500_000_000,
        "middle": 2_500_000_000,
        "deep": 5_000_000_000,
        "vision": 1_800_000_000,
    }.get(str(target_family or "").strip().lower(), 2_500_000_000)


def _safe_public_decision(decision: dict) -> dict:
    """Keep only operational metadata; request or prompt content never enters status."""

    return {
        key: value
        for key, value in decision.items()
        if key
        in {
            "schema_version",
            "manager_version",
            "enabled",
            "allowed",
            "target_model",
            "target_family",
            "target_resident",
            "estimated_model_bytes",
            "reserve_gb",
            "available_before_gb",
            "available_commit_before_gb",
            "required_before_load_gb",
            "projected_available_gb",
            "commit_fallback_allowed",
            "commit_fallback_used",
            "unmanaged_idle_handoff_allowed",
            "unmanaged_idle_handoff_used",
            "evicted",
            "skipped",
            "reason",
            "transition_count",
            "content_logged",
            "never_deletes_model_files",
            "raw_models_protected",
        }
    }


def adaptive_resource_manager_status() -> dict:
    """Return privacy-safe adaptive model residency state."""

    with _RESIDENCY_LOCK:
        return {
            "schema_version": ADAPTIVE_RESOURCE_MANAGER_SCHEMA_VERSION,
            "manager_version": ADAPTIVE_RESOURCE_MANAGER_VERSION,
            "enabled": adaptive_model_memory_enabled(),
            "reserve_gb": adaptive_model_memory_reserve_gb(),
            "transition_count": _RESIDENCY_TRANSITIONS,
            "last_decision": dict(_LAST_RESIDENCY_DECISION),
            "policy": {
                "never_delete_model_files": True,
                "never_interrupt_busy_models": True,
                "protect_raw_user_models": True,
                "protect_unmanaged_models": True,
                "content_logged": False,
            },
        }


def _memory_status_windows() -> dict:
    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_ulong),
            ("memory_load", ctypes.c_ulong),
            ("total_physical", ctypes.c_ulonglong),
            ("available_physical", ctypes.c_ulonglong),
            ("total_page_file", ctypes.c_ulonglong),
            ("available_page_file", ctypes.c_ulonglong),
            ("total_virtual", ctypes.c_ulonglong),
            ("available_virtual", ctypes.c_ulonglong),
            ("available_extended_virtual", ctypes.c_ulonglong),
        ]

    state = MemoryStatusEx()
    state.length = ctypes.sizeof(MemoryStatusEx)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise OSError("GlobalMemoryStatusEx failed")
    gib = float(1024**3)
    return {
        "memory_load_percent": int(state.memory_load),
        "total_physical_gb": round(state.total_physical / gib, 2),
        "available_physical_gb": round(state.available_physical / gib, 2),
        "total_commit_gb": round(state.total_page_file / gib, 2),
        "available_commit_gb": round(state.available_page_file / gib, 2),
    }


def _memory_status_posix() -> dict:
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    total_pages = int(os.sysconf("SC_PHYS_PAGES"))
    available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
    gib = float(1024**3)
    total = page_size * total_pages
    available = page_size * available_pages
    return {
        "memory_load_percent": round((1 - available / max(total, 1)) * 100),
        "total_physical_gb": round(total / gib, 2),
        "available_physical_gb": round(available / gib, 2),
        "total_commit_gb": None,
        "available_commit_gb": None,
    }


def system_memory_status() -> dict:
    """Return a best-effort, dependency-free system memory snapshot."""
    try:
        return _memory_status_windows() if os.name == "nt" else _memory_status_posix()
    except Exception as error:
        return {
            "memory_load_percent": None,
            "total_physical_gb": None,
            "available_physical_gb": None,
            "total_commit_gb": None,
            "available_commit_gb": None,
            "error": str(error),
        }


def _ollama_base_url() -> str:
    try:
        from nova_local_llm_connector import LocalLLMConfig

        source = str(LocalLLMConfig().url or "http://127.0.0.1:11434/api/generate")
    except Exception:
        source = "http://127.0.0.1:11434/api/generate"
    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "http://127.0.0.1:11434"
    return f"{parsed.scheme}://{parsed.netloc}"


def configured_ollama_base_url() -> str:
    """Return the configured Ollama origin without embedding a model route."""

    return _ollama_base_url()


def list_ollama_loaded_models(timeout: int = 3) -> list[dict]:
    """List currently resident Ollama models without exposing prompts."""
    request = urllib.request.Request(
        _ollama_base_url() + "/api/ps",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return []
    models = []
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        models.append(
            {
                "name": str(item.get("name") or item.get("model") or ""),
                "size_bytes": int(item.get("size") or 0),
                "size_vram_bytes": int(item.get("size_vram") or 0),
                "expires_at": item.get("expires_at"),
            }
        )
    return models


def installed_ollama_model_size_bytes(model_name: str, timeout: int = 3) -> int:
    """Return Ollama's local installed-size metadata for one model."""

    target = _normalize_model_name(model_name)
    if not target:
        return 0
    request = urllib.request.Request(
        _ollama_base_url() + "/api/tags",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(1, int(timeout)),
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return 0
    for item in payload.get("models", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("model") or "")
        if _normalize_model_name(name) != target:
            continue
        try:
            return max(0, int(item.get("size") or 0))
        except (TypeError, ValueError):
            return 0
    return 0


def nova_managed_ollama_models() -> set[str]:
    """Return configured Ollama model names Nova is allowed to unload."""
    names = {str(os.environ.get("NOVA_DOLPHIN_LORA_OLLAMA_MODEL") or "nova-dolphin3-lora").strip()}
    names.add(str(os.environ.get("NOVA_VISION_MODEL") or "moondream").strip())
    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
        names.add(str(config.model or "").strip())
        for task_type in ("general", "reasoning", "coding"):
            names.update(config.middle_reviewer_model_preferences(task_type))
            names.update(config.escalation_model_preferences(task_type))
    except Exception:
        pass
    return {name.removesuffix(":latest") for name in names if name}


def nova_reviewer_ollama_models() -> set[str]:
    """Return installed-model names Nova may use for managed larger review."""

    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
        names = set()
        for task_type in ("general", "reasoning", "coding"):
            names.update(config.middle_reviewer_model_preferences(task_type))
            names.update(config.escalation_model_preferences(task_type))
        primary = str(config.model or "").strip().removesuffix(":latest")
        names = {
            str(name or "").strip().removesuffix(":latest")
            for name in names
            if str(name or "").strip()
        }
        names.discard(primary)
        return names
    except Exception:
        return set()


def unload_ollama_model(model_name: str, timeout: int = 30) -> dict:
    """Unload one Ollama model from RAM while keeping its installed files."""
    name = str(model_name or "").strip()
    if not name:
        raise ValueError("model_name is required")
    request = urllib.request.Request(
        _ollama_base_url() + "/api/generate",
        data=json.dumps({"model": name, "keep_alive": 0}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(1, int(timeout))) as response:
        response.read()
    return {"model": name, "unloaded": True}


def prepare_model_residency(
    target_model: str,
    *,
    target_family: str = "managed",
    estimated_model_bytes: int = 0,
    protected_models: tuple[str, ...] = (),
    allow_commit_fallback: bool = False,
    allow_unmanaged_idle_handoff: bool = False,
    timeout: int = 20,
) -> dict:
    """Safely make RAM headroom for one Nova-managed Ollama model.

    Only idle Nova-managed Ollama runtimes may be released. Installed files,
    adapters, raw user-selected models, unmanaged models, and busy generations
    are never touched.
    """

    global _LAST_RESIDENCY_DECISION, _RESIDENCY_TRANSITIONS

    target = str(target_model or "").strip()
    family = str(target_family or "managed").strip().lower() or "managed"
    normalized_target = _normalize_model_name(target)
    estimate = max(0, int(estimated_model_bytes or 0))
    if not estimate:
        estimate = _default_model_size_bytes(family)
    reserve_gb = adaptive_model_memory_reserve_gb()
    decision = {
        "schema_version": ADAPTIVE_RESOURCE_MANAGER_SCHEMA_VERSION,
        "manager_version": ADAPTIVE_RESOURCE_MANAGER_VERSION,
        "enabled": adaptive_model_memory_enabled(),
        "allowed": False,
        "target_model": target or None,
        "target_family": family,
        "target_resident": False,
        "estimated_model_bytes": estimate,
        "reserve_gb": reserve_gb,
        "available_before_gb": None,
        "available_commit_before_gb": None,
        "required_before_load_gb": None,
        "projected_available_gb": None,
        "commit_fallback_allowed": bool(allow_commit_fallback),
        "commit_fallback_used": False,
        "unmanaged_idle_handoff_allowed": bool(allow_unmanaged_idle_handoff),
        "unmanaged_idle_handoff_used": False,
        "evicted": [],
        "skipped": [],
        "reason": "invalid_target",
        "transition_count": _RESIDENCY_TRANSITIONS,
        "content_logged": False,
        "never_deletes_model_files": True,
        "raw_models_protected": True,
    }
    if not normalized_target:
        return decision

    with _RESIDENCY_LOCK:
        if not decision["enabled"]:
            decision.update(allowed=True, reason="disabled_preserve_compatibility")
            _LAST_RESIDENCY_DECISION = _safe_public_decision(decision)
            return decision

        loaded_models = list_ollama_loaded_models()
        resident_names = {
            _normalize_model_name(item.get("name", ""))
            for item in loaded_models
            if isinstance(item, dict)
        }
        if normalized_target in resident_names:
            decision.update(
                allowed=True,
                target_resident=True,
                reason="already_resident",
            )
            memory = system_memory_status()
            decision["available_before_gb"] = memory.get("available_physical_gb")
            decision["projected_available_gb"] = memory.get("available_physical_gb")
            _LAST_RESIDENCY_DECISION = _safe_public_decision(decision)
            return decision

        memory = system_memory_status()
        available_gb = memory.get("available_physical_gb")
        available_commit_gb = memory.get("available_commit_gb")
        if available_gb is None:
            decision.update(
                allowed=True,
                reason="memory_unknown_preserve_compatibility",
            )
            _LAST_RESIDENCY_DECISION = _safe_public_decision(decision)
            return decision

        available_gb = max(0.0, float(available_gb))
        # The small overhead factor covers runtime buffers without pretending to
        # know an exact platform-specific allocation.
        required_gb = estimate / float(1024**3) * 1.12 + reserve_gb
        projected_gb = available_gb
        decision.update(
            available_before_gb=round(available_gb, 2),
            available_commit_before_gb=(
                round(max(0.0, float(available_commit_gb)), 2)
                if available_commit_gb is not None
                else None
            ),
            required_before_load_gb=round(required_gb, 2),
            projected_available_gb=round(projected_gb, 2),
        )
        if projected_gb >= required_gb:
            decision.update(allowed=True, reason="headroom_available")
            _LAST_RESIDENCY_DECISION = _safe_public_decision(decision)
            return decision

        roles = _configured_ollama_model_roles()
        managed_names = {_normalize_model_name(name) for name in nova_managed_ollama_models()}
        protected = {_normalize_model_name(name) for name in protected_models}
        protected.add(normalized_target)
        activity = model_activity_status()
        priorities = {
            "deep": {"middle": 0, "vision": 1, "deep": 2, "primary": 3, "managed": 4},
            "middle": {"deep": 0, "vision": 1, "middle": 2, "primary": 3, "managed": 4},
            "vision": {"deep": 0, "middle": 1, "vision": 2, "primary": 3, "managed": 4},
            "primary": {"deep": 0, "middle": 1, "vision": 2, "managed": 3, "primary": 4},
        }.get(family, {"deep": 0, "middle": 1, "vision": 2, "primary": 3, "managed": 4})
        candidates = []
        for item in loaded_models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            normalized_name = _normalize_model_name(name)
            role = _model_role(name, roles)
            if not normalized_name or normalized_name in protected:
                continue
            is_managed = normalized_name in managed_names
            if not is_managed and not (
                allow_unmanaged_idle_handoff
                and family == "vision"
                and role == "managed"
            ):
                decision["skipped"].append(
                    {"model": name, "role": role, "reason": "unmanaged_model_protected"}
                )
                continue
            if role == "raw":
                decision["skipped"].append(
                    {"model": name, "role": role, "reason": "raw_user_model_protected"}
                )
                continue
            activity_family = _activity_family_for_role(role)
            if int(activity.get(activity_family) or 0) > 0:
                decision["skipped"].append(
                    {"model": name, "role": role, "reason": "generation_in_progress"}
                )
                continue
            candidate_role = role if is_managed else "unmanaged_idle"
            size_bytes = max(0, int(item.get("size_bytes") or 0))
            candidates.append(
                (
                    priorities.get(role, 9),
                    -size_bytes,
                    name,
                    candidate_role,
                    size_bytes,
                )
            )

        for _, _, name, role, size_bytes in sorted(candidates):
            if projected_gb >= required_gb:
                break
            try:
                unload_ollama_model(name, timeout=timeout)
                released_gb = size_bytes / float(1024**3)
                projected_gb += released_gb
                decision["evicted"].append(
                    {
                        "model": name,
                        "role": role,
                        "released_estimate_gb": round(released_gb, 2),
                    }
                )
                if role == "unmanaged_idle":
                    decision["unmanaged_idle_handoff_used"] = True
            except Exception:
                decision["skipped"].append(
                    {"model": name, "role": role, "reason": "unload_failed"}
                )

        if decision["evicted"]:
            _RESIDENCY_TRANSITIONS += 1
        decision["transition_count"] = _RESIDENCY_TRANSITIONS
        decision["projected_available_gb"] = round(projected_gb, 2)
        decision["allowed"] = projected_gb >= required_gb
        if decision["allowed"]:
            decision["reason"] = "safe_headroom_created"
        elif (
            allow_commit_fallback
            and available_commit_gb is not None
            and max(0.0, float(available_commit_gb)) >= required_gb
            and available_gb >= 0.75
        ):
            # Windows can safely page an idle text runtime while a user-requested
            # vision model runs. Keep this opt-in so background warmups and normal
            # chat never trade responsiveness for virtual-memory headroom.
            decision.update(
                allowed=True,
                commit_fallback_used=True,
                reason="commit_headroom_available",
            )
        else:
            decision["reason"] = "insufficient_safe_memory"
        _LAST_RESIDENCY_DECISION = _safe_public_decision(decision)
        return decision


@contextmanager
def managed_model_residency(
    target_model: str,
    *,
    target_family: str = "managed",
    estimated_model_bytes: int = 0,
    protected_models: tuple[str, ...] = (),
    allow_commit_fallback: bool = False,
    allow_unmanaged_idle_handoff: bool = False,
    timeout: int = 20,
) -> Iterator[dict]:
    """Atomically prepare residency and protect the target while it generates."""

    activity_context = None
    with _RESIDENCY_LOCK:
        decision = prepare_model_residency(
            target_model,
            target_family=target_family,
            estimated_model_bytes=estimated_model_bytes,
            protected_models=protected_models,
            allow_commit_fallback=allow_commit_fallback,
            allow_unmanaged_idle_handoff=allow_unmanaged_idle_handoff,
            timeout=timeout,
        )
        if decision.get("allowed"):
            activity_context = model_activity(_activity_family_for_role(target_family))
            activity_context.__enter__()
    try:
        yield decision
    finally:
        if activity_context is not None:
            activity_context.__exit__(None, None, None)


def model_memory_status() -> dict:
    """Report local model residency and whether each family is busy."""
    from nova_lora_runtime import runtime_cache_status

    activity = model_activity_status()
    hf_runtimes = runtime_cache_status()
    ollama_models = list_ollama_loaded_models()
    reviewer_names = nova_reviewer_ollama_models()
    return {
        "ok": True,
        "system": system_memory_status(),
        "huggingface_runtimes": hf_runtimes,
        "ollama_models": ollama_models,
        "activity": activity,
        "qwen": {
            "loaded": any(
                item.get("loaded") and "qwen" in f"{item.get('base_model', '')} {item.get('adapter_name', '')}".lower()
                for item in hf_runtimes
            ),
            "busy": any(
                item.get("busy") and "qwen" in f"{item.get('base_model', '')} {item.get('adapter_name', '')}".lower()
                for item in hf_runtimes
            ),
            "unload_requested": any(
                item.get("unload_requested") and "qwen" in f"{item.get('base_model', '')} {item.get('adapter_name', '')}".lower()
                for item in hf_runtimes
            ),
        },
        "dolphin": {
            "loaded": any("dolphin" in item.get("name", "").lower() for item in ollama_models),
            "busy": activity.get("dolphin", 0) > 0,
        },
        "reviewer": {
            "loaded": any(
                str(item.get("name") or "").removesuffix(":latest") in reviewer_names
                for item in ollama_models
            ),
            "busy": activity.get("reviewer", 0) > 0,
            "models": [
                str(item.get("name") or "")
                for item in ollama_models
                if str(item.get("name") or "").removesuffix(":latest") in reviewer_names
            ],
        },
        "adaptive_resource_manager": adaptive_resource_manager_status(),
        "policy": {
            "single_huggingface_runtime": True,
            "never_delete_model_files": True,
            "skip_busy_models": True,
            "adaptive_residency": adaptive_model_memory_enabled(),
            "protect_raw_user_models": True,
        },
    }


def unload_model_memory(target: str = "idle") -> dict:
    """Release selected idle model memory and return the refreshed status."""
    from nova_lora_runtime import unload_cached_lora_runtimes

    normalized = str(target or "idle").strip().lower()
    if normalized not in {"idle", "all", "qwen", "dolphin", "reviewer"}:
        raise ValueError("target must be idle, all, qwen, dolphin, or reviewer")

    unloaded: list[dict] = []
    skipped: list[dict] = []
    if normalized in {"idle", "all", "qwen"}:
        hf_result = unload_cached_lora_runtimes(
            force=False,
            family="qwen" if normalized == "qwen" else None,
        )
        unloaded.extend({"provider": "huggingface", **item} for item in hf_result["unloaded"])
        skipped.extend({"provider": "huggingface", **item} for item in hf_result["skipped"])

    if normalized in {"idle", "all", "dolphin", "reviewer"}:
        activity = model_activity_status()
        if normalized == "dolphin" and activity.get("dolphin", 0):
            skipped.append({"provider": "ollama", "model": "dolphin", "reason": "generation_in_progress"})
        elif normalized == "reviewer" and activity.get("reviewer", 0):
            skipped.append({"provider": "ollama", "model": "reviewer", "reason": "generation_in_progress"})
        else:
            managed_names = nova_managed_ollama_models()
            reviewer_names = nova_reviewer_ollama_models()
            for model in list_ollama_loaded_models():
                name = model.get("name", "")
                normalized_name = str(name).removesuffix(":latest")
                if normalized_name not in managed_names:
                    continue
                if normalized == "dolphin" and "dolphin" not in name.lower():
                    continue
                if normalized == "reviewer" and normalized_name not in reviewer_names:
                    continue
                if normalized in {"idle", "all"}:
                    family = "reviewer" if normalized_name in reviewer_names else (
                        "dolphin" if "dolphin" in name.lower() else ""
                    )
                    if family and activity.get(family, 0):
                        skipped.append(
                            {
                                "provider": "ollama",
                                "model": name,
                                "reason": "generation_in_progress",
                            }
                        )
                        continue
                try:
                    unloaded.append({"provider": "ollama", **unload_ollama_model(name)})
                except Exception as error:
                    skipped.append({"provider": "ollama", "model": name, "reason": str(error)})

    return {
        "ok": not skipped,
        "target": normalized,
        "unloaded": unloaded,
        "skipped": skipped,
        "status": model_memory_status(),
    }
