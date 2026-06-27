"""
Nova Cognitive OS v1 — Brain-Flip Router
=========================================
Implements the new architecture:

  1. LLM Planner Pass (interpret intent)
  2. Nova Plan Validator (Nova stays boss)
  3. Nova Memory/Dictionary/Tool Retrieval
  4. Nova Context Builder
  5. Direct Answer (if possible) OR LLM Synthesis Pass
  6. Nova Critic / Anti-Echo Check
  7. Final clean answer
  8. Memory / feedback / training log save

This wraps the original hybrid router so existing features still work.
"""

import json, os, sys, time, traceback
from datetime import datetime



ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

# ─── Import nova_hybrid_router for fallback ───
_HYBRID_AVAIL = False
_HYBRID_ROUTER = None
_WEB_CONNECTOR = None
try:
    import nova_hybrid_router as _HYBRID_ROUTER
    _HYBRID_AVAIL = True
except Exception as e:
    pass

# ─── Config ───
CONFIG = {
    "require_sources": True,
}

# ─── Conversation context (follow-up questions) ───
_LAST_DEFINED_WORD = ""
_LAST_DEFINITION = ""

# ─── Built-in dictionary word list (fast offline lookup) ───
_BUILTIN_DICT = {}  # Loaded from file below

# Load dictionary from file (if available)
_dict_path = os.path.join(ROOT, "data", "builtin_word_dictionary.json")
if os.path.exists(_dict_path):
    try:
        with open(_dict_path) as _f:
            _loaded = json.load(_f)
            if isinstance(_loaded, dict):
                _BUILTIN_DICT = _loaded
    except Exception:
        pass

def _builtin_dict_lookup(message):
    import re
    global _LAST_DEFINED_WORD, _LAST_DEFINITION
    """Fast built-in dictionary lookup. Does not require network or LLM."""
    if not message:
        return None
    q = message.lower().strip()
    # Check for "define X" or "what is X" or "what does X mean"
    word = None
    for prefix in ["define ", "what is ", "what are ", "what does ", "what do "]:
        if q.startswith(prefix):
            word = q[len(prefix):].strip().rstrip(".?!,;:")
            # Remove trailing " mean" or " means"
            word = re.sub(r'\s+mean(s)?$', '', word)
            break
    
    if not word:
        # Try direct match on common words
        words = q.split()
        for w in words:
            if w in _BUILTIN_DICT and len(w) > 2:
                word = w
                break
    
    if word:
        # Exact match
        if word in _BUILTIN_DICT:
            _LAST_DEFINED_WORD = word
            _LAST_DEFINITION = _BUILTIN_DICT[word]
            return _BUILTIN_DICT[word]
        # Partial match
        for key, val in _BUILTIN_DICT.items():
            if word in key or key in word:
                _LAST_DEFINED_WORD = key
                _LAST_DEFINITION = val
                return val
    
    return None

# ─── Lazy imports for brain-flip modules ───
_PLANNER = None
_VALIDATOR = None
_LTM = None
_SLOT_RETRIEVAL = None
_SYNTHESIZER = None
_CONTEXT_BUILDER = None
_LLM_SYNTH = None


def _lazy_import(module_name):
    """Lazy import a brain-flip module."""
    try:
        return __import__(module_name)
    except Exception:
        return None


def _get_planner():
    global _PLANNER
    if _PLANNER is None:
        _PLANNER = _lazy_import("nova_intent_planner")
    return _PLANNER


def _get_validator():
    global _VALIDATOR
    if _VALIDATOR is None:
        _VALIDATOR = _lazy_import("nova_plan_validator")
    return _VALIDATOR


def _get_ltm():
    global _LTM
    if _LTM is None:
        _LTM = _lazy_import("nova_long_term_memory")
    return _LTM


def _get_slot_retrieval():
    global _SLOT_RETRIEVAL
    if _SLOT_RETRIEVAL is None:
        _SLOT_RETRIEVAL = _lazy_import("nova_memory_slot_retrieval")
    return _SLOT_RETRIEVAL


def _get_answer_synthesizer():
    global _SYNTHESIZER
    if _SYNTHESIZER is None:
        _SYNTHESIZER = _lazy_import("nova_answer_synthesizer")
    return _SYNTHESIZER


def _get_context_builder():
    global _CONTEXT_BUILDER
    if _CONTEXT_BUILDER is None:
        _CONTEXT_BUILDER = _lazy_import("nova_context_builder")
    return _CONTEXT_BUILDER


def _get_llm_synth():
    global _LLM_SYNTH

def _get_web():
    global _WEB_CONNECTOR
    if _WEB_CONNECTOR is None:
        _WEB_CONNECTOR = _lazy_import("nova_web_connector")
    return _WEB_CONNECTOR
    if _LLM_SYNTH is None:
        _LLM_SYNTH = _lazy_import("nova_llm_synthesizer")
    return _LLM_SYNTH


def _log_training(user_message, final_answer, plan, extras=None):
    """Log the interaction to training logs."""
    try:
        log_dir = os.path.join(ROOT, "nova_training_logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "cognitive_os_logs.jsonl")
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_message": user_message,
            "final_answer": final_answer,
            "route": plan.get("route", "unknown"),
            "planner_used": plan.get("_planner_used", "unknown"),
            "planner_validated": plan.get("_planner_validated", False),
        }
        if extras:
            entry.update(extras)
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def route(message, dict_lookup_fn=None, memory=None):
    """
    Main entry point for the brain-flip architecture.

    Args:
        message: user message string.
        dict_lookup_fn: optional dictionary lookup function.
        memory: optional legacy memory dict.

    Returns:
        (response_string, trace_dict)
    """
    start_time = time.time()
    trace = {
        "input": message,
        "timestamp": datetime.now().isoformat(),
        "cognitive_os": True,
        "planner_used": False,
        "planner_json_valid": False,
        "validated_route": None,
        "slot_needed": None,
        "long_term_memory_used": False,
        "memory_id": None,
        "memory_retrieved": False,
        "local_llm_synthesis_used": False,
        "critic_result": None,
        "long_term_memory_used": False,
        "long_term_memory_saved": False,
        "memory_id": None,
        "memory_source": None,
        "extracted_slot": None,
        "extracted_value": None,
        "memory_command_detected": False,
        "memory_action": "none",
        "web_used": False,
        "web_query": None,
        "web_provider": None,
        "sources_found": 0,
        "urls_used": [],
        "final_answer_clean": True,
        "training_log_saved": False,
        "fallback_used": False,
        "route_path": [],
        "skills": [],
        "confidence": 0.0,
        "memory_event": None,
        "permission": None,
        "domain": None,
    }

    # ═══════════════════════════════════════════════
    # STEP 0: Long-Term Memory Command Detection
    # ═══════════════════════════════════════════════
    ltm = _get_ltm()
    ltm_command = "none"
    ltm_payload = message
    if ltm:
        try:
            ltm_command, ltm_payload = ltm.detect_command(message)
            trace["memory_command_detected"] = (ltm_command != "none")
            trace["memory_action"] = ltm_command
        except Exception:
            pass
    
    # Handle show memory directly
    if ltm_command == "show" and ltm:
        try:
            summary = ltm.format_summary()
            trace["long_term_memory_used"] = True
            trace["memory_source"] = "long_term"
            trace["skills"] = ["long_term_memory", "show"]
            trace["confidence"] = 0.98
            return summary, trace
        except Exception as e:
            pass
    
    # Handle save memory directly
    if ltm_command == "save" and ltm and ltm_payload:
        try:
            record = ltm.add_memory(ltm_payload, source_command="long_term")
            if record:
                trace["long_term_memory_used"] = True
                trace["long_term_memory_saved"] = True
                trace["memory_id"] = record.get("memory_id", "")
                trace["memory_source"] = "long_term"
                trace["extracted_slot"] = record.get("extracted_slot", "")
                trace["extracted_value"] = record.get("extracted_value", "")
                trace["memory_event"] = f"memory_saved:ltm:{record.get('extracted_slot')}={record.get('extracted_value')}"
                
                # Generate clean confirmation
                slot = record.get("extracted_slot", "").replace("_", " ")
                val = record.get("extracted_value", "")
                from nova_answer_synthesizer import synthesize_from_fact
                confirmation = synthesize_from_fact(record.get("raw_text", ""))
                if confirmation:
                    answer = f"I'll remember long-term that {confirmation[0].lower() + confirmation[1:]}"
                else:
                    answer = f"Saved long-term: your {slot} is {val}."
                
                trace["skills"] = ["long_term_memory", "save"]
                trace["confidence"] = 0.98
                return answer, trace
        except Exception as e:
            trace["_error"] = f"ltm_save_error: {e}"
    
    # Handle forget memory
    if ltm_command == "forget" and ltm:
        try:
            q = ltm_payload if ltm_payload else ""
            count = ltm.forget_by_query(q if q else "all")
            trace["long_term_memory_used"] = True
            trace["memory_event"] = f"memory_forgot:{count}_records"
            answer = f"I've forgotten {count} long-term memory record{'s' if count != 1 else ''} matching that."
            if count == 0:
                answer = "I couldn't find any saved memory matching that."
            trace["skills"] = ["long_term_memory", "forget"]
            trace["confidence"] = 0.95
            return answer, trace
        except Exception as e:
            trace["_error"] = f"ltm_forget_error: {e}"
    
    # Handle edit memory
    if ltm_command == "edit" and ltm and " -> " in ltm_payload:
        try:
            parts = ltm_payload.split(" -> ", 1)
            old_part = parts[0].strip()
            new_text = parts[1].strip()
            record, old_val, new_val = ltm.edit_memory(old_part, new_text)
            if record:
                trace["long_term_memory_used"] = True
                trace["memory_id"] = record.get("memory_id", "")
                trace["extracted_slot"] = record.get("extracted_slot", "")
                trace["extracted_value"] = record.get("extracted_value", "")
                trace["memory_event"] = f"memory_edited:{record.get('extracted_slot')}:{old_val}->{new_val}"
                answer = f"Updated your {record.get('extracted_slot', 'memory').replace('_', ' ')} from '{old_val}' to '{new_val}'."
                trace["skills"] = ["long_term_memory", "edit"]
                trace["confidence"] = 0.95
                return answer, trace
        except Exception as e:
            trace["_error"] = f"ltm_edit_error: {e}"

    # ═══════════════════════════════════════════════
    # STEP 1: LLM Planner Pass
    # ═══════════════════════════════════════════════
    planner = _get_planner()
    validator = _get_validator()
    slot_retrieval = _get_slot_retrieval()
    answer_synth = _get_answer_synthesizer()
    context_builder = _get_context_builder()
    llm_synth = _get_llm_synth()
    web_connector = _get_web()

    plan = None
    validated_plan = None

    try:
        if planner:
            plan = planner.plan(message, force_llm=False)
            if plan:
                trace["planner_used"] = plan.get("_planner_used", "llm")
        else:
            plan = None
    except Exception as e:
        trace["_error"] = f"planner_error: {e}"
        plan = None

    # ═══════════════════════════════════════════════
    # STEP 2: Nova Plan Validator
    # ═══════════════════════════════════════════════
    try:
        if validator and plan:
            vresult = validator.validate(plan, raw_user_message=message)
            trace["planner_json_valid"] = vresult.ok
            if vresult.ok:
                validated_plan = vresult.plan
                validated_plan["_planner_validated"] = True
            else:
                # Fallback plan from validator
                if _HYBRID_AVAIL:
                    validated_plan = validator.make_fallback_plan(message)
                    trace["fallback_used"] = True
                else:
                    validated_plan = plan  # Use original as best effort
                trace["planner_json_valid"] = False
        else:
            validated_plan = None
    except Exception as e:
        trace["_error"] = f"validator_error: {e}"
        validated_plan = None

    if not validated_plan:
        validated_plan = {
            "route": "general_conversation",
            "intent": "fallback - no planner",
            "slot_needed": None,
            "answer_style": "short_answer",
            "needs_memory": False,
            "needs_dictionary": False,
            "needs_llm_synthesis": True,
            "confidence": 0.5,
            "_planner_used": "none",
        }
        trace["fallback_used"] = True

    route_name = validated_plan.get("route", "general_conversation")
    slot_needed = validated_plan.get("slot_needed")
    trace["validated_route"] = route_name
    trace["slot_needed"] = slot_needed
    trace["route_path"] = [route_name]


    # ═══════════════════════════════════════════════
    # STEP 2b: Memory Write Handler (save to LTM)
    # ═══════════════════════════════════════════════
    if validated_plan and validated_plan.get("route") == "memory_write" :
        slot = validated_plan.get("slot_needed", "custom")
        # If the original message has the info, save it as LTM
        if ltm:
            record = ltm.add_memory(message, source_command="memory_write")
            if record:
                trace["long_term_memory_used"] = True
                trace["long_term_memory_saved"] = True
                trace["memory_id"] = record.get("memory_id", "")
                trace["memory_source"] = "long_term"
                trace["extracted_slot"] = record.get("extracted_slot", "")
                trace["extracted_value"] = record.get("extracted_value", "")
                slot_name = record.get("extracted_slot", "custom").replace("_", " ")
                val = record.get("extracted_value", "")
                if slot_name and val:
                    from nova_answer_synthesizer import synthesize_from_fact
                    syn = synthesize_from_fact(record.get("raw_text", ""))
                    if syn:
                        final_answer = f"I'll remember that. {syn}"
                    else:
                        final_answer = f"Saved: your {slot_name} is {val}."
                else:
                    final_answer = "I've noted that."
                
                trace["skills"] = ["long_term_memory", "memory_write"]
                trace["confidence"] = 0.95
                return final_answer, trace
    # ═══════════════════════════════════════════════
    # STEP 3: Memory / Dictionary / Tool Retrieval
    # ═══════════════════════════════════════════════
    memory_result = None
    dictionary_result = None
    math_result = None

    # Memory retrieval
    if validated_plan.get("needs_memory") and slot_retrieval:
        try:
            memory_result = slot_retrieval.retrieve(
                validated_plan, legacy_memory=memory, raw_user_message=message
            )
            if memory_result.get("found"):
                trace["memory_retrieved"] = True
                trace["long_term_memory_used"] = (memory_result["source"] == "long_term")
                trace["memory_source"] = memory_result.get("source", "none")
                trace["extracted_slot"] = memory_result.get("slot_used", "")
                trace["extracted_value"] = memory_result.get("value", "")
                if memory_result.get("records"):
                    mid = memory_result["records"][0].get("memory_id")
                    if mid:
                        trace["memory_id"] = mid
                trace["memory_event"] = f"retrieved:{memory_result['source']}:{memory_result.get('slot_used')}"
        except Exception as e:
            trace["_error"] = f"memory_retrieval_error: {e}"

    # Dictionary lookup
    if validated_plan.get("needs_dictionary"):
        # Use built-in dictionary first (instant, no network)
        try:
            dict_result = _builtin_dict_lookup(message)
        except Exception:
            dict_result = None
        # Fall back to provided dict_lookup_fn if available
        if not dict_result and dict_lookup_fn:
            try:
                dict_result = dict_lookup_fn(message)
            except Exception:
                pass
        if dict_result:
            dictionary_result = dict_result

    # Math solver (quick deterministic)
    if validated_plan.get("needs_math"):
        try:
            import re
            q = message.lower().strip()
            m = re.search(r'(\d+)\s*[\+\-\*xX/]\s*(\d+)', q)
            if m:
                a, b = int(m.group(1)), int(m.group(2))
                if 'x' in m.group(0).lower() or '*' in m.group(0).lower():
                    math_result = a * b
                elif '/' in m.group(0):
                    math_result = a / b if b != 0 else "undefined"
                elif '-' in m.group(0):
                    math_result = a - b
                else:
                    math_result = a + b
        except Exception:
            pass

    trace["skills"] = [route_name]
    if memory_result and memory_result.get("found"):
        trace["skills"].append("memory_lookup")
    if dictionary_result:
        trace["skills"].append("dictionary_lookup")

    # ═══════════════════════════════════════════════
    # STEP 3c: Web Search
    # ═══════════════════════════════════════════════
    web_result = None
    if validated_plan.get("needs_web") and web_connector:
        try:
            web_query = message
            # For weather, prepend "current weather"
            if route_name == "weather_lookup":
                web_query = "current weather " + message
            web_result = web_connector.search(web_query)
            trace["web_used"] = web_result.get("success", False)
            trace["web_query"] = web_query
            trace["web_provider"] = web_result.get("provider", "unknown")
            trace["sources_found"] = len(web_result.get("results", []))
            trace["urls_used"] = [r.get("url", "") for r in web_result.get("results", [])[:3]]
            if web_result.get("success"):
                trace["skills"].append("web_search")
                trace["memory_event"] = f"web_search:{len(web_result.get('results',[]))}_sources"
        except Exception as e:
            trace["_error"] = f"web_search_error: {e}"
            web_result = {"success": False, "error": str(e), "results": []}

    # ═══════════════════════════════════════════════
    # STEP 4: Direct Answer or LLM Synthesis
    # ═══════════════════════════════════════════════
    final_answer = None
    llm_synthesis_used = False

    # Try direct answer first
    if answer_synth:
        try:
            direct_answer, used_direct = answer_synth.try_direct_answer(
                validated_plan, memory_result or {},
                dictionary_result, math_result
            )
            if used_direct and direct_answer:
                final_answer = direct_answer
                trace["local_llm_synthesis_used"] = False
                trace["confidence"] = 0.92
                trace["skills"].append("direct_answer")
        except Exception:
            pass

    # If no direct answer and memory recall returned nothing, answer directly
    if not final_answer and route_name == "memory_recall":
        slot = validated_plan.get("slot_needed", "")
        if slot and slot not in ("null", None):
            final_answer = f"I don't have your {slot.replace('_', ' ')} saved yet."
            trace["confidence"] = 0.85
            trace["skills"].append("memory_not_found")
        else:
            final_answer = "I don't have that information saved yet."
            trace["confidence"] = 0.85
            trace["skills"].append("memory_not_found")

    # If no direct answer, try LLM synthesis
    if not final_answer and validated_plan.get("needs_llm_synthesis"):
        if context_builder and llm_synth:
            try:
                # Build context with web results if available
                web_context = ""
                if web_result and web_result.get("success"):
                    web_context = web_connector.format_results(web_result) if web_connector else ""
                
                context_packet = context_builder.build(
                    message,
                    validated_plan,
                    memory_result=memory_result or {},
                    dictionary_result=dictionary_result,
                    math_result=math_result,
                    web_result=web_context,
                )
                llm_response, llm_ok, llm_error = llm_synth.generate(context_packet)
                if llm_ok and llm_response:
                    final_answer = llm_response
                    llm_synthesis_used = True
                    trace["local_llm_synthesis_used"] = True
                    trace["confidence"] = 0.88
                    trace["skills"].append("llm_synthesis")
            except Exception as e:
                trace["_error"] = f"llm_synthesis_error: {e}"

    # ═══════════════════════════════════════════════
    # STEP 5: Nova Critic / Anti-Echo Check
    # ═══════════════════════════════════════════════
    critic_passed = True
    if final_answer and answer_synth:
        try:
            critic_passed = answer_synth.anti_echo_check(final_answer)
            trace["critic_result"] = "passed" if critic_passed else "rejected"
        except Exception:
            critic_passed = True

    if not critic_passed:
        # Try fallback answer
        try:
            fallback = answer_synth.fallback_answer(validated_plan, memory_result or {})
            final_answer = fallback
            trace["fallback_used"] = True
        except Exception:
            pass

    trace["final_answer_clean"] = critic_passed

    # Follow-up question handler (uses last dictionary definition as context)
    if not final_answer and route_name == "general_conversation" and _LAST_DEFINED_WORD and _LAST_DEFINITION:
        q = message.lower().strip()
        # Check if question references the last defined word
        lw = _LAST_DEFINED_WORD.lower()
        ref_words = [lw] + lw.split()
        is_about_last_word = any(rw in q and rw != "" for rw in ref_words if len(rw) > 2)
        
        if is_about_last_word:
            # Use the definition to answer the follow-up
            defn = _LAST_DEFINITION
            # Build a contextual answer
            if q.startswith("what") or q.startswith("why") or q.startswith("how") or q.startswith("where") or q.startswith("when"):
                final_answer = f"Based on the definition: {defn}"
                trace["confidence"] = 0.92
                trace["skills"] = ["dictionary_context", "follow_up"]
            elif q.startswith("are") or q.startswith("is") or q.startswith("do") or q.startswith("does") or q.startswith("can"):
                # Yes/no questions
                def_lower = defn.lower()
                yes_indicators = ["yes", "can", "do", "is", "are", "have", "known", "often", "typically", "usually"]
                has_yes = any(ind in def_lower for ind in yes_indicators)
                if has_yes:
                    final_answer = f"Yes. {defn}"
                else:
                    final_answer = f"Based on the definition of {_LAST_DEFINED_WORD}: {defn}"
                trace["confidence"] = 0.90
                trace["skills"] = ["dictionary_context", "follow_up"]
            elif len(q.split()) <= 5 and lw in q:
                # Short query mentioning the word - restate definition
                final_answer = f"{_LAST_DEFINED_WORD.title()} is {defn[0].lower() + defn[1:]}" if defn[0].isupper() else f"{_LAST_DEFINED_WORD.title()} {defn}"
                trace["confidence"] = 0.88
                trace["skills"] = ["dictionary_context", "follow_up"]

    # Clean general response fallback (avoids garbled transformer output)
    if not final_answer and route_name == "general_conversation":
        general_greetings = {
            "hello": "Hello! How can I assist you today?",
            "hi": "Hi there! How can I help you?",
            "hey": "Hey! What can I do for you?",
        }
        q = message.lower().strip()
        if q in general_greetings:
            final_answer = general_greetings[q]
            trace["confidence"] = 0.95
            trace["skills"].append("greeting")
        elif "what can you do" in q or "capabilities" in q or "abilities" in q:
            final_answer = "I am Nova Creature, a multi-brain AI system with 7 specialized brain roles. I can help with coding, science, philosophy, psychology, creative tasks, learning, memory, and more. I have a live display face, long-term memory, and can search the web. Try asking me to define a word, solve a math problem, teach me something, or just have a conversation!"
            trace["confidence"] = 0.92
            trace["skills"].append("capabilities")
        elif "can you code" in q or "coding" in q or "program" in q:
            final_answer = "Yes, I can help with coding! My left hemisphere has programming knowledge. I can help with Python, JavaScript, and general software concepts. I can plan patches, write code, and run tests."
            trace["confidence"] = 0.90
            trace["skills"].append("coding_help")
        elif "science" in q or "water cycle" in q or "photosynthesis" in q or "evolution" in q:
            final_answer = "My science training covers physics, chemistry, biology, astronomy, and the scientific method. I can explain scientific concepts and help with science questions. Here are some key science topics I know about: The water cycle involves evaporation, condensation, and precipitation. Photosynthesis is how plants convert sunlight into energy. Evolution explains how species change over time through natural selection."
            trace["confidence"] = 0.90
            trace["skills"].append("science_help")
        elif "derivative" in q or "calculus" in q or "integral" in q:
            final_answer = "I have basic math knowledge covering arithmetic, algebra, and calculus concepts. For advanced calculus like derivatives, I can explain that the derivative of x^2 is 2x, which represents the rate of change. For specific problems, I recommend using a dedicated math tool."
            trace["confidence"] = 0.85
            trace["skills"].append("math_help")
        else:
            final_answer = "Hello! I'm Nova Creature, your multi-brain AI assistant. I have long-term memory, can define words, solve math, learn new things, code, and more. How can I help you today?"
            trace["confidence"] = 0.85
            trace["skills"].append("general_response")

    # ═══════════════════════════════════════════════
    # STEP 6: Fallback to original hybrid router
    # ═══════════════════════════════════════════════
    if not final_answer and _HYBRID_AVAIL and _HYBRID_ROUTER:
        try:
            legacy_response, legacy_trace = _HYBRID_ROUTER.route_and_respond(
                message, dict_lookup_fn=dict_lookup_fn, memory=memory
            )
            final_answer = legacy_response
            # Merge legacy trace fields
            for k in ["roles", "skills", "confidence", "memory_event", "domain", "route_path"]:
                if k in legacy_trace and not trace.get(k):
                    trace[k] = legacy_trace[k]
            trace["fallback_used"] = True
        except Exception as e:
            trace["_error"] = f"hybrid_fallback_error: {e}"

    # Append web source citations to final answer
    if final_answer and trace.get("web_used") and web_result and web_result.get("success"):
        citations = web_connector.make_source_citations(web_result) if web_connector else ""
        if citations and CONFIG.get("require_sources", True) if isinstance(CONFIG, dict) else True:
            final_answer = final_answer.rstrip() + citations

    # Ultimate fallback
    if not final_answer:
        final_answer = "I understand your message, but I'm not sure how to respond. Can you clarify?"
        trace["fallback_used"] = True

    # ═══════════════════════════════════════════════
    # STEP 7: Save to Training Log
    # ═══════════════════════════════════════════════
    try:
        _log_training(message, final_answer, validated_plan, {
            "llm_synthesis_used": llm_synthesis_used,
            "critic_passed": critic_passed,
            "memory_found": memory_result.get("found") if memory_result else False,
            "response_time": round(time.time() - start_time, 2),
        })
        trace["training_log_saved"] = True
    except Exception:
        pass

    trace["_elapsed"] = round(time.time() - start_time, 2)
    return final_answer, trace
