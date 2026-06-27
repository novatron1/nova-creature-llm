"""
Nova Context Builder
====================
Builds a structured context packet for the LLM synthesis pass.
Combines the user message, validated plan, memory results, and dictionary results
into a clean prompt that helps the LLM generate a good answer while preventing it
from inventing facts.
"""

import json


def build(user_message, plan, memory_result=None, dictionary_result=None,
          tool_result=None, math_result=None, web_result=None):
    """
    Build a context packet for LLM synthesis.

    Args:
        user_message: original user message.
        plan: validated plan dict.
        memory_result: result from memory_slot_retrieval.retrieve().
        dictionary_result: string dict definition or None.
        tool_result: tool output or None.
        math_result: math result or None.
        web_result: formatted web search results string or None.

    Returns:
        dict with system_prompt, memory_context, and user_question.
    """
    route = plan.get("route", "general_conversation")
    style = plan.get("answer_style", "short_answer")

    # ─── Memory Context ───
    memory_context_items = []

    if memory_result and memory_result.get("found"):
        for r in memory_result.get("records", []):
            raw = r.get("raw_text", "")
            slot = r.get("extracted_slot", "")
            if raw:
                memory_context_items.append(f"- {raw} (slot: {slot})")

    memory_context = "\n".join(memory_context_items) if memory_context_items else "None"

    # ─── Dictionary Context ───
    dict_context = dictionary_result if dictionary_result else "None"
    web_context = web_result if web_result else "None"

    # ─── Style Instructions ───
    style_instructions = {
        "second_person_direct": "Answer directly in second person (you/your). Be concise. Do not repeat the question.",
        "explanation": "Provide a clear explanation. Use examples if helpful.",
        "list": "Provide the answer as a numbered or bullet list.",
        "code": "Provide code with explanation.",
        "short_answer": "Answer concisely in 1-2 sentences.",
        "long_answer": "Provide a thorough answer.",
        "confirmation": "Confirm the action briefly.",
        "short_definition": "Give a concise definition. 1-2 sentences.",
    }
    style_note = style_instructions.get(style, "Answer concisely.")

    # ─── Build System Prompt ───
    system_prompt = f"""You are Nova Creature's language cortex. Your job is to help word the final answer.

Rules:
- Do NOT invent facts that are not in the memory or web context below.
- Do NOT claim the user has information that is not in memory.
- If the user asks about saved personal information and memory context is "None", say it is not saved yet.
- For general explanations, coding help, planning, and creative tasks, answer the user's general question normally.
- Do NOT use phrases like "based on memory" or "from my saved knowledge".
- Answer in second person (you/your) when answering about the user's saved information.
- Be concise and natural.
- IMPORTANT: When web results are provided, use them as factual sources.
  Cite sources by number e.g. [1] when referring to search results.
- Route: {route}
- Style: {style_note}

Memory Context:
{memory_context}

Dictionary Context:
{dict_context}

Web Search Results:
{web_context}"""

    return {
        "system_prompt": system_prompt,
        "memory_context": memory_context,
        "dict_context": dict_context,
        "user_question": user_message,
        "route": route,
        "style": style,
        "style_note": style_note,
    }
