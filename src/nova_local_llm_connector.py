"""
Nova Local LLM Cortex Connector
=================================
Connects Nova to a downloaded local LLM (Ollama, LM Studio) while keeping Nova's
own brain system (memory, dictionary, routing, role transformers, critic) in control.

Architecture:
  User message
  → Nova normalizer
  → Nova dictionary / meaning expansion
  → Nova memory lookup
  → Nova 7-role transformer route voting
  → Nova route selector → decides if local LLM should be called
  → Nova builds task-specific prompt
  → local LLM generates fluent answer
  → Nova critic checks answer
  → Nova final speech output
  → Nova saves training log
"""

import json, os, time, sys, re
from contextlib import nullcontext
from pathlib import Path
from datetime import datetime
from typing import Optional, Any, Callable

# Try httpx first, then urllib (httpx is more modern)
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_DOLPHIN_LOCAL_LLM_MODEL = "dolphin3"
DEFAULT_QWEN_LOCAL_LLM_MODEL = "qwen2.5:1.5b"
DEFAULT_FAST_LOCAL_LLM_MODEL = DEFAULT_QWEN_LOCAL_LLM_MODEL
DEFAULT_DEEP_LOCAL_LLM_MODEL = DEFAULT_QWEN_LOCAL_LLM_MODEL
DEFAULT_DIRECT_DEEPSEEK_MODEL = DEFAULT_DOLPHIN_LOCAL_LLM_MODEL
DEFAULT_LOCAL_LLM_MODEL = DEFAULT_QWEN_LOCAL_LLM_MODEL
DEFAULT_LOCAL_LLM_CONTEXT = 8192
QWEN_FULL_LORA_ADAPTER_ID = "nova-qwen2-5-1-5b-focused-repair-20260723"
DOLPHIN_FULL_LORA_ADAPTER_ID = "nova-dolphin3-llama3-1-8b-full-sft-20260712"
SMART_LORA_AUTO_MODES = {"smart", "smart_adapter", "adaptive", "adaptive_adapter", "qwen_dolphin"}
QWEN_FIRST_LORA_AUTO_MODES = {"qwen_first", "qwen-first", "regular_qwen", "regular-qwen"}
OLLAMA_QWEN_FIRST_AUTO_MODES = {
    "ollama_qwen_first",
    "ollama-qwen-first",
    "qwen_ollama_first",
    "qwen-ollama-first",
}


def clean_local_llm_output(raw: str) -> str:
    """Remove complete or interrupted reasoning blocks before Nova uses output."""

    text = str(raw or "").strip()
    text = re.sub(r"(?is)<think\b[^>]*>.*?</think\s*>", "", text)
    # A cancelled or token-limited response may contain an opening tag without
    # its close.  Nothing after that opening tag is safe visible content.
    text = re.sub(r"(?is)<think\b[^>]*>.*$", "", text)
    text = re.sub(r"(?is)</?think\b[^>]*>", "", text)
    return text.strip()


def qwen_reasoning_directive(
    model_id: str,
    *,
    reasoning_enabled: bool | None = None,
    reasoning_mode: str = "fast",
) -> str:
    """Return Qwen3's documented prompt directive for this Nova turn."""

    if "qwen3" not in str(model_id or "").lower():
        return ""
    mode = str(reasoning_mode or "fast").strip().lower()
    enabled = bool(reasoning_enabled) if reasoning_enabled is not None else mode in {
        "deep", "agent", "verify",
    }
    return "/think" if enabled else "/no_think"


def apply_qwen_reasoning_control(
    prompt: str,
    model_id: str,
    context: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Apply provider-specific syntax while returning provider-neutral metadata."""

    context = context if isinstance(context, dict) else {}
    mode = str(context.get("reasoning_mode") or "fast").strip().lower()
    requested = context.get("reasoning_enabled")
    directive = qwen_reasoning_directive(
        model_id,
        reasoning_enabled=requested if isinstance(requested, bool) else None,
        reasoning_mode=mode,
    )
    controlled = str(prompt or "")
    if directive and not controlled.lstrip().startswith(("/think", "/no_think")):
        controlled = directive + "\n" + controlled
    return controlled, {
        "reasoning_mode": mode,
        "reasoning_enabled": directive == "/think",
        "reasoning_budget": context.get("reasoning_budget"),
        "provider_directive": directive or None,
        "reasoning_content_stored": False,
    }


class _VisibleReasoningFilter:
    """Incrementally publish only text outside Qwen reasoning tags."""

    _OPEN = "<think>"
    _CLOSE = "</think>"

    def __init__(self, publish: Callable[[str], bool | None]) -> None:
        self.publish = publish
        self.buffer = ""
        self.in_reasoning = False

    @staticmethod
    def _tag_prefix_suffix(value: str, tag: str) -> int:
        maximum = min(len(value), len(tag) - 1)
        for size in range(maximum, 0, -1):
            if value[-size:].lower() == tag[:size]:
                return size
        return 0

    def feed(self, chunk: str) -> bool:
        self.buffer += str(chunk or "")
        while self.buffer:
            if self.in_reasoning:
                index = self.buffer.lower().find(self._CLOSE)
                if index < 0:
                    keep = self._tag_prefix_suffix(self.buffer, self._CLOSE)
                    self.buffer = self.buffer[-keep:] if keep else ""
                    return True
                self.buffer = self.buffer[index + len(self._CLOSE) :]
                self.in_reasoning = False
                continue
            index = self.buffer.lower().find(self._OPEN)
            if index < 0:
                keep = self._tag_prefix_suffix(self.buffer, self._OPEN)
                visible = self.buffer[:-keep] if keep else self.buffer
                self.buffer = self.buffer[-keep:] if keep else ""
                return self.publish(visible) is not False if visible else True
            visible = self.buffer[:index]
            self.buffer = self.buffer[index + len(self._OPEN) :]
            if visible and self.publish(visible) is False:
                return False
            self.in_reasoning = True
        return True

    def finish(self) -> bool:
        if self.in_reasoning:
            self.buffer = ""
            return True
        visible = self.buffer
        self.buffer = ""
        return self.publish(visible) is not False if visible else True

# ─── Config ──────────────────────────────────────────────────
class LocalLLMConfig:
    """Configuration for local LLM connection."""
    
    DEFAULT_CONFIG = {
        "NOVA_USE_LOCAL_LLM": False,
        "NOVA_LOCAL_LLM_PROVIDER": "ollama",
        "NOVA_LOCAL_LLM_MODEL": DEFAULT_LOCAL_LLM_MODEL,
        "NOVA_FAST_LOCAL_LLM_MODEL": DEFAULT_FAST_LOCAL_LLM_MODEL,
        "NOVA_DEEP_LOCAL_LLM_MODEL": DEFAULT_DEEP_LOCAL_LLM_MODEL,
        "NOVA_OPTIONAL_STRONG_MODEL": "qwen3:8b",
        "NOVA_OPTIONAL_STRONG_TIMEOUT": 240,
        "NOVA_OPTIONAL_STRONG_KEEP_ALIVE": "5m",
        "NOVA_ACTIVE_BRAIN": DEFAULT_DEEP_LOCAL_LLM_MODEL,
        "NOVA_DIRECT_DEEPSEEK_MODEL": DEFAULT_DIRECT_DEEPSEEK_MODEL,
        "NOVA_DIRECT_DEEPSEEK_TIMEOUT": 180,
        "NOVA_LOCAL_LLM_URL": "http://127.0.0.1:11434/api/generate",
        "NOVA_LOCAL_LLM_TIMEOUT": 120,
        "NOVA_LOCAL_LLM_CONTEXT": DEFAULT_LOCAL_LLM_CONTEXT,
        "NOVA_LOCAL_LLM_FALLBACK": True,
        "NOVA_LOG_LOCAL_LLM_PROMPTS": False,
        "NOVA_REASONING_DEFAULT_MODE": "fast",
        "NOVA_REASONING_ALLOW_DEEP": True,
        "NOVA_REASONING_ALLOW_AGENT": True,
        "NOVA_REASONING_MAX_TOOL_STEPS": 4,
        "NOVA_HIDE_REASONING_CONTENT": True,
        "NOVA_MODEL_PROVIDER": "existing",
        "NOVA_MODEL_PROVIDER_BASE_URL": "http://127.0.0.1:8000",
        "NOVA_MODEL_PROVIDER_MODEL": "",
        "NOVA_MODEL_PROVIDER_CONTEXT": 8192,
        "NOVA_MODEL_PROVIDER_TIMEOUT": 120,
        "NOVA_ALLOW_REMOTE_MODEL_PROVIDER": False,
        "NOVA_MEMORY_V2_ENABLED": True,
        "NOVA_MEMORY_V2_DATABASE": "data/nova_memory.db",
        "NOVA_MEMORY_AUTOMATIC_WRITES": "selective",
        "NOVA_RAG_ENABLED": True,
        "NOVA_RAG_DATABASE": "data/nova_knowledge.db",
        "NOVA_RAG_TOP_K": 6,
        "NOVA_TOOLS_ENABLED": True,
        "NOVA_VERIFICATION_ENABLED": True,
        "NOVA_VERIFICATION_MODE": "risk_based",
        "NOVA_TELEMETRY_ENABLED": False,
        "NOVA_LOG_PRIVATE_MEMORY": False,
        "NOVA_NATURAL_CHAT": True,
        "NOVA_ULTRA_THINK": True,
        "NOVA_AGENT_MODE": True,
        "NOVA_AGENT_MAX_STEPS": 6,
        "NOVA_AGENT_REQUIRE_APPROVAL": True,
        "NOVA_AGENT_ALLOW_SHELL": False,
        "NOVA_AGENT_ALLOW_FILE_WRITE": False,
        "NOVA_AGENT_ALLOW_WEB": False,
        "NOVA_AGENT_TRACE": True,
        "NOVA_LORA_ADAPTER_ENABLED": True,
        "NOVA_LORA_ADAPTER_PATH": "",
        "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
        "NOVA_LORA_RUNTIME_ENABLED": True,
        "NOVA_LORA_DEVICE": "auto",
        "NOVA_LORA_MAX_NEW_TOKENS": 256,
        "NOVA_LORA_AUTO_MODE": "ollama_qwen_first",
        "NOVA_REGULAR_CHAT_ESCALATION_ENABLED": True,
        "NOVA_MIDDLE_REVIEWER_ENABLED": True,
        "NOVA_DIRECT_MIDDLE_ENABLED": True,
        "NOVA_DIRECT_MIDDLE_THRESHOLD": "0.84",
        "NOVA_DIRECT_MIDDLE_MAX_TOKENS": 256,
        "NOVA_MIDDLE_REVIEWER_MIN_MODEL_BYTES": 1_500_000_000,
        "NOVA_MIDDLE_REVIEWER_MAX_MODEL_BYTES": 3_000_000_000,
        "NOVA_MIDDLE_REVIEWER_WARMUP_MIN_AVAILABLE_GB": 5,
        "NOVA_MIDDLE_REVIEWER_GENERAL_MODELS": "qwen2.5:3b,qwen2.5-coder:3b,phi3:mini,gemma2:2b",
        "NOVA_MIDDLE_REVIEWER_REASONING_MODELS": "qwen2.5:3b,qwen2.5-coder:3b,phi3:mini",
        "NOVA_MIDDLE_REVIEWER_CODING_MODELS": "qwen2.5-coder:3b,qwen2.5:3b,phi3:mini",
        "NOVA_ESCALATION_MIN_MODEL_BYTES": 3_000_000_000,
        "NOVA_ESCALATION_MAX_MODEL_BYTES": 8_000_000_000,
        "NOVA_ESCALATION_TIMEOUT_SECONDS": 180,
        "NOVA_ESCALATION_GENERAL_MODELS": "nova-dolphin3-lora,dolphin3,deepseek-r1:7b,qwen2.5-coder:7b",
        "NOVA_ESCALATION_REASONING_MODELS": "qwen2.5-coder:7b,deepseek-r1:7b,nova-dolphin3-lora,dolphin3",
        "NOVA_ESCALATION_CODING_MODELS": "qwen2.5-coder:7b,deepseek-r1:7b,nova-dolphin3-lora,dolphin3",
        "NOVA_ALLOW_MODEL_DOWNLOADS": False,
        "NOVA_MODEL_WARMUP": True,
        "NOVA_MODEL_WARMUP_DELAY_SECONDS": 3,
        "NOVA_MODEL_WARMUP_TIMEOUT": 180,
        "NOVA_OLLAMA_KEEP_ALIVE": "30m",
        "NOVA_REVIEWER_WARMUP": True,
        "NOVA_REVIEWER_WARMUP_TASK": "reasoning",
        "NOVA_REVIEWER_WARMUP_MIN_AVAILABLE_GB": 8,
        "NOVA_REVIEWER_KEEP_ALIVE": "10m",
        "NOVA_FAST_PLANNER": True,
    }
    
    def __init__(self):
        self.config = dict(self.DEFAULT_CONFIG)
        self._load_from_file()
        # Explicit process environment is the final override. This lets
        # launchers and tests change providers without editing checked-in files.
        self._load_from_env()
    
    def _load_from_env(self):
        """Load config from environment variables."""
        for key in self.DEFAULT_CONFIG:
            env_val = os.environ.get(key)
            if env_val is not None:
                if env_val.lower() in ("true", "1", "yes"):
                    self.config[key] = True
                elif env_val.lower() in ("false", "0", "no"):
                    self.config[key] = False
                else:
                    try:
                        self.config[key] = int(env_val)
                    except ValueError:
                        self.config[key] = env_val
    
    def _load_from_file(self):
        """Load portable defaults, then optional machine-local overrides."""
        portable_path = ROOT / "nova_llm_config.json"
        if portable_path.exists():
            try:
                with open(portable_path, encoding="utf-8") as f:
                    portable_config = json.load(f)
                if isinstance(portable_config, dict):
                    for key, value in portable_config.items():
                        if key in self.DEFAULT_CONFIG:
                            self.config[key] = value
            except (OSError, ValueError, TypeError):
                pass

        config_paths = [
            ROOT / ".nova_llm_config",
            ROOT / ".env",
        ]
        for path in config_paths:
            if path.exists():
                try:
                    with open(path) as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                key, val = line.split("=", 1)
                                key = key.strip()
                                val = val.strip().strip("\"'")
                                if key in self.DEFAULT_CONFIG:
                                    if val.lower() in ("true", "1", "yes"):
                                        self.config[key] = True
                                    elif val.lower() in ("false", "0", "no"):
                                        self.config[key] = False
                                    else:
                                        try:
                                            self.config[key] = int(val)
                                        except ValueError:
                                            self.config[key] = val
                except Exception:
                    pass  # Silent fail on config load
    
    @property
    def use_local_llm(self) -> bool:
        return self.config.get("NOVA_USE_LOCAL_LLM", False)
    
    @property
    def provider(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_PROVIDER", "ollama")
    
    @property
    def model(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_MODEL", DEFAULT_LOCAL_LLM_MODEL)

    @property
    def fast_model(self) -> str:
        return self.config.get("NOVA_FAST_LOCAL_LLM_MODEL", DEFAULT_FAST_LOCAL_LLM_MODEL)

    @property
    def deep_model(self) -> str:
        return self.config.get("NOVA_DEEP_LOCAL_LLM_MODEL", DEFAULT_DEEP_LOCAL_LLM_MODEL)

    @property
    def optional_strong_model(self) -> str:
        return str(self.config.get("NOVA_OPTIONAL_STRONG_MODEL", "qwen3:8b") or "qwen3:8b")

    @property
    def optional_strong_timeout(self) -> int:
        return max(30, min(int(self.config.get("NOVA_OPTIONAL_STRONG_TIMEOUT", 240) or 240), 600))

    @property
    def optional_strong_keep_alive(self) -> str:
        return str(self.config.get("NOVA_OPTIONAL_STRONG_KEEP_ALIVE", "5m") or "5m")

    @property
    def active_brain(self) -> str:
        return str(self.config.get("NOVA_ACTIVE_BRAIN", self.deep_model) or self.deep_model)

    @property
    def direct_deepseek_model(self) -> str:
        return self.config.get("NOVA_DIRECT_DEEPSEEK_MODEL", DEFAULT_DIRECT_DEEPSEEK_MODEL)

    @property
    def direct_deepseek_timeout(self) -> int:
        return int(self.config.get("NOVA_DIRECT_DEEPSEEK_TIMEOUT", 180))

    @property
    def context_window(self) -> int:
        return int(self.config.get("NOVA_LOCAL_LLM_CONTEXT", DEFAULT_LOCAL_LLM_CONTEXT))
    
    @property
    def url(self) -> str:
        return self.config.get("NOVA_LOCAL_LLM_URL", "http://127.0.0.1:11434/api/generate")
    
    @property
    def timeout(self) -> int:
        return int(self.config.get("NOVA_LOCAL_LLM_TIMEOUT", 30))
    
    @property
    def fallback(self) -> bool:
        return self.config.get("NOVA_LOCAL_LLM_FALLBACK", True)
    
    @property
    def log_prompts(self) -> bool:
        return self.config.get("NOVA_LOG_LOCAL_LLM_PROMPTS", False)

    @property
    def reasoning_default_mode(self) -> str:
        value = str(self.config.get("NOVA_REASONING_DEFAULT_MODE", "fast") or "fast").lower()
        return value if value in {"fast", "deep", "agent", "verify"} else "fast"

    @property
    def reasoning_max_tool_steps(self) -> int:
        return max(0, min(int(self.config.get("NOVA_REASONING_MAX_TOOL_STEPS", 4) or 4), 12))

    @property
    def reasoning_allow_deep(self) -> bool:
        return bool(self.config.get("NOVA_REASONING_ALLOW_DEEP", True))

    @property
    def reasoning_allow_agent(self) -> bool:
        return bool(self.config.get("NOVA_REASONING_ALLOW_AGENT", True))

    @property
    def hide_reasoning_content(self) -> bool:
        return bool(self.config.get("NOVA_HIDE_REASONING_CONTENT", True))

    @property
    def memory_v2_enabled(self) -> bool:
        return bool(self.config.get("NOVA_MEMORY_V2_ENABLED", True))

    @property
    def memory_automatic_writes(self) -> str:
        return str(
            self.config.get("NOVA_MEMORY_AUTOMATIC_WRITES", "selective")
            or "selective"
        ).strip().lower()

    @property
    def rag_enabled(self) -> bool:
        return bool(self.config.get("NOVA_RAG_ENABLED", True))

    @property
    def rag_top_k(self) -> int:
        return max(1, min(int(self.config.get("NOVA_RAG_TOP_K", 6) or 6), 20))

    @property
    def tools_enabled(self) -> bool:
        return bool(self.config.get("NOVA_TOOLS_ENABLED", True))

    @property
    def verification_enabled(self) -> bool:
        return bool(self.config.get("NOVA_VERIFICATION_ENABLED", True))

    @property
    def verification_mode(self) -> str:
        return str(
            self.config.get("NOVA_VERIFICATION_MODE", "risk_based")
            or "risk_based"
        ).strip().lower()

    @property
    def lora_adapter_enabled(self) -> bool:
        return bool(self.config.get("NOVA_LORA_ADAPTER_ENABLED", True))

    @property
    def lora_adapter_path(self) -> str:
        return str(self.config.get("NOVA_LORA_ADAPTER_PATH", "") or "")

    @property
    def lora_base_model(self) -> str:
        return str(self.config.get("NOVA_LORA_BASE_MODEL", "Qwen/Qwen2.5-1.5B-Instruct") or "")

    @property
    def lora_runtime_enabled(self) -> bool:
        return bool(self.config.get("NOVA_LORA_RUNTIME_ENABLED", True))

    @property
    def lora_device(self) -> str:
        return str(self.config.get("NOVA_LORA_DEVICE", "auto") or "auto")

    @property
    def lora_max_new_tokens(self) -> int:
        return int(self.config.get("NOVA_LORA_MAX_NEW_TOKENS", 256) or 256)

    @property
    def lora_auto_mode(self) -> str:
        return str(
            self.config.get("NOVA_LORA_AUTO_MODE", "ollama_qwen_first")
            or "ollama_qwen_first"
        ).lower()

    @property
    def regular_chat_escalation_enabled(self) -> bool:
        return bool(self.config.get("NOVA_REGULAR_CHAT_ESCALATION_ENABLED", True))

    @property
    def middle_reviewer_enabled(self) -> bool:
        return bool(self.config.get("NOVA_MIDDLE_REVIEWER_ENABLED", True))

    @property
    def direct_middle_enabled(self) -> bool:
        return bool(self.config.get("NOVA_DIRECT_MIDDLE_ENABLED", True))

    @property
    def direct_middle_threshold(self) -> float:
        try:
            value = float(self.config.get("NOVA_DIRECT_MIDDLE_THRESHOLD", 0.84) or 0.84)
        except (TypeError, ValueError):
            value = 0.84
        return max(0.68, min(value, 0.98))

    @property
    def direct_middle_max_tokens(self) -> int:
        value = int(self.config.get("NOVA_DIRECT_MIDDLE_MAX_TOKENS", 256) or 256)
        return max(128, min(value, 512))

    @property
    def middle_reviewer_min_model_bytes(self) -> int:
        value = int(self.config.get("NOVA_MIDDLE_REVIEWER_MIN_MODEL_BYTES", 1_500_000_000) or 0)
        return max(256_000_000, min(value, 16_000_000_000))

    @property
    def middle_reviewer_max_model_bytes(self) -> int:
        value = int(self.config.get("NOVA_MIDDLE_REVIEWER_MAX_MODEL_BYTES", 3_000_000_000) or 0)
        return max(self.middle_reviewer_min_model_bytes, min(value, 16_000_000_000))

    @property
    def middle_reviewer_warmup_min_available_gb(self) -> float:
        try:
            value = float(self.config.get("NOVA_MIDDLE_REVIEWER_WARMUP_MIN_AVAILABLE_GB", 5) or 5)
        except (TypeError, ValueError):
            value = 5.0
        return max(2.0, min(value, 128.0))

    def middle_reviewer_model_preferences(self, task_type: str = "general") -> tuple[str, ...]:
        key = {
            "coding": "NOVA_MIDDLE_REVIEWER_CODING_MODELS",
            "reasoning": "NOVA_MIDDLE_REVIEWER_REASONING_MODELS",
        }.get(str(task_type or "").lower(), "NOVA_MIDDLE_REVIEWER_GENERAL_MODELS")
        raw = str(self.config.get(key, "") or "")
        return tuple(item.strip() for item in raw.split(",") if item.strip())

    @property
    def escalation_min_model_bytes(self) -> int:
        value = int(self.config.get("NOVA_ESCALATION_MIN_MODEL_BYTES", 3_000_000_000) or 0)
        return max(0, min(value, 64_000_000_000))

    @property
    def escalation_max_model_bytes(self) -> int:
        value = int(self.config.get("NOVA_ESCALATION_MAX_MODEL_BYTES", 8_000_000_000) or 0)
        return max(256_000_000, min(value, 64_000_000_000))

    @property
    def escalation_timeout_seconds(self) -> int:
        value = int(self.config.get("NOVA_ESCALATION_TIMEOUT_SECONDS", 180) or 180)
        return max(5, min(value, 600))

    def escalation_model_preferences(self, task_type: str = "general") -> tuple[str, ...]:
        key = {
            "coding": "NOVA_ESCALATION_CODING_MODELS",
            "reasoning": "NOVA_ESCALATION_REASONING_MODELS",
        }.get(str(task_type or "").lower(), "NOVA_ESCALATION_GENERAL_MODELS")
        raw = str(self.config.get(key, "") or "")
        return tuple(item.strip() for item in raw.split(",") if item.strip())

    @property
    def allow_model_downloads(self) -> bool:
        """Model downloads require an explicit opt-in; cached/local models remain usable."""
        return bool(self.config.get("NOVA_ALLOW_MODEL_DOWNLOADS", False))

    @property
    def model_warmup(self) -> bool:
        return bool(self.config.get("NOVA_MODEL_WARMUP", True))

    @property
    def model_warmup_timeout(self) -> int:
        return max(1, int(self.config.get("NOVA_MODEL_WARMUP_TIMEOUT", 180) or 180))

    @property
    def model_warmup_delay_seconds(self) -> int:
        return max(0, min(30, int(self.config.get("NOVA_MODEL_WARMUP_DELAY_SECONDS", 3) or 0)))

    @property
    def ollama_keep_alive(self) -> str:
        return str(self.config.get("NOVA_OLLAMA_KEEP_ALIVE", "30m") or "30m")

    @property
    def reviewer_warmup(self) -> bool:
        return bool(self.config.get("NOVA_REVIEWER_WARMUP", True))

    @property
    def reviewer_warmup_task(self) -> str:
        value = str(self.config.get("NOVA_REVIEWER_WARMUP_TASK", "reasoning") or "reasoning").strip().lower()
        return value if value in {"general", "reasoning", "coding"} else "reasoning"

    @property
    def reviewer_warmup_min_available_gb(self) -> float:
        try:
            value = float(self.config.get("NOVA_REVIEWER_WARMUP_MIN_AVAILABLE_GB", 8) or 8)
        except (TypeError, ValueError):
            value = 8.0
        return max(2.0, min(value, 128.0))

    @property
    def reviewer_keep_alive(self) -> str:
        return str(self.config.get("NOVA_REVIEWER_KEEP_ALIVE", "10m") or "10m")

    @property
    def fast_planner(self) -> bool:
        return bool(self.config.get("NOVA_FAST_PLANNER", True))


# ─── LLM Response Object ────────────────────────────────────
class LocalLLMResponse:
    """Structured response from a local LLM call."""
    
    def __init__(self, 
                 local_llm_used: bool = False,
                 provider: str = "",
                 model: str = "",
                 url: str = "",
                 prompt: str = "",
                 raw_output: str = "",
                 error: Optional[str] = None,
                 fallback_used: bool = False,
                 fallback_reason: str = "",
                 response_time_ms: float = 0.0,
                 finish_reason: str = ""):
        self.local_llm_used = local_llm_used
        self.provider = provider
        self.model = model
        self.url = url
        self.prompt = prompt
        self.raw_output = raw_output
        self.error = error
        self.fallback_used = fallback_used
        self.fallback_reason = fallback_reason
        self.response_time_ms = response_time_ms
        self.finish_reason = str(finish_reason or "")
    
    def to_dict(self) -> dict:
        return {
            "local_llm_used": self.local_llm_used,
            "provider": self.provider,
            "model": self.model,
            "url": self.url,
            "prompt": self.prompt[:500] if self.prompt else "",  # Truncate for logs
            "raw_output": self.raw_output[:500] if self.raw_output else "",
            "error": self.error,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "response_time_ms": self.response_time_ms,
            "finish_reason": self.finish_reason,
        }
    
    def __repr__(self) -> str:
        status = "✓ LLM" if self.local_llm_used else "✗ Fallback"
        return f"<LocalLLMResponse {status} {self.provider}/{self.model} ({self.response_time_ms:.0f}ms)>"


# ─── Local LLM Connector ────────────────────────────────────
class LocalLLMConnector:
    """Connects to local LLM runtimes (Ollama, LM Studio)."""
    
    def __init__(self, config: Optional[LocalLLMConfig] = None):
        self.config = config or LocalLLMConfig()
        self._log_file = ROOT / "nova_training_logs" / "local_llm_calls.jsonl"
        os.makedirs(self._log_file.parent, exist_ok=True)
    
    def is_available(self) -> bool:
        """Check if local LLM is configured and reachable."""
        if not self.config.use_local_llm:
            return False
        try:
            if HAS_HTTPX:
                resp = httpx.get(
                    self.config.url.rsplit("/api", 1)[0] if "/api" in self.config.url else self.config.url,
                    timeout=2.0
                )
                return resp.status_code < 500
            else:
                import urllib.request
                base_url = self.config.url.rsplit("/api", 1)[0] if "/api" in self.config.url else self.config.url
                req = urllib.request.Request(base_url, method="HEAD")
                urllib.request.urlopen(req, timeout=2)
                return True
        except Exception:
            return False

    def warm_up(self) -> dict:
        """Load the preferred local model without generating a visible answer."""
        if not self.config.use_local_llm:
            return {"ok": False, "state": "disabled", "reason": "Local LLM use is disabled"}
        if not self.config.model_warmup:
            return {"ok": False, "state": "disabled", "reason": "Model warm-up is disabled"}

        lora_result = None
        if (
            self.config.lora_runtime_enabled
            and self.config.lora_adapter_enabled
            and self.config.lora_auto_mode not in OLLAMA_QWEN_FIRST_AUTO_MODES
        ):
            try:
                import nova_lora_runtime

                lora_result = nova_lora_runtime.warm_up_lora(self.config)
                if lora_result.get("ok"):
                    return lora_result
            except Exception as exc:
                lora_result = {"ok": False, "state": "failed", "error": str(exc)}

        if self.config.provider != "ollama":
            return lora_result or {
                "ok": False,
                "state": "unsupported",
                "reason": f"Warm-up is not implemented for provider {self.config.provider!r}",
            }

        import urllib.request

        url = self.config.url if self.config.url.startswith("http") else f"http://{self.config.url}"
        payload = {
            "model": self.config.model,
            "prompt": "",
            "stream": False,
            "keep_alive": self.config.ollama_keep_alive,
            "options": {"num_predict": 0},
        }
        started = time.monotonic()
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.config.model_warmup_timeout) as response:
                response.read()
            return {
                "ok": True,
                "state": "ready",
                "provider": "ollama",
                "model": self.config.model,
                "keep_alive": self.config.ollama_keep_alive,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "lora_fallback": lora_result,
            }
        except Exception as exc:
            return {
                "ok": False,
                "state": "failed",
                "provider": "ollama",
                "model": self.config.model,
                "error": str(exc),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
                "lora_fallback": lora_result,
            }
    
    def _build_prompt(self, context: dict) -> str:
        """Build the full prompt for the local LLM with Nova context."""
        if context.get("raw_prompt"):
            return str(context["raw_prompt"])

        try:
            from nova_dolphin_training import dolphin_training_profile

            dolphin_profile = "\n\n" + dolphin_training_profile().strip()
        except Exception:
            dolphin_profile = ""

        system = f"""You are Nova Creature's language cortex. Nova's router has already selected the task route. Use the supplied memory, dictionary meanings, route context, and brain votes. Do not invent saved personal facts. Do not claim to remember anything unless Nova memory provides it. Answer clearly and directly.

NOVA IDENTITY:
You are Nova Creature, a multi-brain AI system.

SELECTED ROUTE:
{context.get('selected_route', 'general')}

USER MESSAGE:
{context.get('user_message', '')}

NORMALIZED MESSAGE:
{context.get('normalized_message', context.get('user_message', ''))}

DICTIONARY MEANINGS:
{context.get('dictionary_meanings', 'None')}

MEMORY MATCHES:
{context.get('memory_matches', 'None')}

BRAIN ROLE VOTES:
{context.get('brain_votes', 'None')}

ROUTE TRACE:
{context.get('route_trace', 'None')}

CURRENT TASK:
{context.get('task_instruction', 'Respond to the user.')}

OUTPUT RULES:
- Answer cleanly and directly.
- Do not expose hidden code internals unless asked.
- Do not invent personal facts.
- If memory is missing, say it is not saved yet.
- MEMORY RULE: When the user mentions a personal fact like "my favorite food is pizza", 
  Nova saves this in memory. When asked about it later, use the saved memory.
- IDENTITY RULE: The user's statements about themselves (like "I was born in 1980", 
  "my name is X") are facts ABOUT THE USER. Do not repeat them as if Nova is saying them.
  Answer in second person ("You were born in 1980") not first person.
- Keep the final answer useful and readable."""

        if dolphin_profile:
            system += dolphin_profile

        return system
    
    def _call_ollama(
        self,
        prompt: str,
        options_override: dict = None,
        model_override: str = None,
        timeout_override: int = None,
        keep_alive_override: str = None,
    ) -> LocalLLMResponse:
        """Call Ollama API."""
        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        active_model = model_override or self.config.model
        active_timeout = int(timeout_override or self.config.timeout)

        options = {
            "temperature": 0.7,
            "top_k": 40,
            "num_ctx": self.config.context_window,
            "num_predict": 256,
        }
        if options_override:
            options.update(options_override)
        
        payload = {
            "model": active_model,
            "prompt": prompt,
            "stream": False,
            "options": options,
            "keep_alive": str(keep_alive_override or self.config.ollama_keep_alive),
        }
        
        start = time.time()
        try:
            if HAS_HTTPX:
                resp = httpx.post(url, json=payload, timeout=active_timeout)
                resp.raise_for_status()
                data = resp.json()
                raw = clean_local_llm_output(data.get("response", ""))
            else:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=active_timeout) as r:
                    data = json.loads(r.read())
                raw = clean_local_llm_output(data.get("response", ""))
            
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=True,
                provider="ollama",
                model=active_model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error=None,
                fallback_used=False,
                response_time_ms=elapsed,
                finish_reason=str(data.get("done_reason") or ""),
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="ollama",
                model=active_model,
                url=url,
                prompt=prompt,
                raw_output="",
                error=str(e),
                fallback_used=self.config.fallback,
                fallback_reason=f"Ollama error: {e}",
                response_time_ms=elapsed,
            )
    
    def _call_ollama_stream(
        self,
        prompt: str,
        on_delta: Callable[[str], bool | None],
        is_cancelled: Callable[[], bool] | None = None,
        options_override: dict = None,
        model_override: str = None,
        timeout_override: int = None,
        keep_alive_override: str = None,
    ) -> LocalLLMResponse:
        """Call Ollama's NDJSON stream and publish genuine incremental text."""
        import urllib.request

        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        active_model = model_override or self.config.model
        active_timeout = int(timeout_override or self.config.timeout)
        options = {
            "temperature": 0.7,
            "top_k": 40,
            "num_ctx": self.config.context_window,
            "num_predict": 256,
        }
        if options_override:
            options.update(options_override)
        payload = {
            "model": active_model,
            "prompt": prompt,
            "stream": True,
            "options": options,
            "keep_alive": str(keep_alive_override or self.config.ollama_keep_alive),
        }
        start = time.time()
        raw_parts: list[str] = []
        visible_filter = _VisibleReasoningFilter(on_delta)
        cancelled = False
        finish_reason = ""
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=active_timeout) as response:
                for raw_line in response:
                    if is_cancelled and is_cancelled():
                        cancelled = True
                        break
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise RuntimeError(str(data["error"]))
                    delta = str(data.get("response") or "")
                    if delta:
                        raw_parts.append(delta)
                        if visible_filter.feed(delta) is False:
                            cancelled = True
                            break
                    if data.get("done"):
                        finish_reason = str(data.get("done_reason") or "")
                        break
            if not cancelled:
                visible_filter.finish()
            raw = clean_local_llm_output("".join(raw_parts))
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=bool(raw) and not cancelled,
                provider="ollama",
                model=active_model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error="stream_cancelled" if cancelled else (None if raw else "ollama_stream_empty_output"),
                fallback_used=False,
                fallback_reason="The streaming request was cancelled" if cancelled else ("" if raw else "Ollama stream returned empty output"),
                response_time_ms=elapsed,
                finish_reason=finish_reason,
            )
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="ollama",
                model=active_model,
                url=url,
                prompt=prompt,
                raw_output=clean_local_llm_output("".join(raw_parts)),
                error=str(exc),
                fallback_used=self.config.fallback,
                fallback_reason=f"Ollama streaming error: {exc}",
                response_time_ms=elapsed,
            )

    def _call_lm_studio(self, prompt: str) -> LocalLLMResponse:
        """Call LM Studio (OpenAI-compatible API)."""
        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Respond based on the system context."}
            ],
            "temperature": 0.7,
            "max_tokens": 256,
            "stream": False,
        }
        
        start = time.time()
        try:
            if HAS_HTTPX:
                resp = httpx.post(url, json=payload, timeout=self.config.timeout)
                resp.raise_for_status()
                data = resp.json()
                raw = clean_local_llm_output(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
            else:
                import urllib.request
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.config.timeout) as r:
                    data = json.loads(r.read())
                raw = clean_local_llm_output(data.get("choices", [{}])[0].get("message", {}).get("content", ""))
            
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=True,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error=None,
                fallback_used=False,
                response_time_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output="",
                error=str(e),
                fallback_used=self.config.fallback,
                fallback_reason=f"LM Studio error: {e}",
                response_time_ms=elapsed,
            )

    def _call_lm_studio_stream(
        self,
        prompt: str,
        on_delta: Callable[[str], bool | None],
        is_cancelled: Callable[[], bool] | None = None,
    ) -> LocalLLMResponse:
        """Consume an OpenAI-compatible SSE stream from LM Studio."""
        import urllib.request

        url = self.config.url
        if not url.startswith("http"):
            url = f"http://{url}"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Respond based on the system context."},
            ],
            "temperature": 0.7,
            "max_tokens": 256,
            "stream": True,
        }
        start = time.time()
        raw_parts: list[str] = []
        cancelled = False
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                for raw_line in response:
                    if is_cancelled and is_cancelled():
                        cancelled = True
                        break
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        break
                    data = json.loads(value)
                    delta = str(
                        ((data.get("choices") or [{}])[0].get("delta") or {}).get("content")
                        or ""
                    )
                    if delta:
                        raw_parts.append(delta)
                        if on_delta(delta) is False:
                            cancelled = True
                            break
            raw = clean_local_llm_output("".join(raw_parts))
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=bool(raw) and not cancelled,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output=raw,
                error="stream_cancelled" if cancelled else (None if raw else "lm_studio_stream_empty_output"),
                fallback_used=False,
                fallback_reason="The streaming request was cancelled" if cancelled else ("" if raw else "LM Studio stream returned empty output"),
                response_time_ms=elapsed,
            )
        except Exception as exc:
            elapsed = (time.time() - start) * 1000
            return LocalLLMResponse(
                local_llm_used=False,
                provider="lm_studio",
                model=self.config.model,
                url=url,
                prompt=prompt,
                raw_output=clean_local_llm_output("".join(raw_parts)),
                error=str(exc),
                fallback_used=self.config.fallback,
                fallback_reason=f"LM Studio streaming error: {exc}",
                response_time_ms=elapsed,
            )

    def _should_use_lora_runtime(self, context: dict) -> bool:
        """Keep the trained LoRA path for deep work, not every quick planner/chat turn."""
        if not self.config.lora_runtime_enabled or not self.config.lora_adapter_enabled:
            return False

        explicit = context.get("use_lora_runtime")
        if explicit is not None:
            if isinstance(explicit, str):
                return explicit.strip().lower() in {"1", "true", "yes", "on"}
            return bool(explicit)

        route = str(context.get("selected_route", "") or "").lower()
        user_message = str(
            context.get("user_message")
            or context.get("normalized_message")
            or context.get("raw_prompt")
            or ""
        ).lower()

        if route == "planner":
            return False

        deep_routes = {
            "deepseek_direct",
            "coding_help",
            "planning",
            "feedback",
            "ultra_think",
            "deep_conversation",
        }
        explicit_deep_markers = (
            "use nova lora",
            "nova lora",
            "full adapter",
            "full trained",
            "deep mode",
            "ultra think",
            "think hard",
            "think harder",
            "deepseek",
            "deep seek",
            "college",
            "prove",
            "debug",
            "fix this code",
            "hard code",
        )

        force_lora_markers = (
            "use nova lora",
            "nova lora",
            "use lora",
            "trained adapter",
            "full adapter",
            "full trained",
            "adapter only",
            "force adapter",
        )
        mode = self.config.lora_auto_mode
        if mode in {"off", "false", "disabled"}:
            return False
        if mode in OLLAMA_QWEN_FIRST_AUTO_MODES:
            return False
        if any(marker in user_message for marker in force_lora_markers):
            return True
        if mode in SMART_LORA_AUTO_MODES:
            return bool(user_message)
        if mode in QWEN_FIRST_LORA_AUTO_MODES:
            return route != "planner" and bool(user_message)
        if mode in {"always", "all"}:
            return True
        if mode in {"dolphin_first", "dolphin-first", "dolphin", "fallback", "second"}:
            return False
        return route in deep_routes or any(marker in user_message for marker in explicit_deep_markers)

    def _select_smart_lora_adapter_id(self, context: dict | None) -> str:
        """Pick the trained adapter while keeping Nova's router/memory in charge."""
        context = context or {}
        explicit = context.get("lora_adapter_id") or context.get("adapter_id")
        if explicit:
            return str(explicit)

        mode = self.config.lora_auto_mode
        if mode not in SMART_LORA_AUTO_MODES | QWEN_FIRST_LORA_AUTO_MODES:
            return ""

        route = str(context.get("selected_route", "") or "").lower()
        text = str(
            context.get("user_message")
            or context.get("normalized_message")
            or context.get("raw_prompt")
            or ""
        ).lower()

        if route == "planner":
            return ""

        if mode in QWEN_FIRST_LORA_AUTO_MODES:
            return QWEN_FULL_LORA_ADAPTER_ID

        dolphin_markers = (
            "how are you",
            "how do you feel",
            "what do you think",
            "do you like",
            "hard day",
            "talk like",
            "conversation",
            "chat with",
            "make me",
            "build me",
            "create",
            "game",
            "story",
            "imagine",
            "personality",
            "social",
        )
        if any(marker in text for marker in dolphin_markers):
            return DOLPHIN_FULL_LORA_ADAPTER_ID

        qwen_markers = (
            "what is",
            "define",
            "definition",
            "explain",
            "difference between",
            "tell me the difference",
            "when did",
            "where is",
            "who is",
            "how many",
            "math",
            "calculate",
            "evidence",
            "proof",
            "fact",
            "factual",
            "debug",
            "error",
            "fix this code",
        )
        if route in {"coding_help", "research", "feedback", "deep_conversation"}:
            return QWEN_FULL_LORA_ADAPTER_ID
        if any(marker in text for marker in qwen_markers):
            return QWEN_FULL_LORA_ADAPTER_ID

        return DOLPHIN_FULL_LORA_ADAPTER_ID

    def _adapter_only_requested(self, context: dict | None) -> bool:
        """True when the caller explicitly wants the trained LoRA adapter with no Ollama fallback."""
        context = context or {}
        for key in ("adapter_only_mode", "trained_adapter_only", "trained_adapter_only_mode"):
            value = context.get(key)
            if value is None:
                continue
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        return False

    def _call_lora_runtime(
        self,
        prompt: str,
        options_override: dict = None,
        context: dict | None = None,
    ) -> Optional[LocalLLMResponse]:
        """Call the optional Hugging Face/PEFT LoRA runtime before Ollama."""
        if not self._should_use_lora_runtime(context or {}):
            return None

        options_override = options_override or {}
        max_new_tokens = int(options_override.get("num_predict") or self.config.lora_max_new_tokens)
        temperature = float(options_override.get("temperature", 0.35))
        top_p = float(options_override.get("top_p", 0.9))

        try:
            import nova_lora_runtime

            return nova_lora_runtime.generate_with_lora(
                prompt,
                config=self.config,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                top_p=top_p,
                adapter_id=self._select_smart_lora_adapter_id(context) or (context or {}).get("lora_adapter_id") or (context or {}).get("adapter_id"),
                adapter_path=(context or {}).get("lora_adapter_path"),
                base_model=(context or {}).get("lora_base_model"),
            )
        except Exception as e:
            return LocalLLMResponse(
                local_llm_used=False,
                provider="hf_peft_lora",
                model=f"{self.config.lora_base_model} + LoRA",
                prompt=prompt,
                error=str(e),
                fallback_used=True,
                fallback_reason=f"LoRA runtime error: {e}",
            )

    def _ollama_residency_context(
        self,
        context: dict,
        model_name: str,
        family: str,
    ):
        """Return Nova's safe residency guard without changing provider output."""

        if not context.get("adaptive_model_memory"):
            return nullcontext(
                {
                    "enabled": False,
                    "allowed": True,
                    "reason": "request_not_managed",
                    "content_logged": False,
                }
            )
        try:
            from nova_model_quality import get_default_model_quality_registry

            quality = get_default_model_quality_registry()
            if quality.is_quarantined("ollama", model_name):
                return nullcontext(
                    {
                        "enabled": True,
                        "allowed": False,
                        "reason": "model_quality_quarantined",
                        "model_quality": quality.model_status(
                            "ollama",
                            model_name,
                        ),
                        "content_logged": False,
                    }
                )
            from nova_model_memory import (
                installed_ollama_model_size_bytes,
                managed_model_residency,
            )

            configured_size = int(
                context.get("primary_model_size_bytes")
                or context.get("local_llm_model_size_bytes")
                or 0
            )
            installed_size = (
                installed_ollama_model_size_bytes(model_name)
                if configured_size <= 0
                else 0
            )

            return managed_model_residency(
                model_name,
                target_family=family,
                estimated_model_bytes=configured_size or installed_size,
            )
        except Exception:
            return nullcontext(
                {
                    "enabled": True,
                    "allowed": True,
                    "reason": "resource_manager_unavailable_preserve_compatibility",
                    "content_logged": False,
                }
            )

    def _residency_blocked_response(self, prompt: str, model_name: str, decision: dict):
        reason = str((decision or {}).get("reason") or "insufficient_safe_memory")
        return LocalLLMResponse(
            local_llm_used=False,
            provider="ollama",
            model=model_name,
            prompt=prompt,
            error=f"adaptive_model_memory:{reason}",
            fallback_used=True,
            fallback_reason=(
                "Nova protected active or user-controlled models instead of loading "
                f"{model_name}: {reason}"
            ),
        )

    def _record_managed_model_quality(
        self,
        context: dict,
        response: LocalLLMResponse,
        family: str,
    ) -> None:
        """Record content-free provider health only for Nova-managed Ollama calls."""

        if not context.get("adaptive_model_memory"):
            return
        if str(getattr(response, "provider", "") or "").lower() != "ollama":
            return
        residency_reason = str(
            (context.get("model_residency") or {}).get("reason") or ""
        )
        if residency_reason in {
            "model_quality_quarantined",
            "insufficient_safe_memory",
            "model_memory_policy_blocked",
        }:
            return
        try:
            from nova_model_quality import get_default_model_quality_registry

            registry = get_default_model_quality_registry()
            model_name = str(
                getattr(response, "model", "")
                or context.get("local_llm_model")
                or context.get("ollama_model")
                or self.config.model
            )
            latency_ms = float(getattr(response, "response_time_ms", 0.0) or 0.0)
            if bool(getattr(response, "local_llm_used", False)) and str(
                getattr(response, "raw_output", "") or ""
            ).strip():
                registry.record_success(
                    "ollama",
                    model_name,
                    latency_ms=latency_ms,
                    source=f"{family}_runtime",
                )
            else:
                error = str(getattr(response, "error", "") or "").lower()
                registry.record_failure(
                    "ollama",
                    model_name,
                    latency_ms=latency_ms,
                    reason=(
                        "timeout"
                        if "timed out" in error or "timeout" in error
                        else (
                            "empty_response"
                            if bool(getattr(response, "local_llm_used", False))
                            else "provider_error"
                        )
                    ),
                    source=f"{family}_runtime",
                )
        except Exception:
            # Quality telemetry must never break a working generation path.
            return
    
    def generate(self, context: dict) -> LocalLLMResponse:
        """Main generation method. Routes to correct provider."""
        if not self.config.use_local_llm:
            return LocalLLMResponse(
                local_llm_used=False,
                fallback_used=self.config.fallback,
                fallback_reason="NOVA_USE_LOCAL_LLM is not enabled",
            )
        
        prompt = self._build_prompt(context)
        options_override = context.get("ollama_options") or context.get("local_llm_options")
        model_override = context.get("local_llm_model") or context.get("ollama_model")
        timeout_override = context.get("local_llm_timeout") or context.get("ollama_timeout")
        keep_alive_override = context.get("local_llm_keep_alive")

        lora_response = self._call_lora_runtime(
            prompt,
            options_override=options_override,
            context=context,
        )
        adapter_only = self._adapter_only_requested(context)
        if lora_response and lora_response.local_llm_used:
            if self.config.log_prompts:
                self._save_log(context, lora_response)
            return lora_response

        if adapter_only:
            if lora_response:
                lora_response.fallback_used = False
                if self.config.log_prompts:
                    self._save_log(context, lora_response)
                return lora_response

            response = LocalLLMResponse(
                local_llm_used=False,
                provider="hf_peft_lora",
                model=f"{self.config.lora_base_model} + LoRA",
                prompt=prompt,
                error="LoRA adapter runtime is not available or not enabled",
                fallback_used=False,
                fallback_reason="Adapter-only mode requested, so Ollama fallback was skipped",
            )
            if self.config.log_prompts:
                self._save_log(context, response)
            return response
        
        target_family = "primary"
        if self.config.provider == "lm_studio":
            response = self._call_lm_studio(prompt)
        else:  # Default to ollama
            target_model = str(model_override or self.config.model or "").strip()
            prompt, reasoning_control = apply_qwen_reasoning_control(
                prompt,
                target_model,
                context,
            )
            context["reasoning_control"] = reasoning_control
            target_family = (
                "middle"
                if str(context.get("primary_model_tier") or "") == "middle"
                else "primary"
            )
            if context.get("adaptive_model_memory"):
                with self._ollama_residency_context(
                    context,
                    target_model,
                    target_family,
                ) as residency:
                    context["model_residency"] = residency
                    if residency.get("allowed"):
                        response = self._call_ollama(
                            prompt,
                            options_override=options_override,
                            model_override=model_override,
                            timeout_override=timeout_override,
                            keep_alive_override=keep_alive_override,
                        )
                    else:
                        response = self._residency_blocked_response(
                            prompt,
                            target_model,
                            residency,
                        )
            elif target_family == "middle":
                from nova_model_memory import model_activity

                with model_activity("reviewer"):
                    response = self._call_ollama(
                        prompt,
                        options_override=options_override,
                        model_override=model_override,
                        timeout_override=timeout_override,
                        keep_alive_override=keep_alive_override,
                    )
            else:
                response = self._call_ollama(
                    prompt,
                    options_override=options_override,
                    model_override=model_override,
                    timeout_override=timeout_override,
                    keep_alive_override=keep_alive_override,
                )

        self._record_managed_model_quality(context, response, target_family)
        
        if self.config.log_prompts:
            self._save_log(context, response)
        
        return response
    
    def generate_stream(
        self,
        context: dict,
        on_delta: Callable[[str], bool | None],
        is_cancelled: Callable[[], bool] | None = None,
    ) -> LocalLLMResponse:
        """Generate through the configured local backend with real deltas.

        Provider selection mirrors :meth:`generate`. LoRA uses its native
        transformer streamer when available, otherwise Nova safely falls back
        to the configured local runtime just as the completed path does.
        """
        if not self.config.use_local_llm:
            return LocalLLMResponse(
                local_llm_used=False,
                fallback_used=self.config.fallback,
                fallback_reason="NOVA_USE_LOCAL_LLM is not enabled",
            )

        prompt = self._build_prompt(context)
        options_override = context.get("ollama_options") or context.get("local_llm_options")
        model_override = context.get("local_llm_model") or context.get("ollama_model")
        timeout_override = context.get("local_llm_timeout") or context.get("ollama_timeout")
        keep_alive_override = context.get("local_llm_keep_alive")

        lora_response = None
        lora_streamed = False
        if self._should_use_lora_runtime(context):
            options = options_override or {}

            def publish_lora_delta(delta: str):
                nonlocal lora_streamed
                lora_streamed = lora_streamed or bool(delta)
                return on_delta(delta)

            try:
                import nova_lora_runtime

                lora_response = nova_lora_runtime.generate_with_lora_stream(
                    prompt,
                    on_delta=publish_lora_delta,
                    is_cancelled=is_cancelled,
                    config=self.config,
                    max_new_tokens=int(options.get("num_predict") or self.config.lora_max_new_tokens),
                    temperature=float(options.get("temperature", 0.35)),
                    top_p=float(options.get("top_p", 0.9)),
                    adapter_id=self._select_smart_lora_adapter_id(context) or context.get("lora_adapter_id") or context.get("adapter_id"),
                    adapter_path=context.get("lora_adapter_path"),
                    base_model=context.get("lora_base_model"),
                )
            except Exception as exc:
                lora_response = LocalLLMResponse(
                    local_llm_used=False,
                    provider="hf_peft_lora",
                    model=f"{self.config.lora_base_model} + LoRA",
                    prompt=prompt,
                    error=str(exc),
                    fallback_used=True,
                    fallback_reason=f"LoRA streaming runtime error: {exc}",
                )
            if lora_response and lora_response.local_llm_used:
                if self.config.log_prompts:
                    self._save_log(context, lora_response)
                return lora_response
            if lora_streamed:
                # Never mix two providers inside one visible stream. The
                # synthesizer will close the partial answer with a safe tail.
                if self.config.log_prompts and lora_response:
                    self._save_log(context, lora_response)
                return lora_response

        if self._adapter_only_requested(context):
            response = lora_response or LocalLLMResponse(
                local_llm_used=False,
                provider="hf_peft_lora",
                model=f"{self.config.lora_base_model} + LoRA",
                prompt=prompt,
                error="LoRA streaming runtime is unavailable",
                fallback_used=False,
                fallback_reason="Adapter-only mode requested, so provider fallback was skipped",
            )
            response.fallback_used = False
            if self.config.log_prompts:
                self._save_log(context, response)
            return response

        if is_cancelled and is_cancelled():
            return LocalLLMResponse(
                local_llm_used=False,
                fallback_used=False,
                fallback_reason="The streaming request was cancelled",
                error="stream_cancelled",
            )
        target_family = "primary"
        if self.config.provider == "lm_studio":
            response = self._call_lm_studio_stream(prompt, on_delta, is_cancelled)
        else:
            target_model = str(model_override or self.config.model or "").strip()
            prompt, reasoning_control = apply_qwen_reasoning_control(
                prompt,
                target_model,
                context,
            )
            context["reasoning_control"] = reasoning_control
            target_family = (
                "middle"
                if str(context.get("primary_model_tier") or "") == "middle"
                else "primary"
            )
            if context.get("adaptive_model_memory"):
                with self._ollama_residency_context(
                    context,
                    target_model,
                    target_family,
                ) as residency:
                    context["model_residency"] = residency
                    if residency.get("allowed"):
                        response = self._call_ollama_stream(
                            prompt,
                            on_delta,
                            is_cancelled,
                            options_override=options_override,
                            model_override=model_override,
                            timeout_override=timeout_override,
                            keep_alive_override=keep_alive_override,
                        )
                    else:
                        response = self._residency_blocked_response(
                            prompt,
                            target_model,
                            residency,
                        )
            elif target_family == "middle":
                from nova_model_memory import model_activity

                with model_activity("reviewer"):
                    response = self._call_ollama_stream(
                        prompt,
                        on_delta,
                        is_cancelled,
                        options_override=options_override,
                        model_override=model_override,
                        timeout_override=timeout_override,
                        keep_alive_override=keep_alive_override,
                    )
            else:
                response = self._call_ollama_stream(
                    prompt,
                    on_delta,
                    is_cancelled,
                    options_override=options_override,
                    model_override=model_override,
                    timeout_override=timeout_override,
                    keep_alive_override=keep_alive_override,
                )
        self._record_managed_model_quality(context, response, target_family)
        if self.config.log_prompts:
            self._save_log(context, response)
        return response

    def _save_log(self, context: dict, response: LocalLLMResponse):
        """Save local LLM call to training log."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "user_input": context.get("user_message", ""),
            "normalized_input": context.get("normalized_message", ""),
            "dictionary_meanings": context.get("dictionary_meanings", ""),
            "memory_matches": context.get("memory_matches", ""),
            "selected_route": context.get("selected_route", ""),
            "brain_votes": context.get("brain_votes", ""),
            "prompt_sent": response.prompt[:500] if response.prompt else "",
            "raw_output": response.raw_output[:500] if response.raw_output else "",
            "error": response.error,
            "fallback_used": response.fallback_used,
            "fallback_reason": response.fallback_reason,
            "response_time_ms": response.response_time_ms,
            "provider": response.provider,
            "model": response.model,
            "local_llm_used": response.local_llm_used,
        }
        try:
            with open(self._log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            pass  # Silent fail on log write


# ─── Singleton ────────────────────────────────────────────────
_LLM_CONNECTOR = None

def get_llm_connector():
    """Get or create the singleton LLM connector."""
    global _LLM_CONNECTOR
    if _LLM_CONNECTOR is None:
        _LLM_CONNECTOR = LocalLLMConnector()
    return _LLM_CONNECTOR


# ─── Quick self-test ─────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("NOVA LOCAL LLM CORTEX CONNECTOR — Self Test")
    print("=" * 60)
    
    connector = get_llm_connector()
    config = connector.config
    
    print(f"\nConfig:")
    print(f"  USE_LOCAL_LLM: {config.use_local_llm}")
    print(f"  PROVIDER: {config.provider}")
    print(f"  MODEL: {config.model}")
    print(f"  URL: {config.url}")
    print(f"  TIMEOUT: {config.timeout}s")
    print(f"  FALLBACK: {config.fallback}")
    
    available = connector.is_available()
    print(f"\nLocal LLM available: {available}")
    
    if available:
        print("\nTesting LLM generation...")
        context = {
            "user_message": "Hello, what can you do?",
            "selected_route": "general_conversation",
            "dictionary_meanings": "None",
            "memory_matches": "None",
            "brain_votes": "memory=0.3, critic=0.3, speech=0.4",
            "route_trace": "memory_transformer -> critic_conscience_transformer -> speech_output_transformer",
            "task_instruction": "Respond to the user's greeting.",
        }
        result = connector.generate(context)
        print(f"\nResult: {result}")
        print(f"  local_llm_used: {result.local_llm_used}")
        print(f"  provider: {result.provider}")
        print(f"  model: {result.model}")
        print(f"  fallback_used: {result.fallback_used}")
        print(f"  response_time_ms: {result.response_time_ms:.0f}")
        if result.error:
            print(f"  error: {result.error}")
        if result.raw_output:
            print(f"\n  raw_output: {result.raw_output[:300]}")
    else:
        print("\nLocal LLM not available. This is expected if Ollama/LM Studio is not running.")
        print("Fallback behavior will be used.")
    
    print("\nDone.")
