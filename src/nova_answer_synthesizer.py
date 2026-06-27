"""
Nova Answer Synthesizer
=======================
Converts retrieved memory into clean second-person answers.
No debug labels. No raw memory dumps. No question repetition.
Supports direct answers without requiring LLM synthesis.
"""

import re


def try_direct_answer(plan, memory_result, dictionary_result, math_result):
    """
    Try to produce a direct answer without LLM synthesis.

    Args:
        plan: validated plan dict.
        memory_result: result from memory slot retrieval.
        dictionary_result: dict lookup result or None.
        math_result: math solving result or None.

    Returns:
        (answer_string, used_direct) or (None, False)
    """
    route = plan.get("route", "")
    style = plan.get("answer_style", "")
    slot_needed = plan.get("slot_needed")

    # ─── Memory recall: direct second-person answer ───
    if route == "memory_recall" and memory_result.get("found"):
        raw_text = memory_result.get("raw_text")

        # If long_term memory already has synthesized answer (from lesson search)
        if memory_result.get("synthesized_answer"):
            return memory_result["synthesized_answer"], True

        if raw_text:
            syn = synthesize_from_fact(raw_text, slot_needed)
            if syn:
                return syn, True

    # ─── Memory recall summary (show all) ───
    if route == "memory_recall" and slot_needed is None and memory_result.get("found"):
        records = memory_result.get("records", [])
        if records:
            lines = []
            for r in records:
                rt = r.get("raw_text", "")
                syn = synthesize_from_fact(rt, None)
                lines.append(syn if syn else rt)
            return "\n".join(lines), True

    # ─── Dictionary lookup ───
    if route == "dictionary_lookup" and dictionary_result:
        return dictionary_result, True

    # ─── Math solver ───
    if route == "math_solver" and math_result:
        return f"The answer is {math_result}.", True

    # ─── Memory write confirmation ───
    if route == "memory_write":
        slot = plan.get("slot_needed", "custom")
        value = plan.get("_extracted_value", "")
        if slot and value:
            return f"Saved: your {slot.replace('_', ' ')} is {value}.", True
        return "I've saved that to my long-term memory.", True

    return None, False


def fallback_answer(plan, memory_result=None):
    """
    Generate a safe fallback when critic rejects the LLM synthesis or no answer is generated.

    Args:
        plan: validated plan dict.
        memory_result: optional memory retrieval result.

    Returns:
        str: clean fallback answer.
    """
    route = plan.get("route", "")

    if route == "memory_recall":
        if memory_result and memory_result.get("found"):
            raw = memory_result.get("raw_text", "")
            if raw:
                syn = synthesize_from_fact(raw, plan.get("slot_needed"))
                if syn:
                    return syn
            return f"I recall: {raw[:100]}"
        else:
            return "I don't have that information saved yet."

    if route == "memory_write":
        return "I've noted that."

    if route == "dictionary_lookup":
        return "I couldn't find that word in my dictionary."

    return "I'm not sure how to answer that. Can you rephrase?"


def synthesize_from_fact(raw_text, slot_needed=None):
    """
    Transform a saved fact into a clean second-person answer.
    Case-insensitive — handles both 'My ...' and 'my ...'.
    """
    if not raw_text:
        return None

    mem = raw_text.strip()
    if not mem:
        return None
    
    # Normalize: capitalize first letter, fix standalone "i" to "I"
    mem = mem[0].upper() + mem[1:]
    mem = re.sub(r'\\bi\\b', 'I', mem)
    
    result = None

    # Direct pattern matching with case-insensitive prefix stripping
    lower = mem.lower()
    
    # "I was born X"
    if lower.startswith("i was born"):
        result = "You were born" + mem[len("I was born"):]

    # "I live X"
    elif lower.startswith("i live"):
        result = "You " + mem[2:]

    # "I work X"
    elif lower.startswith("i work"):
        result = "You " + mem[2:]

    # "I am from X"
    elif lower.startswith("i am from"):
        result = "You are from" + mem[len("I am from"):]

    # "I am X"
    elif lower.startswith("i am "):
        result = "You are " + mem[5:]

    # "I like/love/enjoy X"
    elif any(lower.startswith(p) for p in ["i like ", "i love ", "i enjoy "]):
        result = "You " + mem[2:]

    # "I have X"
    elif lower.startswith("i have "):
        result = "You have " + mem[7:]

    # "I speak X"
    elif lower.startswith("i speak "):
        result = "You speak " + mem[8:]

    # "I drive X"
    elif lower.startswith("i drive "):
        result = "You drive " + mem[8:]

    # "My name is X"
    elif lower.startswith("my name is "):
        result = "Your name is " + mem[11:]

    # "My favorite X is Y"
    elif lower.startswith("my favorite") and " is " in lower:
        parts = lower.split(" is ", 1)
        if len(parts) == 2:
            prop = parts[0].replace("my favorite ", "").strip()
            val_mem = mem.split(" is ", 1)[1] if " is " in mem else parts[1]
            if prop:
                result = f"Your favorite {prop} is {val_mem}"

    # "My X name is Y"
    elif " name is " in lower and lower.startswith("my "):
        before = lower.replace("my ", "", 1)
        if before.endswith(" name is"):
            prop = before.replace(" name is", "").strip()
            val_mem = mem.split(" name is ", 1)[1] if " name is " in mem else ""
            if prop and prop != "name":
                result = f"Your {prop} name is {val_mem}"
        elif " name is " in before:
            prop = before.split(" name is ")[0].strip()
            val_mem = mem.split(" name is ", 1)[1] if " name is " in mem else ""
            if prop:
                result = f"Your {prop} name is {val_mem}"

    # "My X is Y" (generic, but only for nouns not already handled)
    elif lower.startswith("my ") and " is " in lower:
        before = lower.replace("my ", "", 1)
        prop = before.split(" is ")[0].strip()
        val_mem = mem.split(" is ", 1)[1] if " is " in mem else ""
        if prop and prop not in ("", "name", "favorite"):
            result = f"Your {prop} is {val_mem}"

    # Generic "I X"
    elif lower.startswith("i ") and len(mem) > 3:
        result = "You " + mem[2:]

    if result:
        if result.startswith("You was "):
            result = "You were" + result[7:]
        if not result.endswith(('.', '!', '?')):
            result += '.'

    return result
def anti_echo_check(answer):
    """
    Verify the final answer is clean.
    Returns True if answer passes anti-echo rules.
    """
    if not answer:
        return False

    bad_patterns = [
        "memory_search", "saved knowledge", "debug:", "From my stored",
        '"memory"', '"lessons"', "'memory'",
    ]
    for bp in bad_patterns:
        if bp in answer:
            return False

    return True
