"""
Nova LLM Synthesizer
====================
Generates a polished final answer using the local LLM when direct answers aren't available.
Nova remains in control — the LLM is only asked to help word the final answer.
"""

import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))


def generate(context_packet, timeout=15):
    """
    Generate a response from the local LLM using the context packet.

    Args:
        context_packet: dict from nova_context_builder.build().
        timeout: max seconds to wait for LLM response.

    Returns:
        (response_text, success_bool, error_str)
    """
    system_prompt = context_packet.get("system_prompt", "")
    user_question = context_packet.get("user_question", "")

    if not user_question:
        return None, False, "empty_user_question"

    # Build the full prompt
    prompt = f"{system_prompt}\n\nUser: {user_question}\n\nNova:"

    try:
        from nova_local_llm_connector import LocalLLMConnector
        llm = LocalLLMConnector()
        response = llm.generate(context_packet)

        if response and response.strip():
            clean = response.strip()
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
        })
        if response.local_llm_used and response.raw_output and response.raw_output.strip():
            return response.raw_output.strip(), True, None
        return None, False, response.fallback_reason or "llm_unavailable"
    except Exception as e:
        return None, False, f"llm_error: {e}"
