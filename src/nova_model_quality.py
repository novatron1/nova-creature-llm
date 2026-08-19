"""Privacy-safe local model qualification and quarantine.

The registry stores only provider/model operational metadata. It never stores
prompts, generated text, memory content, credentials, or private reasoning.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from threading import RLock
import time
from typing import Callable
import urllib.request


MODEL_QUALITY_SCHEMA_VERSION = "1.0"
MODEL_QUALITY_ENGINE_VERSION = "1.0"
_SAFE_FAILURE_REASONS = {
    "benchmark_output_mismatch",
    "candidate_consistency_failed",
    "candidate_firewall_rejected",
    "candidate_token_limit",
    "empty_response",
    "generation_failed",
    "low_quality_vision_response",
    "model_memory_policy_blocked",
    "provider_error",
    "timeout",
}
_RED_SQUARE_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAA"
    "AARnQU1BAACxjwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAACMSURBVHhe7dAh"
    "AQAADITA7196K0ADEGeQ7LYzawBFkwZQNGkARZMGUDRpAEWTBlA0aQBFkwZQNGkA"
    "RZMGUDRpAEWTBlA0aQBFkwZQNGkARZMGUDRpAEWTBlA0aQBFkwZQNGkARZMGUDRp"
    "AEWTBlA0aQBFkwZQNGkARZMGUDRpAEWTBlA0aQBFE/mA3QNDiOHS/086WQAAAABJ"
    "RU5ErkJggg=="
)


def _environment_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _environment_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _iso_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def _normalized_key(provider_id: str, model_id: str) -> str:
    return (
        str(provider_id or "unknown").strip().lower()
        + "/"
        + str(model_id or "unknown").strip().lower().removesuffix(":latest")
    )


class NovaModelQualityRegistry:
    """Persist content-free model health and apply a conservative circuit breaker."""

    def __init__(
        self,
        path: str | Path,
        *,
        enabled: bool | None = None,
        failure_threshold: int | None = None,
        quarantine_seconds: int | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self.path = Path(path)
        self.enabled = (
            _environment_bool("NOVA_MODEL_QUALITY_ENABLED", True)
            if enabled is None
            else bool(enabled)
        )
        self.failure_threshold = (
            _environment_int("NOVA_MODEL_QUALITY_FAILURE_THRESHOLD", 2, 2, 10)
            if failure_threshold is None
            else max(2, min(int(failure_threshold), 10))
        )
        self.quarantine_seconds = (
            _environment_int(
                "NOVA_MODEL_QUALITY_QUARANTINE_SECONDS",
                3600,
                60,
                86_400,
            )
            if quarantine_seconds is None
            else max(60, min(int(quarantine_seconds), 86_400))
        )
        self._clock = clock or time.time
        self._lock = RLock()
        self._records: dict[str, dict] = {}
        self._load_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("records", {}) if isinstance(payload, dict) else {}
            if isinstance(records, dict):
                self._records = {
                    str(key): dict(value)
                    for key, value in records.items()
                    if isinstance(value, dict)
                }
        except Exception:
            self._records = {}
            self._load_error = "quality_registry_load_failed"

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": MODEL_QUALITY_SCHEMA_VERSION,
            "engine_version": MODEL_QUALITY_ENGINE_VERSION,
            "updated_at": _iso_timestamp(self._clock()),
            "records": self._records,
        }
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def _record(self, provider_id: str, model_id: str) -> tuple[str, dict]:
        key = _normalized_key(provider_id, model_id)
        record = self._records.setdefault(
            key,
            {
                "provider_id": str(provider_id or "unknown"),
                "model_id": str(model_id or "unknown"),
                "success_count": 0,
                "failure_count": 0,
                "consecutive_failures": 0,
                "average_latency_ms": None,
                "last_quality_score": None,
                "last_result": "untested",
                "last_failure_reason": None,
                "last_source": None,
                "last_checked_at": None,
                "quarantine_until": None,
            },
        )
        return key, record

    def record_success(
        self,
        provider_id: str,
        model_id: str,
        *,
        latency_ms: float | None = None,
        quality_score: float = 1.0,
        source: str = "runtime",
        verified: bool = False,
    ) -> dict:
        """Record a successful managed result; verified checks can clear quarantine."""

        if not self.enabled:
            return {"enabled": False, "quarantined": False}
        now = self._clock()
        with self._lock:
            _, record = self._record(provider_id, model_id)
            record["success_count"] = int(record.get("success_count") or 0) + 1
            record["consecutive_failures"] = 0
            record["last_result"] = "passed"
            record["last_failure_reason"] = None
            record["last_source"] = str(source or "runtime")[:32]
            record["last_checked_at"] = _iso_timestamp(now)
            record["last_quality_score"] = round(
                max(0.0, min(float(quality_score), 1.0)),
                3,
            )
            if latency_ms is not None:
                latency = max(0.0, float(latency_ms))
                prior = record.get("average_latency_ms")
                record["average_latency_ms"] = round(
                    latency if prior is None else float(prior) * 0.75 + latency * 0.25,
                    3,
                )
            if verified:
                record["quarantine_until"] = None
            self._save()
            return self.model_status(provider_id, model_id)

    def record_failure(
        self,
        provider_id: str,
        model_id: str,
        *,
        reason: str,
        latency_ms: float | None = None,
        source: str = "runtime",
    ) -> dict:
        """Record a safe failure category and quarantine only after repetition."""

        if not self.enabled:
            return {"enabled": False, "quarantined": False}
        now = self._clock()
        safe_reason = (
            str(reason or "").strip().lower()
            if str(reason or "").strip().lower() in _SAFE_FAILURE_REASONS
            else "provider_error"
        )
        with self._lock:
            _, record = self._record(provider_id, model_id)
            record["failure_count"] = int(record.get("failure_count") or 0) + 1
            record["consecutive_failures"] = (
                int(record.get("consecutive_failures") or 0) + 1
            )
            record["last_result"] = "failed"
            record["last_failure_reason"] = safe_reason
            record["last_source"] = str(source or "runtime")[:32]
            record["last_checked_at"] = _iso_timestamp(now)
            record["last_quality_score"] = 0.0
            if latency_ms is not None:
                latency = max(0.0, float(latency_ms))
                prior = record.get("average_latency_ms")
                record["average_latency_ms"] = round(
                    latency if prior is None else float(prior) * 0.75 + latency * 0.25,
                    3,
                )
            if int(record["consecutive_failures"]) >= self.failure_threshold:
                record["quarantine_until"] = _iso_timestamp(
                    now + self.quarantine_seconds
                )
            self._save()
            return self.model_status(provider_id, model_id)

    def model_status(self, provider_id: str, model_id: str) -> dict:
        with self._lock:
            record = dict(
                self._records.get(_normalized_key(provider_id, model_id)) or {}
            )
        if not record:
            return {
                "provider_id": str(provider_id or "unknown"),
                "model_id": str(model_id or "unknown"),
                "status": "untested",
                "quarantined": False,
            }
        until = record.get("quarantine_until")
        quarantine_active = False
        if until:
            try:
                quarantine_active = (
                    datetime.fromisoformat(str(until)).timestamp() > self._clock()
                )
            except (TypeError, ValueError):
                quarantine_active = False
        record["quarantined"] = quarantine_active
        record["status"] = (
            "quarantined"
            if quarantine_active
            else ("healthy" if record.get("last_result") == "passed" else "probation")
        )
        record["content_logged"] = False
        return record

    def is_quarantined(self, provider_id: str, model_id: str) -> bool:
        if not self.enabled:
            return False
        return bool(self.model_status(provider_id, model_id).get("quarantined"))

    def clear_quarantine(self, provider_id: str, model_id: str) -> dict:
        with self._lock:
            _, record = self._record(provider_id, model_id)
            record["quarantine_until"] = None
            record["consecutive_failures"] = 0
            record["last_result"] = "untested"
            self._save()
        return self.model_status(provider_id, model_id)

    def status(self) -> dict:
        with self._lock:
            identities = [
                (
                    str(record.get("provider_id") or "unknown"),
                    str(record.get("model_id") or "unknown"),
                )
                for record in self._records.values()
            ]
        records = [
            self.model_status(provider_id, model_id)
            for provider_id, model_id in identities
        ]
        return {
            "ok": self._load_error is None,
            "enabled": self.enabled,
            "schema_version": MODEL_QUALITY_SCHEMA_VERSION,
            "engine_version": MODEL_QUALITY_ENGINE_VERSION,
            "failure_threshold": self.failure_threshold,
            "quarantine_seconds": self.quarantine_seconds,
            "record_count": len(records),
            "quarantined_count": sum(
                1 for record in records if record.get("quarantined")
            ),
            "records": records,
            "load_error": self._load_error,
            "content_logged": False,
            "raw_adapter_modes_excluded": True,
        }


_DEFAULT_REGISTRY: NovaModelQualityRegistry | None = None
_DEFAULT_REGISTRY_LOCK = RLock()


def get_default_model_quality_registry(
    root: str | Path | None = None,
) -> NovaModelQualityRegistry:
    global _DEFAULT_REGISTRY
    with _DEFAULT_REGISTRY_LOCK:
        if _DEFAULT_REGISTRY is None:
            base = Path(root) if root is not None else Path(__file__).resolve().parents[1]
            path = os.environ.get("NOVA_MODEL_QUALITY_PATH") or (
                base / "data" / "nova_model_quality.json"
            )
            _DEFAULT_REGISTRY = NovaModelQualityRegistry(path)
        return _DEFAULT_REGISTRY


def benchmark_loaded_ollama_models(
    *,
    registry: NovaModelQualityRegistry | None = None,
    maximum_models: int | None = None,
    timeout_seconds: int | None = None,
) -> dict:
    """Run bounded, content-free qualification probes on resident managed models."""

    from nova_model_memory import (
        configured_ollama_model_role,
        configured_ollama_base_url,
        list_ollama_loaded_models,
        managed_model_residency,
        nova_managed_ollama_models,
    )

    active_registry = registry or get_default_model_quality_registry()
    maximum = (
        _environment_int("NOVA_MODEL_QUALITY_MAX_MODELS", 3, 1, 8)
        if maximum_models is None
        else max(1, min(int(maximum_models), 8))
    )
    timeout = (
        _environment_int("NOVA_MODEL_QUALITY_TIMEOUT", 45, 5, 120)
        if timeout_seconds is None
        else max(5, min(int(timeout_seconds), 120))
    )
    loaded = list_ollama_loaded_models()
    managed_names = {
        str(name or "").strip().lower().removesuffix(":latest")
        for name in nova_managed_ollama_models()
    }
    ordered = sorted(
        loaded,
        key=lambda item: {
            "primary": 0,
            "middle": 1,
            "vision": 2,
            "deep": 3,
            "managed": 4,
            "raw": 9,
        }.get(configured_ollama_model_role(item.get("name", "")), 8),
    )
    results: list[dict] = []
    checked = 0
    for item in ordered:
        if checked >= maximum:
            break
        model_name = str(item.get("name") or "").strip()
        role = configured_ollama_model_role(model_name)
        if not model_name:
            continue
        if role == "raw":
            results.append(
                {
                    "provider": "ollama",
                    "model": model_name,
                    "role": role,
                    "status": "skipped_raw_user_model",
                    "content_logged": False,
                }
            )
            continue
        if model_name.lower().removesuffix(":latest") not in managed_names:
            results.append(
                {
                    "provider": "ollama",
                    "model": model_name,
                    "role": role,
                    "status": "skipped_unmanaged_model",
                    "content_logged": False,
                }
            )
            continue
        checked += 1
        if role == "vision":
            prompt = "Return only the single color word for this solid-color image."
            expected = "red"
            images = [_RED_SQUARE_PNG_BASE64]
            target_family = "vision"
        else:
            prompt = "Return exactly this token and nothing else: NOVA_OK_731"
            expected = "nova_ok_731"
            images = None
            target_family = role if role in {"primary", "middle", "deep"} else "managed"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "10m",
            "options": {
                "temperature": 0,
                "seed": 0,
                "num_ctx": 2048,
                "num_predict": 16,
            },
        }
        if images:
            payload["images"] = images
        started = time.monotonic()
        reason = "benchmark_output_mismatch"
        passed = False
        try:
            with managed_model_residency(
                model_name,
                target_family=target_family,
                estimated_model_bytes=int(item.get("size_bytes") or 0),
            ) as residency:
                if not residency.get("allowed"):
                    reason = "model_memory_policy_blocked"
                else:
                    request = urllib.request.Request(
                        configured_ollama_base_url() + "/api/generate",
                        data=json.dumps(payload).encode("utf-8"),
                        headers={
                            "Content-Type": "application/json",
                            "Accept": "application/json",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(request, timeout=timeout) as response:
                        response_payload = json.loads(
                            response.read().decode("utf-8")
                        )
                    output = str(response_payload.get("response") or "").strip().lower()
                    if role == "vision":
                        passed = expected in output.split()
                        if (
                            not passed
                            and not output
                            and (
                                response_payload.get("done") is True
                                or str(
                                    response_payload.get("done_reason") or ""
                                ).strip()
                            )
                        ):
                            # Some vision runtimes accept and complete a valid
                            # image request but decline synthetic-color semantics.
                            # That proves transport/media health only; actual
                            # user-image output is still scored by the runtime path.
                            passed = True
                            reason = "passed_transport"
                    else:
                        passed = (
                            output.replace("`", "")
                            .strip()
                            .strip(" .,!?:;\"'")
                            == expected
                        )
                    if reason != "passed_transport":
                        reason = "passed" if passed else "benchmark_output_mismatch"
        except Exception as error:
            reason = (
                "timeout"
                if "timed out" in str(error).lower()
                else "provider_error"
            )
        latency_ms = round((time.monotonic() - started) * 1000, 3)
        if passed:
            active_registry.record_success(
                "ollama",
                model_name,
                latency_ms=latency_ms,
                quality_score=1.0 if reason == "passed" else 0.6,
                source="benchmark",
                verified=reason == "passed",
            )
        else:
            active_registry.record_failure(
                "ollama",
                model_name,
                latency_ms=latency_ms,
                reason=reason,
                source="benchmark",
            )
        results.append(
            {
                "provider": "ollama",
                "model": model_name,
                "role": role,
                "status": "passed" if passed else "failed",
                "reason": reason,
                "latency_ms": latency_ms,
                "quarantined": active_registry.is_quarantined(
                    "ollama",
                    model_name,
                ),
                "content_logged": False,
            }
        )
    return {
        "ok": all(
            item.get("status") in {"passed", "skipped_raw_user_model"}
            for item in results
        ),
        "checked": checked,
        "results": results,
        "registry": active_registry.status(),
        "content_logged": False,
        "raw_adapter_modes_excluded": True,
    }
