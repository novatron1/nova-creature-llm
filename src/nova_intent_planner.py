"""
Nova Intent Planner — LLM-First Architecture
=============================================
Uses the local LLM to interpret user intent BEFORE routing.
The LLM is smarter at understanding natural language but is constrained to JSON output.
Nova retains full control over execution, memory, and validation.

Flow:
  user_message → normalize → LLM planner → structured JSON plan → Nova validator
"""

import json, os, sys, re
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# ─── Planner Prompt Template ───────────────────────────────────────────────

PLANNER_PROMPT = """You are the intent planner for Nova Creature. Your job is to interpret the user's message and return ONLY valid JSON.

Rules:
- Return ONLY a single JSON object. No text before or after.
- Do not invent facts the user didn't say.
- If unsure, use route "unknown" with low confidence.
- "slot_needed" should identify the specific info the user is asking about (e.g., "favorite_food", "birth_year", "name", "location", "dog_name", "cat_name", "custom_slot", null).
- For memory write commands like "long-term remember this: X" or "remember this: X", use route "memory_write".
- For "show long-term memory" use route "memory_recall".
- For dictionary lookups like "define X" or "what does X mean", use route "dictionary_lookup".
- For math like "2 x 2" or "what is 5+3", use route "math_solver".
- For simple direct questions about saved facts, use route "memory_recall".
- For general chat that doesn't fit other routes, use route "general_conversation".
- "needs_llm_synthesis": true only when the answer requires creative generation (explanations, definitions, coding, chat).
- "needs_llm_synthesis": false for direct memory recall or simple math.

Valid routes: memory_recall, memory_write, dictionary_lookup, math_solver, weather_lookup, web_search, coding_help, general_conversation, planning, feedback, unknown

User message: {user_message}

JSON:"""


def _call_llm_planner(user_message, timeout=2):
    """Call the local LLM and return the raw response."""
    try:
        from nova_local_llm_connector import LocalLLMConnector as NovaLocalLLMConnector, HAS_HTTPX
        llm = NovaLocalLLMConnector()
        # Quick availability check before full generate
        try:
            import httpx
            base_url = llm.config.url.rsplit("/api", 1)[0] if "/api" in llm.config.url else llm.config.url
            resp = httpx.get(base_url, timeout=1.0)
            if resp.status_code >= 500:
                return None
        except Exception:
            return None  # LLM not available, skip to deterministic
        prompt = PLANNER_PROMPT.format(user_message=user_message)
        # Generate with the formatted prompt as context
        from nova_local_llm_connector import LocalLLMResponse
        # Build context dict properly
        context = {
            "user_message": user_message,
            "normalized_message": user_message,
            "selected_route": "planner",
            "task_instruction": "Return a JSON plan with route, intent, slot_needed, needs_memory, needs_dictionary, needs_math, needs_weather, needs_web, needs_llm_synthesis, answer_style, and confidence."
        }
        response = llm.generate(context)
        if response and response.local_llm_used and response.raw_output:
            return response.raw_output.strip()
        return None
    except ImportError:
        return None
    except Exception as e:
        return None


def _try_parse_json(raw):
    """Try to extract and parse JSON from LLM output."""
    if not raw:
        return None

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find JSON between backticks
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find { ... } in the text
    m = re.search(r'(\{.*\})', raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    return None


DEFAULT_PLAN = {
    "route": "general_conversation",
    "intent": "fallback - planner unavailable",
    "slot_needed": None,
    "answer_style": "short_answer",
    "needs_memory": False,
    "needs_dictionary": False,
    "needs_math": False,
    "needs_weather": False,
    "needs_web": False,
    "needs_tool": False,
    "needs_llm_synthesis": True,
    "confidence": 0.0,
}


def plan(user_message, force_llm=True):
    """
    Plan the user's intent.

    Args:
        user_message: The raw user message string.
        force_llm: If True, always try LLM. If False, use fast deterministic patterns first.

    Returns:
        dict: The plan JSON with route, intent, slots, etc.
    """
    start_time = datetime.now()

    # Try LLM planner
    llm_planner_used = False
    if force_llm:
        raw = _call_llm_planner(user_message)
        parsed = _try_parse_json(raw) if raw else None

        if parsed and isinstance(parsed, dict) and "route" in parsed:
            parsed["_planner_used"] = "llm"
            parsed["_planner_raw"] = raw
            parsed["_planner_timestamp"] = start_time.isoformat()
            llm_planner_used = True
            return parsed

    # Fast-path deterministic patterns (when LLM is unavailable or slow)
    q = user_message.lower().strip()

    # Memory write commands
    for prefix in ["long-term remember this: ", "remember this long term: ",
                   "save this to long-term memory: ", "always remember: "]:
        if q.startswith(prefix):
            content = user_message[len(prefix):]
            slot = _infer_slot(content)
            return {
                "route": "memory_write",
                "intent": f"save long-term memory: {content[:80]}",
                "slot_needed": slot,
                "answer_style": "confirmation",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": False,
                "confidence": 0.95,
                "_planner_used": "deterministic_fast_path",
                "_planner_timestamp": start_time.isoformat(),
            }

    # Show / forget / edit memory
    if q in ("show long-term memory", "show long term memory", "show memory"):
        return {
            "route": "memory_recall",
            "intent": "show all saved long-term memory",
            "slot_needed": None,
            "answer_style": "list",
            "needs_memory": True,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.98,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
            "needs_web": False,
        }

    # Forget command
    if q.startswith("forget ") or "forget this" in q:
        return {
            "route": "memory_write",
            "intent": "forget long-term memory",
            "slot_needed": "custom_slot",
            "answer_style": "confirmation",
            "needs_memory": True,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.90,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
            "needs_web": False,
        }

    # Save name pattern
    name_save = re.search(r'my name is (.+)', q)
    if name_save:
        name_val = name_save.group(1).strip()
        return {
            "route": "memory_write",
            "intent": f"save name: {name_val}",
            "slot_needed": "name",
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    # Profile fact patterns — save to memory (name, favorites, birth, location, work, origin)
    profile_fact = re.search(r'my favorite (\w+) is (.+)', q)
    if profile_fact:
        prop = profile_fact.group(1)
        val = profile_fact.group(2).strip().rstrip('.!?,')
        return {
            "route": "memory_write",
            "intent": f"save favorite {prop}: {val}",
            "slot_needed": "favorite_" + prop,
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    if re.search(r'i was born', q):
        return {
            "route": "memory_write",
            "intent": "save birth info",
            "slot_needed": "birth_year",
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    if re.search(r'i live in', q):
        return {
            "route": "memory_write",
            "intent": "save location",
            "slot_needed": "location",
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    if re.search(r'i work (?:at|for)', q):
        return {
            "route": "memory_write",
            "intent": "save workplace",
            "slot_needed": "workplace",
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    if re.search(r'(?:i am from|i. m from)', q):
        return {
            "route": "memory_write",
            "intent": "save origin",
            "slot_needed": "origin",
            "answer_style": "confirmation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": "now",
        }

    # Memory recall questions (deterministic patterns) — must come before dictionary/math
    recall_patterns = [
        (r"what(?:'s| is)? my name", "name", "second_person_direct", 0.97),
        (r"where (?:do|am) i live", "location", "second_person_direct", 0.97),
        (r"when (?:was|am) i born", "birth_year", "second_person_direct", 0.97),
        (r"where (?:do|am) i from", "origin", "second_person_direct", 0.97),
        (r"where do i work", "workplace", "second_person_direct", 0.97),
        (r"what(?:'s| is| are) my favorite \w+", None, "second_person_direct", 0.95),
        (r"what (?:do|does) i like", "likes", "second_person_direct", 0.95),
        (r"what (?:do|does) i love", "likes", "second_person_direct", 0.95),
        (r"what(?:'s| is| are) my \w+ name", "pet_name", "second_person_direct", 0.90),
        (r"who am i", "name", "second_person_direct", 0.90),
        (r"what.*research", "research_field", "second_person_direct", 0.90),
        (r"what food", "favorite_food", "second_person_direct", 0.90),
        (r"what color", "favorite_color", "second_person_direct", 0.90),
    ]
    for pattern, slot, style, conf in recall_patterns:
        if re.search(pattern, q):
            return {
                "route": "memory_recall",
                "intent": f"recall saved user information",
                "slot_needed": slot,
                "answer_style": style,
                "needs_memory": True,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": False,
                "needs_web": False,
                "needs_tool": False,
                "needs_llm_synthesis": False,
                "confidence": conf,
                "_planner_used": "deterministic_fast_path",
                "_planner_timestamp": start_time.isoformat(),
            }

    # Dictionary lookups — use strict pattern (not "what is" which overlaps with memory)
    dict_match = re.match(r'(?:define|what does|meaning of)\s+(.+?)(?:\?)?$', q)
    if dict_match:
        return {
            "route": "dictionary_lookup",
            "intent": f"define {dict_match.group(1)}",
            "slot_needed": None,
            "answer_style": "short_definition",
            "needs_memory": False,
            "needs_dictionary": True,
            "needs_math": False,
            "needs_weather": False,
            "needs_tool": False,
            "needs_llm_synthesis": True,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
            "needs_web": False,
        }

        # Weather detection (current weather, not memory)
    weather_keywords = ["weather in ", "weather at ", "weather for ", "temperature in ",
                       "what is the weather", "whats the weather",
                       "how cold ", "how hot ", "how warm "]
    for wk in weather_keywords:
        if wk in q:
            return {
                "route": "weather_lookup",
                "intent": "get current weather",
                "slot_needed": None,
                "answer_style": "short_answer",
                "needs_memory": False,
                "needs_dictionary": False,
                "needs_math": False,
                "needs_weather": True,
                "needs_web": True,
                "needs_tool": False,
                "needs_llm_synthesis": True,
                "confidence": 0.95,
                "_planner_used": "deterministic_fast_path",
                "_planner_timestamp": start_time.isoformat(),
            }

    # Also detect storm/rain/snow/hot/cold/windy as weather questions
    weather_symptoms = ["rain", "snow", "storm", "windy", "humid", "forecast"]
    if any(w in q for w in weather_symptoms):
        return {
            "route": "weather_lookup",
            "intent": "get current weather",
            "slot_needed": None,
            "answer_style": "short_answer",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": True,
            "needs_web": True,
            "needs_tool": False,
            "needs_llm_synthesis": True,
            "confidence": 0.85,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
        }
    

    # Web search detection (current/latest/recent/news)
    if ("current" in q or "latest" in q or "recent" in q or "news" in q or "today" in q
        or "this week" in q or "this year" in q or "live" in q or "breaking" in q
        or "2025" in q or "2026" in q or "2027" in q
        or "recently" in q or "upcoming" in q or "forecast" in q):
        return {
            "route": "web_search",
            "intent": "search the web for current information",
            "slot_needed": None,
            "answer_style": "explanation",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": False,
            "needs_weather": False,
            "needs_web": True,
            "needs_tool": False,
            "needs_llm_synthesis": True,
            "confidence": 0.88,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
        }

    # Math detection
    math_match = re.search(r'(\d+\s*[\+\-\*xX/]\s*\d+)', q)
    if math_match:
        return {
            "route": "math_solver",
            "intent": "solve math",
            "slot_needed": None,
            "answer_style": "short_answer",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_math": True,
            "needs_weather": False,
            "needs_tool": False,
            "needs_llm_synthesis": False,
            "confidence": 0.95,
            "_planner_used": "deterministic_fast_path",
            "_planner_timestamp": start_time.isoformat(),
            "needs_web": False,
        }

    # Default: general conversation
    return {
        "route": "general_conversation",
        "intent": "general response",
        "slot_needed": None,
        "answer_style": "short_answer",
        "needs_memory": False,
        "needs_dictionary": False,
        "needs_math": False,
        "needs_weather": False,
        "needs_tool": False,
        "needs_llm_synthesis": True,
        "confidence": 0.50,
        "_planner_used": "deterministic_fast_path" if not llm_planner_used else "llm",
        "_planner_timestamp": start_time.isoformat(),
        "needs_web": False,
    }


def _infer_slot(text):
    """Try to infer which slot a memory write targets."""
    t = text.lower()
    if "favorite food" in t or "favourite food" in t or "like to eat" in t:
        return "favorite_food"
    if "born" in t or "birth" in t:
        return "birth_year"
    if "live" in t or "living" in t or "address" in t:
        return "location"
    if "name" in t and ("my" in t or "is " in t):
        return "name"
    if "work" in t or "job" in t or "employ" in t:
        return "workplace"
    if "from" in t and ("am" in t or "origin" in t):
        return "origin"
    if "color" in t or "colour" in t:
        return "favorite_color"
    if "dog" in t or "cat" in t or "pet" in t:
        return "pet_name"
    if "like" in t or "love" in t or "hobby" in t:
        return "likes"
    return "custom_slot"
