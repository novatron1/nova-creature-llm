"""
Nova LoRA Runtime
=================
Optional Hugging Face + PEFT runtime for Nova's imported LoRA adapters.

This does not replace Nova's router or memory system. It gives the existing
local LLM connector a real adapter-backed generation path when the required
runtime packages and model files are available, and lets the connector fall
back to Ollama when they are not.
"""

from __future__ import annotations

import gc
import os
from pathlib import Path
from queue import Empty
from threading import Event, RLock, Thread
from typing import Callable, Optional
import time


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVIDER = "hf_peft_lora"
NOVA_LORA_SYSTEM_PROMPT = (
    "You are Nova Creature, the user's local Nova assistant. "
    "Do not claim the identity or origin of the base model provider. "
    "Speak naturally as Nova Creature, stay grounded in Nova's memory/router context, "
    "and do not invent personal saved facts."
)

_RUNTIME_CACHE: dict[tuple[str, str, str, bool], "NovaLoraRuntime"] = {}
_RUNTIME_CACHE_LOCK = RLock()


def _make_response(**kwargs):
    from nova_local_llm_connector import LocalLLMResponse

    return LocalLLMResponse(**kwargs)


def _clean_output(text: str, prompt: str = "") -> str:
    from nova_local_llm_connector import clean_local_llm_output

    cleaned = clean_local_llm_output(text)
    prompt = str(prompt or "").strip()
    if prompt and cleaned.startswith(prompt):
        cleaned = cleaned[len(prompt) :].strip()
    return cleaned.strip()


def _tensor_to_device(value, device: str):
    if hasattr(value, "to"):
        return value.to(device)
    return value


def _inputs_to_device(inputs, device: str):
    if hasattr(inputs, "to"):
        return inputs.to(device)
    if isinstance(inputs, dict):
        return {key: _tensor_to_device(value, device) for key, value in inputs.items()}
    if hasattr(inputs, "input_ids"):
        inputs.input_ids = _tensor_to_device(inputs.input_ids, device)
    return inputs


def _input_ids_from(inputs):
    if isinstance(inputs, dict):
        return inputs.get("input_ids")
    return getattr(inputs, "input_ids", None)


def _generate_kwargs_from_inputs(inputs) -> dict:
    if isinstance(inputs, dict):
        return dict(inputs)
    input_ids = _input_ids_from(inputs)
    if input_ids is None:
        return {}
    return {"input_ids": input_ids}


def _new_tokens(output_ids, input_len: int):
    try:
        return output_ids[0, input_len:]
    except Exception:
        try:
            return output_ids[0][input_len:]
        except Exception:
            return output_ids


class NovaLoraRuntime:
    """Lazy PEFT runtime for one base model + adapter pair."""

    def __init__(
        self,
        base_model: str,
        adapter_path: str,
        device: str = "auto",
        trust_remote_code: bool = True,
        allow_model_downloads: bool = False,
    ):
        self.base_model = str(base_model or "").strip()
        self.adapter_path = str(adapter_path or "").strip()
        self.device_preference = str(device or "auto").strip().lower()
        self.trust_remote_code = trust_remote_code
        self.allow_model_downloads = bool(allow_model_downloads)
        self.tokenizer = None
        self.model = None
        self.device = "cpu"
        self._load_lock = RLock()
        self._activity_lock = RLock()
        self._active_generations = 0
        self._last_used_at = 0.0
        self._unload_requested = False

    @property
    def model_label(self) -> str:
        return f"{self.base_model} + LoRA"

    def _begin_activity(self) -> None:
        with self._activity_lock:
            self._active_generations += 1

    def _finish_activity(self) -> None:
        with self._activity_lock:
            self._active_generations = max(0, self._active_generations - 1)
            self._last_used_at = time.time()
        _release_runtime_if_requested(self)

    def _resolve_device_and_dtype(self, torch):
        if self.device_preference == "auto":
            use_cuda = bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)())
            device = "cuda" if use_cuda else "cpu"
        else:
            device = self.device_preference

        if device == "cuda":
            dtype = getattr(torch, "float16", None)
        elif any(
            marker in self.base_model.lower()
            for marker in ("qwen", "dolphin", "8b", "llama3.1-8b", "llama3-1-8b")
        ):
            # Preserve the checkpoint's native half/bfloat precision. Expanding
            # local LLM weights to float32 creates an unsafe peak on Nova's
            # 16 GB CPU host before runtime overhead is included.
            dtype = "auto"
        else:
            dtype = getattr(torch, "float32", None)
        return device, dtype

    def _validate(self):
        if not self.base_model:
            raise ValueError("missing_lora_base_model")
        if not self.adapter_path:
            raise ValueError("missing_lora_adapter_path")
        adapter_dir = Path(self.adapter_path)
        if not adapter_dir.exists():
            raise FileNotFoundError(f"lora_adapter_path_not_found: {adapter_dir}")
        if not (adapter_dir / "adapter_config.json").exists():
            raise FileNotFoundError(f"adapter_config_missing: {adapter_dir / 'adapter_config.json'}")

    def load(self):
        """Load tokenizer, base model, and adapter exactly once across threads."""
        if self.model is not None and self.tokenizer is not None:
            return

        with self._load_lock:
            if self.model is not None and self.tokenizer is not None:
                return
            self._load_unlocked()

    def _load_unlocked(self):
        """Perform the protected model load."""

        self._validate()
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer
        try:
            from transformers.utils import logging as transformers_logging

            transformers_logging.disable_progress_bar()
        except Exception:
            pass

        self.device, torch_dtype = self._resolve_device_and_dtype(torch)
        adapter_dir = Path(self.adapter_path)

        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(adapter_dir),
                trust_remote_code=self.trust_remote_code,
                local_files_only=True,
            )
        except Exception:
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.base_model,
                trust_remote_code=self.trust_remote_code,
                local_files_only=not self.allow_model_downloads,
            )

        model_kwargs = {
            "trust_remote_code": self.trust_remote_code,
            # Qwen's cached checkpoints are sharded and safe to materialize
            # incrementally on CPU. This avoids a second full-size allocation
            # while loading on Nova's 16 GB host.
            "low_cpu_mem_usage": self.device == "cuda"
            or (self.device == "cpu" and "qwen" in self.base_model.lower()),
            "local_files_only": not self.allow_model_downloads,
        }
        if torch_dtype is not None:
            model_kwargs["dtype"] = torch_dtype
        if self.device == "cuda":
            model_kwargs["device_map"] = "auto"

        base = AutoModelForCausalLM.from_pretrained(self.base_model, **model_kwargs)
        model = PeftModel.from_pretrained(base, str(adapter_dir))
        if hasattr(model, "eval"):
            model.eval()
        if self.device not in {"cpu", "cuda"} and hasattr(model, "to"):
            model.to(self.device)
        # Publish the cached model only after the complete load succeeds so a
        # failed attempt can be retried instead of retaining a partial model.
        self.model = model

    def warm_up(self) -> dict:
        """Load the configured local adapter without generating user-visible text."""
        started = time.monotonic()
        self._begin_activity()
        try:
            self.load()
            return {
                "ok": True,
                "provider": DEFAULT_PROVIDER,
                "model": self.model_label,
                "device": self.device,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": DEFAULT_PROVIDER,
                "model": self.model_label,
                "error": str(exc),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            }
        finally:
            self._finish_activity()

    def _format_prompt(self, prompt: str, *, raw_mode: bool = False) -> str:
        prompt = str(prompt or "").strip()
        if not self.tokenizer or not hasattr(self.tokenizer, "apply_chat_template"):
            return prompt
        try:
            messages = [{"role": "user", "content": prompt}]
            if not raw_mode:
                messages.insert(0, {"role": "system", "content": NOVA_LORA_SYSTEM_PROMPT})
            return self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            return prompt

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 256,
        temperature: float = 0.35,
        top_p: float = 0.9,
        raw_mode: bool = False,
    ):
        start = time.time()
        self._begin_activity()
        try:
            self.load()
            import torch

            model_prompt = self._format_prompt(prompt, raw_mode=raw_mode)
            inputs = self.tokenizer(model_prompt, return_tensors="pt")
            inputs = _inputs_to_device(inputs, self.device)
            input_ids = _input_ids_from(inputs)
            input_len = int(getattr(input_ids, "shape", (1, 0))[-1] or 0)

            generate_kwargs = _generate_kwargs_from_inputs(inputs)
            generate_kwargs.update(
                {
                    "max_new_tokens": int(max_new_tokens),
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "do_sample": float(temperature) > 0,
                }
            )
            eos_token_id = getattr(self.tokenizer, "eos_token_id", None)
            pad_token_id = getattr(self.tokenizer, "pad_token_id", None) or eos_token_id
            if eos_token_id is not None:
                generate_kwargs["eos_token_id"] = eos_token_id
            if pad_token_id is not None:
                generate_kwargs["pad_token_id"] = pad_token_id

            with torch.no_grad():
                output_ids = self.model.generate(**generate_kwargs)
            decoded = self.tokenizer.decode(
                _new_tokens(output_ids, input_len),
                skip_special_tokens=True,
            )
            raw = _clean_output(decoded, prompt=model_prompt)
            elapsed = (time.time() - start) * 1000
            return _make_response(
                local_llm_used=bool(raw),
                provider=DEFAULT_PROVIDER,
                model=self.model_label,
                url=f"adapter://{self.adapter_path}",
                prompt=prompt,
                raw_output=raw,
                error=None if raw else "lora_runtime_empty_output",
                fallback_used=not bool(raw),
                fallback_reason="" if raw else "LoRA runtime returned empty output",
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            return _make_response(
                local_llm_used=False,
                provider=DEFAULT_PROVIDER,
                model=self.model_label,
                url=f"adapter://{self.adapter_path}",
                prompt=prompt,
                raw_output="",
                error=str(exc),
                fallback_used=True,
                fallback_reason=f"LoRA runtime unavailable: {exc}",
                response_time_ms=elapsed,
            )
        finally:
            self._finish_activity()

    def generate_stream(
        self,
        prompt: str,
        on_delta: Callable[[str], bool | None],
        is_cancelled: Callable[[], bool] | None = None,
        max_new_tokens: int = 256,
        temperature: float = 0.35,
        top_p: float = 0.9,
        raw_mode: bool = False,
    ):
        """Generate with Hugging Face's iterator streamer and cancellation."""
        start = time.time()
        self._begin_activity()
        raw_parts: list[str] = []
        stop_event = Event()
        generation_errors: list[Exception] = []
        try:
            self.load()
            import torch
            from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

            runtime_cancelled = is_cancelled or (lambda: False)

            class CancellationCriteria(StoppingCriteria):
                def __call__(self, input_ids, scores, **kwargs):
                    return stop_event.is_set() or bool(runtime_cancelled())

            model_prompt = self._format_prompt(prompt, raw_mode=raw_mode)
            inputs = self.tokenizer(model_prompt, return_tensors="pt")
            inputs = _inputs_to_device(inputs, self.device)
            generate_kwargs = _generate_kwargs_from_inputs(inputs)
            streamer = TextIteratorStreamer(
                self.tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
                timeout=0.5,
            )
            generate_kwargs.update(
                {
                    "max_new_tokens": int(max_new_tokens),
                    "temperature": float(temperature),
                    "top_p": float(top_p),
                    "do_sample": float(temperature) > 0,
                    "streamer": streamer,
                    "stopping_criteria": StoppingCriteriaList([CancellationCriteria()]),
                }
            )
            eos_token_id = getattr(self.tokenizer, "eos_token_id", None)
            pad_token_id = getattr(self.tokenizer, "pad_token_id", None) or eos_token_id
            if eos_token_id is not None:
                generate_kwargs["eos_token_id"] = eos_token_id
            if pad_token_id is not None:
                generate_kwargs["pad_token_id"] = pad_token_id

            def run_generation() -> None:
                try:
                    with torch.no_grad():
                        self.model.generate(**generate_kwargs)
                except Exception as exc:
                    generation_errors.append(exc)
                    try:
                        streamer.on_finalized_text("", stream_end=True)
                    except Exception:
                        pass

            worker = Thread(target=run_generation, name="nova-lora-stream", daemon=True)
            worker.start()
            try:
                while worker.is_alive() or not stop_event.is_set():
                    if runtime_cancelled():
                        stop_event.set()
                    try:
                        text = next(streamer)
                    except StopIteration:
                        break
                    except (Empty, TimeoutError):
                        if not worker.is_alive():
                            break
                        continue
                    if text:
                        raw_parts.append(text)
                        if on_delta(text) is False:
                            stop_event.set()
                    if stop_event.is_set() and not worker.is_alive():
                        break
            finally:
                stop_event.set()
                worker.join(timeout=1.0)

            if generation_errors:
                raise generation_errors[0]
            raw = _clean_output("".join(raw_parts), prompt=model_prompt)
            cancelled = bool(runtime_cancelled())
            elapsed = (time.time() - start) * 1000
            return _make_response(
                local_llm_used=bool(raw) and not cancelled,
                provider=DEFAULT_PROVIDER,
                model=self.model_label,
                url=f"adapter://{self.adapter_path}",
                prompt=prompt,
                raw_output=raw,
                error="stream_cancelled" if cancelled else (None if raw else "lora_runtime_empty_output"),
                fallback_used=False,
                fallback_reason="The streaming request was cancelled" if cancelled else ("" if raw else "LoRA runtime returned empty output"),
                response_time_ms=elapsed,
            )
        except Exception as exc:
            stop_event.set()
            elapsed = (time.time() - start) * 1000
            return _make_response(
                local_llm_used=False,
                provider=DEFAULT_PROVIDER,
                model=self.model_label,
                url=f"adapter://{self.adapter_path}",
                prompt=prompt,
                raw_output=_clean_output("".join(raw_parts)),
                error=str(exc),
                fallback_used=True,
                fallback_reason=f"LoRA streaming runtime unavailable: {exc}",
                response_time_ms=elapsed,
            )
        finally:
            self._finish_activity()


def _active_adapter_from_registry():
    try:
        from nova_lora_adapter_registry import resolve_active_lora_adapter

        return resolve_active_lora_adapter()
    except Exception:
        return None


def _adapter_from_registry(adapter_id: str):
    try:
        from nova_lora_adapter_registry import resolve_lora_adapter

        return resolve_lora_adapter(adapter_id)
    except Exception:
        return None


def _dolphin_cpu_guard_reason(base_model: str, *, allow_slow_cpu: bool = False) -> str | None:
    """Avoid freezing the local app by loading Dolphin 8B LoRA on CPU-only machines."""
    model_text = str(base_model or "").lower()
    is_dolphin_8b = (
        "dolphin" in model_text
        or "llama3.1-8b" in model_text
        or "llama3-1-8b" in model_text
    )
    if not is_dolphin_8b:
        return None
    if allow_slow_cpu or str(os.environ.get("NOVA_LORA_ALLOW_DOLPHIN_CPU", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return None
    try:
        import torch

        if bool(torch.cuda.is_available()):
            return None
    except Exception:
        pass
    return (
        "Dolphin 8B LoRA adapter is installed, but this machine has no CUDA GPU. "
        "Nova skipped loading it on CPU so the app does not freeze. "
        "Use Qwen adapter locally, run Dolphin on a GPU machine, or set "
        "NOVA_LORA_ALLOW_DOLPHIN_CPU=true to force the slow CPU path."
    )


def adapter_runtime_availability(base_model: str, adapter_path: str | None = None) -> dict:
    """Report whether an installed adapter is runnable without loading its weights."""
    model = str(base_model or "").strip()
    path = str(adapter_path or "").strip()
    if path and not os.path.exists(path):
        return {
            "runnable": False,
            "state": "unavailable",
            "reason": "The installed adapter path is missing.",
            "model": model,
            "requires_cuda": False,
            "slow_cpu_override_available": False,
        }
    guard_reason = _dolphin_cpu_guard_reason(model)
    if guard_reason:
        return {
            "runnable": False,
            "state": "unavailable",
            "reason": guard_reason,
            "model": model,
            "requires_cuda": True,
            "slow_cpu_override_available": True,
        }
    return {
        "runnable": True,
        "state": "available",
        "reason": None,
        "model": model,
        "requires_cuda": False,
        "slow_cpu_override_available": False,
    }


def get_lora_runtime(
    base_model: str,
    adapter_path: str,
    device: str = "auto",
    allow_model_downloads: bool = False,
) -> NovaLoraRuntime:
    key = (str(base_model), str(adapter_path), str(device or "auto"), bool(allow_model_downloads))
    evicted: list[NovaLoraRuntime] = []
    with _RUNTIME_CACHE_LOCK:
        runtime = _RUNTIME_CACHE.get(key)
        if runtime is None:
            # Keep a single heavyweight runtime cached. Active requests retain
            # their own reference, while idle models are released before a
            # different adapter starts loading.
            for cached_key in list(_RUNTIME_CACHE):
                if cached_key != key:
                    evicted.append(_RUNTIME_CACHE.pop(cached_key))
            runtime = NovaLoraRuntime(
                base_model=base_model,
                adapter_path=adapter_path,
                device=device,
                allow_model_downloads=allow_model_downloads,
            )
            _RUNTIME_CACHE[key] = runtime
    if evicted:
        evicted.clear()
        gc.collect()
        try:
            import torch

            if bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)()):
                torch.cuda.empty_cache()
        except Exception:
            pass
    return runtime


def _release_runtime_if_requested(runtime: NovaLoraRuntime) -> bool:
    """Drop a queued runtime after its current warm-up or generation finishes."""
    with runtime._activity_lock:
        should_release = runtime._unload_requested and runtime._active_generations == 0
    if not should_release:
        return False
    released = False
    with _RUNTIME_CACHE_LOCK:
        for key, cached in list(_RUNTIME_CACHE.items()):
            if cached is runtime:
                _RUNTIME_CACHE.pop(key)
                released = True
    if released:
        with runtime._activity_lock:
            runtime._unload_requested = False
        gc.collect()
        try:
            import torch

            if bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)()):
                torch.cuda.empty_cache()
        except Exception:
            pass
    return released


def runtime_cache_status() -> list[dict]:
    """Return privacy-safe status for cached LoRA runtimes without loading weights."""
    with _RUNTIME_CACHE_LOCK:
        cached = list(_RUNTIME_CACHE.values())
    status = []
    for runtime in cached:
        with runtime._activity_lock:
            active_generations = int(runtime._active_generations)
            last_used_at = float(runtime._last_used_at or 0.0)
            unload_requested = bool(runtime._unload_requested)
        status.append(
            {
                "base_model": runtime.base_model,
                "adapter_name": Path(runtime.adapter_path).name,
                "device": runtime.device,
                "loaded": runtime.model is not None and runtime.tokenizer is not None,
                "active_generations": active_generations,
                "busy": active_generations > 0,
                "unload_requested": unload_requested,
                "last_used_at": last_used_at or None,
            }
        )
    return status


def unload_cached_lora_runtimes(*, force: bool = False, family: str | None = None) -> dict:
    """Release idle cached LoRA runtimes without deleting models or adapters."""
    normalized_family = str(family or "").strip().lower()
    released: list[NovaLoraRuntime] = []
    skipped: list[dict] = []
    with _RUNTIME_CACHE_LOCK:
        for key, runtime in list(_RUNTIME_CACHE.items()):
            family_text = f"{runtime.base_model} {Path(runtime.adapter_path).name}".lower()
            if normalized_family and normalized_family not in family_text:
                continue
            with runtime._activity_lock:
                busy = runtime._active_generations > 0
            if busy and not force:
                with runtime._activity_lock:
                    runtime._unload_requested = True
                skipped.append(
                    {
                        "base_model": runtime.base_model,
                        "adapter_name": Path(runtime.adapter_path).name,
                        "reason": "generation_in_progress_unload_queued",
                    }
                )
                continue
            released.append(_RUNTIME_CACHE.pop(key))

    unloaded = [
        {
            "base_model": runtime.base_model,
            "adapter_name": Path(runtime.adapter_path).name,
        }
        for runtime in released
    ]
    released.clear()
    gc.collect()
    try:
        import torch

        if bool(getattr(getattr(torch, "cuda", None), "is_available", lambda: False)()):
            torch.cuda.empty_cache()
    except Exception:
        pass
    return {"ok": not skipped, "unloaded": unloaded, "skipped": skipped}


def warm_up_lora(config=None) -> dict:
    """Preload Nova's configured adapter while keeping downloads opt-in."""
    if config is None:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
    if not bool(getattr(config, "lora_runtime_enabled", False)) or not bool(
        getattr(config, "lora_adapter_enabled", False)
    ):
        return {"ok": False, "state": "disabled", "reason": "LoRA runtime is disabled"}

    adapter_path = str(getattr(config, "lora_adapter_path", "") or "")
    base_model = str(getattr(config, "lora_base_model", "") or "")
    if not adapter_path or not base_model:
        active = _active_adapter_from_registry()
        if active:
            adapter_path = adapter_path or str(active.get("path", "") or "")
            base_model = base_model or str(active.get("base_model", "") or "")
    if not adapter_path:
        return {"ok": False, "state": "unavailable", "reason": "No active LoRA adapter path is configured"}
    if not base_model:
        base_model = "Qwen/Qwen2.5-1.5B-Instruct"
    dolphin_guard = _dolphin_cpu_guard_reason(base_model)
    if dolphin_guard:
        return {"ok": False, "state": "unavailable", "reason": dolphin_guard, "model": base_model}

    runtime = get_lora_runtime(
        base_model=base_model,
        adapter_path=adapter_path,
        device=str(getattr(config, "lora_device", "auto") or "auto"),
        allow_model_downloads=bool(getattr(config, "allow_model_downloads", False)),
    )
    result = runtime.warm_up()
    result["state"] = "ready" if result.get("ok") else "failed"
    return result


def generate_with_lora(
    prompt: str,
    config=None,
    max_new_tokens: Optional[int] = None,
    temperature: float = 0.35,
    top_p: float = 0.9,
    adapter_id: str | None = None,
    adapter_path: str | None = None,
    base_model: str | None = None,
    allow_slow_cpu: bool = False,
    raw_mode: bool = False,
):
    """Generate with the active LoRA adapter, or return a fallback response."""
    if config is None:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()

    runtime_enabled = bool(getattr(config, "lora_runtime_enabled", False))
    adapter_enabled = bool(getattr(config, "lora_adapter_enabled", False))
    if not runtime_enabled or not adapter_enabled:
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=str(getattr(config, "lora_base_model", "") or ""),
            prompt=prompt,
            fallback_used=True,
            fallback_reason="LoRA runtime disabled",
        )

    adapter_path = str(adapter_path or getattr(config, "lora_adapter_path", "") or "")
    base_model = str(base_model or getattr(config, "lora_base_model", "") or "")
    adapter_id = str(adapter_id or "").strip()
    if adapter_id:
        selected = _adapter_from_registry(adapter_id)
        if selected:
            adapter_path = str(selected.get("path", "") or adapter_path)
            base_model = str(selected.get("base_model", "") or base_model)
    if not adapter_path or not base_model:
        active = _active_adapter_from_registry()
        if active:
            adapter_path = adapter_path or str(active.get("path", "") or "")
            base_model = base_model or str(active.get("base_model", "") or "")

    if not adapter_path:
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=f"{base_model} + LoRA" if base_model else "",
            prompt=prompt,
            fallback_used=True,
            fallback_reason="No active LoRA adapter path configured",
        )

    if not base_model:
        base_model = "Qwen/Qwen2.5-1.5B-Instruct"

    dolphin_guard = _dolphin_cpu_guard_reason(base_model, allow_slow_cpu=allow_slow_cpu)
    if dolphin_guard:
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=f"{base_model} + LoRA",
            prompt=prompt,
            fallback_used=True,
            fallback_reason=dolphin_guard,
            error=dolphin_guard,
        )

    device = str(getattr(config, "lora_device", "auto") or "auto")
    token_limit = int(max_new_tokens or getattr(config, "lora_max_new_tokens", 256) or 256)
    runtime = get_lora_runtime(
        base_model=base_model,
        adapter_path=adapter_path,
        device=device,
        allow_model_downloads=bool(getattr(config, "allow_model_downloads", False)),
    )
    return runtime.generate(
        prompt,
        max_new_tokens=token_limit,
        temperature=temperature,
        top_p=top_p,
        raw_mode=raw_mode,
    )


def generate_with_lora_stream(
    prompt: str,
    on_delta: Callable[[str], bool | None],
    is_cancelled: Callable[[], bool] | None = None,
    config=None,
    max_new_tokens: Optional[int] = None,
    temperature: float = 0.35,
    top_p: float = 0.9,
    adapter_id: str | None = None,
    adapter_path: str | None = None,
    base_model: str | None = None,
    allow_slow_cpu: bool = False,
    raw_mode: bool = False,
):
    """Stream with the selected LoRA adapter without changing Nova routing."""
    if config is None:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()

    if not bool(getattr(config, "lora_runtime_enabled", False)) or not bool(
        getattr(config, "lora_adapter_enabled", False)
    ):
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=str(getattr(config, "lora_base_model", "") or ""),
            prompt=prompt,
            fallback_used=True,
            fallback_reason="LoRA runtime disabled",
        )

    adapter_path = str(adapter_path or getattr(config, "lora_adapter_path", "") or "")
    base_model = str(base_model or getattr(config, "lora_base_model", "") or "")
    adapter_id = str(adapter_id or "").strip()
    if adapter_id:
        selected = _adapter_from_registry(adapter_id)
        if selected:
            adapter_path = str(selected.get("path", "") or adapter_path)
            base_model = str(selected.get("base_model", "") or base_model)
    if not adapter_path or not base_model:
        active = _active_adapter_from_registry()
        if active:
            adapter_path = adapter_path or str(active.get("path", "") or "")
            base_model = base_model or str(active.get("base_model", "") or "")

    if not adapter_path:
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=f"{base_model} + LoRA" if base_model else "",
            prompt=prompt,
            fallback_used=True,
            fallback_reason="No active LoRA adapter path configured",
        )
    if not base_model:
        base_model = "Qwen/Qwen2.5-1.5B-Instruct"

    dolphin_guard = _dolphin_cpu_guard_reason(base_model, allow_slow_cpu=allow_slow_cpu)
    if dolphin_guard:
        return _make_response(
            local_llm_used=False,
            provider=DEFAULT_PROVIDER,
            model=f"{base_model} + LoRA",
            prompt=prompt,
            fallback_used=True,
            fallback_reason=dolphin_guard,
            error=dolphin_guard,
        )

    runtime = get_lora_runtime(
        base_model=base_model,
        adapter_path=adapter_path,
        device=str(getattr(config, "lora_device", "auto") or "auto"),
        allow_model_downloads=bool(getattr(config, "allow_model_downloads", False)),
    )
    return runtime.generate_stream(
        prompt,
        on_delta=on_delta,
        is_cancelled=is_cancelled,
        max_new_tokens=int(max_new_tokens or getattr(config, "lora_max_new_tokens", 256) or 256),
        temperature=temperature,
        top_p=top_p,
        raw_mode=raw_mode,
    )
