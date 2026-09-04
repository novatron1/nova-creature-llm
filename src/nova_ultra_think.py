"""
Nova Ultra Think route.

This module adds an explicit deep-thinking conversational layer on top of the
existing Nova pipeline. It does not replace the model, alter weights, or mutate
training/checkpoint logic. It only builds a stronger prompt for user requests
that explicitly ask Nova to think harder, then shapes the final answer naturally.
"""

from __future__ import annotations

from pathlib import Path
import json
import os
import re
from typing import Any, Callable

from nova_self_model import build_nova_self_model_prompt_block


ROOT = Path(__file__).resolve().parents[1]

ULTRA_THINK_TRIGGERS = (
    "ultra think",
    "think hard",
    "think harder",
    "deep think",
    "slow think",
    "deep answer",
    "really think",
    "go deep",
)

_TRIGGER_RE = re.compile(
    r"\b(?:ultra\s+think|think\s+hard(?:er)?|deep\s+think|slow\s+think|deep\s+answer|really\s+think|go\s+deep)\b",
    re.IGNORECASE,
)
_LEADING_TRIGGER_RE = re.compile(
    r"^\s*(?:please\s+)?(?:can\s+you\s+)?"
    r"(?:ultra\s+think|think\s+hard(?:er)?|deep\s+think|slow\s+think|deep\s+answer|really\s+think|go\s+deep)"
    r"(?:\s+(?:about|through|on|for))?\s*[:,-]?\s*",
    re.IGNORECASE,
)


ULTRA_THINK_SYSTEM_PROMPT = """You are Nova Creature.

You are using Ultra Think mode because the user explicitly asked for deeper thought.

Think carefully, use recent conversation context, and answer like a real person.

Do not reveal hidden chain-of-thought. If reasoning is useful, give a short natural summary of the conclusion and the key reason, not private step-by-step thinking.

Do not invent saved personal facts. If a saved fact is missing, say it is not saved yet.

Stay grounded, relaxed, and direct. Avoid robotic phrases like "as an AI", "I am unable", "I cannot assist", "it is important to note", and "in conclusion".

For normal conversation, keep the answer natural and connected. Use bullets only when the user asks for structure, code, tests, or steps."""


def _parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return default


def _read_ultra_think_flag_from_files() -> bool:
    for path in (ROOT / ".nova_llm_config", ROOT / ".env"):
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                if key.strip() == "NOVA_ULTRA_THINK":
                    return _parse_bool(value.strip().strip("\"'"), True)
        except Exception:
            pass

    json_path = ROOT / "nova_llm_config.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if "NOVA_ULTRA_THINK" in data:
                return _parse_bool(data.get("NOVA_ULTRA_THINK"), True)
        except Exception:
            pass
    return True


def ultra_think_enabled(config: dict | None = None) -> bool:
    """Return whether the explicit Ultra Think route is enabled."""
    env_value = os.environ.get("NOVA_ULTRA_THINK")
    if env_value is not None:
        return _parse_bool(env_value, True)
    if config and "NOVA_ULTRA_THINK" in config:
        return _parse_bool(config.get("NOVA_ULTRA_THINK"), True)
    return _read_ultra_think_flag_from_files()


def is_ultra_think_request(text: str) -> bool:
    """Detect explicit deep-thinking requests without catching normal chat."""
    return bool(_TRIGGER_RE.search(str(text or "")))


def should_route_ultra_think(text: str, config: dict | None = None) -> bool:
    """Return True when Ultra Think is enabled and the user explicitly asked for it."""
    return ultra_think_enabled(config) and is_ultra_think_request(text)


def strip_ultra_think_trigger(text: str) -> str:
    """Remove the Ultra Think trigger while preserving the actual user request."""
    original = str(text or "").strip()
    if not original:
        return ""
    cleaned = _LEADING_TRIGGER_RE.sub("", original, count=1).strip()
    if cleaned == original and _TRIGGER_RE.search(cleaned):
        cleaned = _TRIGGER_RE.sub("", cleaned, count=1).strip()
        cleaned = re.sub(r"^\s*(?:about|through|on|for)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip(" \t:-,")
    return cleaned or original


def _safe_prompt_text(value: Any, max_chars: int = 1400) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _get_recent_memory(limit: int = 6) -> list[dict[str, str]]:
    try:
        from nova_natural_chat import get_recent_memory

        return get_recent_memory(limit=limit)
    except Exception:
        return []


def _format_recent_memory(recent_memory: list[dict[str, str]] | None) -> str:
    lines: list[str] = []
    for exchange in list(recent_memory or [])[-6:]:
        if not isinstance(exchange, dict):
            continue
        user_text = _safe_prompt_text(exchange.get("user", ""))
        nova_text = _safe_prompt_text(exchange.get("nova", ""))
        if user_text:
            lines.append(f"User: {user_text}")
        if nova_text:
            lines.append(f"Nova Creature: {nova_text}")
    return "\n".join(lines)


def _format_route_context(route_context: Any) -> str:
    if not route_context:
        return ""
    if isinstance(route_context, str):
        return _safe_prompt_text(route_context, max_chars=1800)
    try:
        return _safe_prompt_text(json.dumps(route_context, ensure_ascii=False, sort_keys=True), max_chars=1800)
    except Exception:
        return _safe_prompt_text(route_context, max_chars=1800)


def build_ultra_think_prompt(
    user_input: str,
    recent_memory: list[dict[str, str]] | None = None,
    route_context: Any = None,
) -> str:
    """Build the raw prompt used by the explicit Ultra Think route."""
    current_message = strip_ultra_think_trigger(user_input)
    memory_block = _format_recent_memory(recent_memory if recent_memory is not None else _get_recent_memory())
    route_block = _format_route_context(route_context)
    route_section = f"\nROUTE CONTEXT:\n{route_block}\n" if route_block else ""
    system_prompt = f"{ULTRA_THINK_SYSTEM_PROMPT}\n\n{build_nova_self_model_prompt_block().strip()}"
    return (
        f"SYSTEM:\n{system_prompt}\n\n"
        f"RECENT CONVERSATION:\n{memory_block}\n"
        f"{route_section}\n"
        f"CURRENT USER MESSAGE:\n{_safe_prompt_text(current_message)}\n\n"
        "NOVA CREATURE RESPONSE:"
    )


def _local_llm_defaults() -> tuple[str, int, int]:
    try:
        from nova_local_llm_connector import LocalLLMConfig

        config = LocalLLMConfig()
        return config.deep_model, max(180, int(config.timeout)), int(config.context_window)
    except Exception:
        return "dolphin3", 180, 16384


def _build_context_packet(user_input: str, route_context: Any = None) -> dict[str, Any]:
    question = strip_ultra_think_trigger(user_input)
    prompt = build_ultra_think_prompt(
        user_input,
        recent_memory=_get_recent_memory(),
        route_context=route_context,
    )
    model, timeout, context_window = _local_llm_defaults()
    return {
        "route": "ultra_think",
        "selected_route": "ultra_think",
        "user_question": question,
        "user_message": question,
        "normalized_message": question,
        "task_instruction": "Use Nova Ultra Think mode: answer clearly, naturally, and without hidden chain-of-thought.",
        "system_prompt": prompt,
        "raw_prompt": prompt,
        "local_llm_model": model,
        "local_llm_timeout": timeout,
        "ollama_options": {
            "num_ctx": context_window,
            "temperature": 0.25,
            "num_predict": 900,
        },
    }


def _default_llm_generate(context_packet: dict[str, Any]):
    from nova_local_llm_connector import LocalLLMConnector

    return LocalLLMConnector().generate(context_packet)


def _normalize_llm_result(result: Any, default_model: str) -> tuple[str, bool, str | None, str]:
    if isinstance(result, tuple):
        text = result[0] if len(result) > 0 else ""
        ok = bool(result[1]) if len(result) > 1 else bool(text)
        error = result[2] if len(result) > 2 else None
        return str(text or ""), ok, str(error) if error else None, default_model

    if isinstance(result, str):
        return result, bool(result.strip()), None if result.strip() else "empty_response", default_model

    if result is None:
        return "", False, "llm_unavailable", default_model

    model = getattr(result, "model", None) or default_model
    if getattr(result, "local_llm_used", False):
        return str(getattr(result, "raw_output", "") or ""), True, None, str(model)

    fallback_reason = getattr(result, "fallback_reason", None) or "llm_unavailable"
    return "", False, str(fallback_reason), str(model)


def _memory_guard_answer(question: str) -> tuple[str | None, dict[str, Any]]:
    try:
        from nova_long_term_memory import missing_recall_answer, recall_from_question

        recalled = recall_from_question(question)
        if recalled:
            record, answer = recalled
            return str(answer or "").strip(), {
                "source": "ultra_think_memory_guard",
                "domain": "memory",
                "long_term_memory_used": True,
                "memory_retrieved": True,
                "memory_id": (record or {}).get("memory_id"),
            }
        missing = missing_recall_answer(question)
        if missing:
            return missing, {
                "source": "ultra_think_memory_guard",
                "domain": "memory",
                "long_term_memory_used": True,
                "memory_retrieved": False,
                "missing_memory_guard": True,
            }
    except Exception as exc:
        return None, {"memory_guard_error": str(exc)[:120]}
    return None, {}


def _shape_ultra_answer(raw_text: str, user_input: str, recent_memory: list[dict[str, str]]) -> str:
    clean = str(raw_text or "").strip()
    try:
        from nova_local_llm_connector import clean_local_llm_output

        clean = clean_local_llm_output(clean)
    except Exception:
        pass
    try:
        from nova_natural_chat import shape_response

        shaped = shape_response(clean, user_input=user_input, recent_memory=recent_memory)
        return shaped or clean
    except Exception:
        return clean


def run_ultra_think(
    user_input: str,
    route_context: Any = None,
    llm_generate_fn: Callable[[dict[str, Any]], Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Run the explicit Ultra Think route and return ``(response, trace)``."""
    question = strip_ultra_think_trigger(user_input)
    model, timeout, context_window = _local_llm_defaults()
    trace: dict[str, Any] = {
        "source": "ultra_think",
        "domain": "deep_reasoning",
        "roles": [
            "planner_transformer",
            "memory_transformer",
            "local_llm_cortex",
            "critic_conscience_transformer",
            "speech_output_transformer",
        ],
        "skills": ["ultra_think", "recent_memory", model, "critic_rewrite"],
        "confidence": 0.88,
        "route_path": [
            "ultra_think_router",
            "memory_context",
            f"{model}_draft",
            "critic",
            "natural_speech",
        ],
        "local_llm_model": model,
        "local_llm_timeout": timeout,
        "local_llm_context": context_window,
        "local_llm_synthesis_used": False,
        "final_answer_source": "ultra_think",
    }

    if not ultra_think_enabled():
        trace.update(
            {
                "source": "ultra_think_disabled",
                "confidence": 0.1,
                "route_path": ["ultra_think_disabled"],
                "final_answer_source": "ultra_think_disabled",
            }
        )
        return "Ultra Think is turned off right now.", trace

    guarded_answer, guard_trace = _memory_guard_answer(question)
    if guarded_answer:
        trace.update(guard_trace)
        trace["roles"] = ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]
        trace["skills"] = ["memory_guard", "no_memory_hallucination"]
        trace["confidence"] = 0.96
        trace["route_path"] = ["ultra_think_router", "memory_guard", "speech_output"]
        trace["local_llm_synthesis_used"] = False
        trace["final_answer_source"] = trace.get("source", "ultra_think_memory_guard")
        return guarded_answer, trace

    recent_memory = _get_recent_memory()
    context_packet = _build_context_packet(user_input, route_context=route_context)
    generator = llm_generate_fn or _default_llm_generate
    try:
        raw, ok, error, used_model = _normalize_llm_result(generator(context_packet), model)
    except Exception as exc:
        raw, ok, error, used_model = "", False, str(exc), model

    trace["local_llm_model"] = used_model or model
    trace["local_llm_synthesis_used"] = bool(ok and raw.strip())
    if not ok or not raw.strip():
        trace["confidence"] = 0.42
        trace["local_llm_error"] = error or "empty_response"
        trace["fallback_used"] = True
        response = (
            "Yeah, I can go deeper on that, but the local model didn't return a clean answer yet. "
            f"The thing to focus on is: {question}"
        )
        return response, trace

    response = _shape_ultra_answer(raw, user_input=question, recent_memory=recent_memory)
    trace["fallback_used"] = False
    trace["natural_response_shaped"] = response != raw.strip()
    return response, trace
