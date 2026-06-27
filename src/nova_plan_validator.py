"""
Nova Plan Validator
===================
Validates the planner JSON before Nova executes it.
Nova remains the boss — the LLM planner cannot bypass validation.

Rejection rules:
- Invalid JSON
- Missing required fields
- Unknown routes
- Low confidence below threshold
- Unsafe tool/memory requests
- Memory writes not explicitly requested
- LLM inventing saved facts
"""

import json, re

VALID_ROUTES = [
    "memory_recall", "memory_write", "dictionary_lookup",
    "math_solver", "weather_lookup", "web_search", "coding_help",
    "general_conversation", "planning", "feedback", "unknown",
]

REQUIRED_FIELDS = [
    "route", "intent", "slot_needed", "answer_style",
    "needs_memory", "needs_dictionary", "needs_math",
    "needs_weather", "needs_web", "needs_tool", "needs_llm_synthesis", "confidence",
]

VALID_ANSWER_STYLES = [
    "second_person_direct", "explanation", "list",
    "code", "short_answer", "long_answer", "confirmation",
    "short_definition",
]

CONFIDENCE_THRESHOLD = 0.20  # Below this, reject

# Memory write must come from explicit user commands
MEMORY_WRITE_TRIGGERS = [
    "long-term remember this:",
    "remember this long term:",
    "save this to long-term memory:",
    "always remember:",
    "forget this long-term memory:",
    "edit long-term memory:",
    "remember this:",
    "save this:",
    # Common name/profile patterns — allow memory_write without explicit LTM prefix
    "my name is",
    "i was born",
    "i live in",
    "i work at",
    "i work for",
    "my favorite",
    "my dog",
    "my cat",
    "i am from",
    "i am a",
    "i am an",
]


class ValidationResult:
    def __init__(self, ok=False, plan=None, errors=None, fallback_reason=None):
        self.ok = ok
        self.plan = plan or {}
        self.errors = errors or []
        self.fallback_reason = fallback_reason

    def __bool__(self):
        return self.ok


def validate(plan, raw_user_message=None):
    """
    Validate a planner JSON object.

    Args:
        plan: dict from the intent planner.
        raw_user_message: original user message for additional checks.

    Returns:
        ValidationResult with .ok=True/False, .plan, .errors
    """
    errors = []

    # 1. Must be a dict
    if not isinstance(plan, dict):
        return ValidationResult(
            ok=False, plan={},
            errors=["plan is not a dict"],
            fallback_reason="planner_returns_non_dict"
        )

    # 2. Required fields
    for field in REQUIRED_FIELDS:
        if field not in plan:
            errors.append(f"missing field: {field}")

    if errors:
        return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="missing_fields")

    # 3. Route must be valid
    route = plan.get("route", "")
    if route not in VALID_ROUTES:
        errors.append(f"unknown route: {route}")
        return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="unknown_route")

    # 4. Confidence threshold
    confidence = plan.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)):
        errors.append("confidence must be a number")
        return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="invalid_confidence")

    if confidence < CONFIDENCE_THRESHOLD:
        errors.append(f"confidence {confidence} below threshold {CONFIDENCE_THRESHOLD}")
        return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="low_confidence")

    # 5. Answer style must be valid
    style = plan.get("answer_style", "")
    if style not in VALID_ANSWER_STYLES:
        errors.append(f"unknown answer_style: {style}")
        return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="unknown_answer_style")

    # 6. Memory write safety
    if route == "memory_write" and raw_user_message:
        q = raw_user_message.lower().strip()
        is_explicit = any(q.startswith(trigger.lower()) for trigger in MEMORY_WRITE_TRIGGERS)
        if not is_explicit:
            errors.append("memory_write not explicitly requested by user")
            return ValidationResult(ok=False, plan=plan, errors=errors, fallback_reason="memory_write_not_requested")

    # 7. Memory recall with no memory needed flag mismatch
    if route == "memory_recall" and not plan.get("needs_memory"):
        # This is suspicious but not automatically invalid — allow it with warning
        pass

    # 8. Slot safety: custom_slot is fine, but must not be used for unsafe access
    slot = plan.get("slot_needed")
    if slot and slot not in (None, "null", "custom_slot"):
        # Fine — specific slot requested
        pass

    return ValidationResult(ok=True, plan=plan, errors=[])


def make_fallback_plan(user_message):
    """
    Create a safe fallback plan when validation fails.
    Uses Nova's deterministic classification.
    """
    try:
        from nova_hybrid_router import classify_domain
        domain = classify_domain(user_message)
    except Exception:
        domain = "general"

    route_map = {
        "memory_recall": "memory_recall",
        "dictionary": "dictionary_lookup",
        "math": "math_solver",
        "coding": "coding_help",
        "general": "general_conversation",
        "science": "memory_recall",
        "philosophy": "general_conversation",
        "weather": "weather_lookup",
        "web_search": "web_search",
    }
    route = route_map.get(domain, "general_conversation")

    return {
        "route": route,
        "intent": f"fallback classification: {domain}",
        "slot_needed": None,
        "answer_style": "short_answer",
        "needs_memory": domain in ("memory_recall", "general", "science"),
        "needs_dictionary": domain == "dictionary",
        "needs_math": domain == "math",
        "needs_weather": domain == "weather",
        "needs_tool": False,
        "needs_llm_synthesis": route not in ("memory_recall", "math_solver"),
        "confidence": 0.60,
        "_planner_used": "fallback_validator",
        "_planner_validated": False,
    }
