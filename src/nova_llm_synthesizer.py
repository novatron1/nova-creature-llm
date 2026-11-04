"""
Nova LLM Synthesizer
====================
Generates a polished final answer using the local LLM when direct answers aren't available.
Nova remains in control — the LLM is only asked to help word the final answer.
"""

import json, os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

LAST_LOCAL_LLM_MODEL = ""
LAST_LOCAL_LLM_TIMEOUT = None


def _clean_synthesized_answer(raw_output: str) -> str:
    text = str(raw_output or "").strip()
    if re.search(r"(?im)^\s*Nova\s*:", text):
        parts = re.split(r"(?im)^\s*Nova\s*:\s*", text)
        text = parts[-1].strip()

    label_match = re.search(r"(?ims)\n\s*\n\s*(?:Final answer|Answer)\s*:\s*(.+)$", text)
    if label_match:
        before = text[:label_match.start()].strip()
        labeled = label_match.group(1).strip()
        labeled_complete = bool(re.search(r"[.!?`)]\s*$", labeled)) and len(labeled.split()) >= 6
        if labeled_complete:
            text = labeled
        elif before:
            text = before

    text = re.sub(r"(?im)^\s*(Assistant|AI)\s*:\s*", "", text).strip()
    text = re.sub(r"(?im)^\s*(?:Final answer|Answer)\s*:\s*", "", text).strip()
    return text


def _is_academic_question(user_question: str) -> bool:
    q = str(user_question or "").lower()
    return any(
        marker in q
        for marker in (
            "college ",
            "solve ",
            "f = ma",
            "f=ma",
            "fix this python",
            "empiricism",
            "rationalism",
        )
    )


def _build_prompt(context_packet: dict) -> tuple[str, dict]:
    user_question = context_packet.get("user_question", "")
    if _is_academic_question(user_question):
        return (
            "Answer the academic question directly.\n"
            "Give the final answer only. Do not mention memory. Do not add citations unless sources are provided.\n\n"
            f"Question: {user_question}\n\n"
            "Final answer:",
            {"temperature": 0.2, "num_predict": 450},
        )

    system_prompt = context_packet.get("system_prompt", "")
    return (
        f"{system_prompt}\n\nUser: {user_question}\n\nNova:",
        {"temperature": 0.3, "num_predict": 700},
    )


def _select_local_llm(user_question: str, route: str = "") -> tuple[str, int]:
    from nova_local_llm_connector import (
        DEFAULT_DEEP_LOCAL_LLM_MODEL,
        DEFAULT_FAST_LOCAL_LLM_MODEL,
    )

    q = str(user_question or "").lower()
    route_name = str(route or "")
    deep_markers = (
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
    if (
        _is_academic_question(user_question)
        or route_name in {"coding_help", "planning", "feedback"}
        or any(marker in q for marker in deep_markers)
    ):
        return DEFAULT_DEEP_LOCAL_LLM_MODEL, 120
    return DEFAULT_FAST_LOCAL_LLM_MODEL, 45


def generate(context_packet, timeout=15):
    """
    Generate a response from the local LLM using the context packet.

    Args:
        context_packet: dict from nova_context_builder.build().
        timeout: max seconds to wait for LLM response.

    Returns:
        (response_text, success_bool, error_str)
    """
    user_question = context_packet.get("user_question", "")

    if not user_question:
        return None, False, "empty_user_question"

    prompt, ollama_options = _build_prompt(context_packet)
    selected_model, selected_timeout = _select_local_llm(
        user_question,
        context_packet.get("route", "llm_synthesis"),
    )
    global LAST_LOCAL_LLM_MODEL, LAST_LOCAL_LLM_TIMEOUT
    LAST_LOCAL_LLM_MODEL = selected_model
    LAST_LOCAL_LLM_TIMEOUT = selected_timeout

    try:
        from nova_local_llm_connector import LocalLLMConnector
        llm = LocalLLMConnector()
        response = llm.generate({
            **context_packet,
            "raw_prompt": prompt,
            "user_message": user_question,
            "normalized_message": user_question,
            "selected_route": context_packet.get("route", "llm_synthesis"),
            "task_instruction": "Use Nova's context packet to answer the user clearly and directly.",
            "local_llm_model": selected_model,
            "local_llm_timeout": selected_timeout,
            "ollama_options": ollama_options,
        })

        if isinstance(response, str):
            raw_output = response
        elif response and getattr(response, "local_llm_used", False):
            raw_output = getattr(response, "raw_output", "")
            LAST_LOCAL_LLM_MODEL = getattr(response, "model", None) or selected_model
        elif response:
            return None, False, getattr(response, "fallback_reason", None) or "llm_unavailable"
        else:
            raw_output = ""

        if raw_output and raw_output.strip():
            clean = _clean_synthesized_answer(raw_output)
            return clean, True, None
        else:
            return None, False, "llm_returned_empty"
    except ImportError:
        return None, False, "llm_connector_not_available"
    except Exception as e:
        return None, False, f"llm_error: {e}"


def generate_fallback(user_message, timeout=10):
    """
    Ultra-minimal fallback: just ask the LLM to respond directly.
    Only used when all other paths fail.
    """
    prompt = f"""Answer concisely.

User: {user_message}
Nova:"""
    try:
        from nova_local_llm_connector import LocalLLMConnector
        llm = LocalLLMConnector()
        # Use direct Ollama call via context dict
        response = llm.generate({
            "user_message": user_message,
            "selected_route": "fallback",
            "normalized_message": user_message,
            "task_instruction": "Answer concisely in 1-2 sentences. Be helpful and direct.",
            "local_llm_model": "qwen2.5:1.5b",
            "local_llm_timeout": 45,
        })
        if response.local_llm_used and response.raw_output and response.raw_output.strip():
            return response.raw_output.strip(), True, None
        return None, False, response.fallback_reason or "llm_unavailable"
    except Exception as e:
        return None, False, f"llm_error: {e}"
