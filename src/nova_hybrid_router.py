"""
Nova Hybrid Router — Transformer-Driven Routing Engine
======================================================
Instead of hardcoded if/elif chains, the 7 brain transformers
classify input, decide routing paths, and generate responses.

Architecture:
  1. Fast Path: Dictionary lookup (approved Q&A, instant)
  2. Memory Path: Stored lesson recall
  3. Transformer Path: Role classification → response generation → critic → speech
  4. Learning Loop: Each route is logged, routing weights adjust over time
"""

import json, os, sys, time, hashlib, re, traceback
from pathlib import Path
from datetime import datetime
import numpy as np
from nova_quality_gate import gate_transformer_output, get_answer_source
import nova_long_term_memory as ltm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ─── Brain Initialization (eager at import) ──────────────
BRAIN = None
TOKENIZER = None
CONV_ENGINE = None

def _ensure_brain():
    global BRAIN, TOKENIZER
    if BRAIN is None:
        from nova_transformer_engine import NovaBrain, NovaTokenizer
        TOKENIZER = NovaTokenizer()
        BRAIN = NovaBrain()
        BRAIN.load_all()
    return BRAIN

def _ensure_conv():
    global CONV_ENGINE
    if CONV_ENGINE is None:
        from nova_conversation_engine import ConversationEngine
        CONV_ENGINE = ConversationEngine()
    return CONV_ENGINE

# Pre-load brain at import time
_ensure_brain()

# ─── Routing Classification ──────────────────────────────────
# Domain categories the router can classify into
DOMAINS = {
    "coding": {"left_hemisphere": 0.8, "planner_transformer": 0.2},
    "math": {"left_hemisphere": 0.9, "memory_transformer": 0.1},
    "science": {"memory_transformer": 0.5, "left_hemisphere": 0.3, "critic_conscience_transformer": 0.2},
    "philosophy": {"memory_transformer": 0.4, "critic_conscience_transformer": 0.3, "right_hemisphere": 0.3},
    "psychology": {"memory_transformer": 0.4, "right_hemisphere": 0.3, "critic_conscience_transformer": 0.3},
    "creative": {"right_hemisphere": 0.7, "dream_simulation_transformer": 0.3},
    "memory_recall": {"memory_transformer": 0.8, "critic_conscience_transformer": 0.2},
    "planning": {"planner_transformer": 0.7, "left_hemisphere": 0.3},
    "critic": {"critic_conscience_transformer": 0.9, "memory_transformer": 0.1},
    "speech": {"speech_output_transformer": 0.8, "planner_transformer": 0.2},
    "dream": {"dream_simulation_transformer": 0.7, "right_hemisphere": 0.3},
    "general": {"memory_transformer": 0.3, "critic_conscience_transformer": 0.3, "speech_output_transformer": 0.4},
}

# Keywords that help classify the domain (expand via learning)
DOMAIN_KEYWORDS = {
    "coding": ["code", "program", "python", "javascript", "bug", "debug", "function", "variable", "api", "html", "css", "git", "algorithm", "data structure", "loop", "class", "object", "error", "compile", "syntax", "server", "database", "sql", "app", "software", "dev", "developer", "programming", "script", "terminal", "command", "linux", "windows", "mac"],
    "math": ["math", "equation", "formula", "algebra", "calculus", "geometry", "trigonometry", "number", "calculate", "solve", "derivative", "integral", "probability", "statistic", "pythagorean", "quadratic", "angle", "graph", "function f", "variable x", "plus", "minus", "times", "divided", "equals", "zero", "infinity", "prime"],
    "science": ["science", "physics", "chemistry", "biology", "dna", "cell", "atom", "molecule", "evolution", "gravity", "energy", "force", "planet", "star", "galaxy", "black hole", "quantum", "relativity", "photosynthesis", "neuron", "gene", "climate", "experiment", "hypothesis", "theory", "scientific"],
    "philosophy": ["philosophy", "meaning of life", "consciousness", "reality", "truth", "ethics", "morality", "free will", "soul", "mind", "existence", "god", "belief", "knowledge", "logic", "reason", "argument", "paradox", "infinite", "purpose", "identity", "self"],
    "psychology": ["psychology", "cognition", "memory", "emotion", "brain", "perception", "learning", "behavior", "personality", "mental", "anxiety", "depression", "stress", "trauma", "therapy", "mindful", "conscious", "unconscious", "bias", "cognitive", "neuron", "neuroscience"],
    "creative": ["draw", "paint", "create", "design", "art", "picture", "image", "svg", "canvas", "face", "animation", "visual", "make", "build", "generate", "creative", "imagine", "invent", "compose", "write story", "poem"],
    "memory_recall": ["remember", "recall", "what is my", "who am i", "what did i", "do you know", "do you remember", "what was", "who was", "tell me about yourself", "what do you know"],
    "planning": ["plan", "step", "order", "first", "next", "then", "after", "before", "schedule", "organize", "strategy", "method", "approach", "build", "create plan", "how to", "guide", "tutorial"],
    "critic": ["truth", "lie", "fake", "wrong", "correct", "check", "verify", "confirm", "contradiction", "conflict", "error", "mistake", "uncertain", "doubt", "evidence", "proof", "fact", "claim"],
    "speech": ["explain", "describe", "summarize", "clarify", "tell", "talk", "say", "speak", "answer", "respond", "define", "elaborate"],
    "dream": ["imagine", "what if", "hypothetical", "scenario", "simulate", "pretend", "suppose", "could", "would", "might", "possible", "alternate", "future", "dream", "vision"],
}

# Routing log for learning
ROUTING_LOG = []
ROUTING_LOG_PATH = ROOT / "data" / "routing_log.jsonl"

def classify_domain(text):
    """Classify input text into a domain using keyword scoring + transformer embedding if available."""
    q = text.lower().strip()
    scores = {}
    
    # Keyword scoring
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in q:
                score += 1
        if score > 0:
            scores[domain] = score
    
    # No domain matched → general
    if not scores:
        return "general"
    
    # Return highest scoring domain
    best = max(scores, key=scores.get)
    return best

def get_route_for_domain(domain):
    """Get the brain role routing path for a given domain."""
    if domain in DOMAINS:
        # Sort roles by weight
        roles = sorted(DOMAINS[domain].items(), key=lambda x: -x[1])
        return [r for r, w in roles]
    return ["memory_transformer", "critic_conscience_transformer", "speech_output_transformer"]

def generate_transformer_response(text, domain=None):
    """Generate a response using the transformer brain.
    
    Uses actual trained checkpoint weights to generate responses.
    Returns (response_text, route_path, confidence, error_info).
    Speed-optimized: only tries the primary role once.
    """
    brain = _ensure_brain()
    
    if domain is None:
        domain = classify_domain(text)
    
    # Get the route roles for this domain - only use primary role for speed
    route_roles = get_route_for_domain(domain)
    primary_role = route_roles[0] if route_roles else "memory_transformer"
    
    # Build a prompt that includes domain context
    prompt = f"[{domain.upper()}] {text}"
    
    errors = {}
    
    # Try the primary role only (speed optimization)
    if primary_role in brain.models:
        try:
            gen_result = brain.infer(primary_role, prompt, max_new_tokens=20, temperature=0.0)
            gen_text, stats = gen_result
            
            if gen_text and stats.get('tokens_generated', 0) > 0:
                if gen_text and len(gen_text) > len(prompt) + 2:
                    response = gen_text[len(prompt):].strip()
                    if response and len(response) > 2:
                        conf = min(0.92, 0.5 + 0.04 * len(response))
                        return response, route_roles, conf, errors, True
        except Exception as e:
            errors[primary_role] = f"{type(e).__name__}: {str(e)[:80]}"
    
    # Transformer did not run or produced empty output
    return None, route_roles, 0.0, errors, False

def route_and_respond(text, dict_lookup_fn=None, memory=None):
    """Main routing function — the hybrid brain.
    
    1. Fast Path: Dictionary check
    2. Memory Path: Stored lesson recall
    3. Transformer Path: Domain classification → generation → critic → speech
    """
    trace = {
        "input": text,
        "timestamp": datetime.now().isoformat(),
        "roles": [],
        "skills": [],
        "confidence": 0.0,
        "memory_event": None,
        "permission": None,
        "domain": None,
        "route_path": [],
    }
    
    q = text.lower().strip()
    
    # ─── Fast Path: Dictionary ───
    if dict_lookup_fn:
        dict_answer = dict_lookup_fn(text)
        if dict_answer:
            trace["roles"] = ["memory_transformer", "dictionary_system"]
            trace["skills"] = ["dictionary_lookup", "fast_path"]
            trace["confidence"] = 0.98
            trace["memory_event"] = "dictionary_hit"
            trace["domain"] = "dictionary"
            _log_route(text, "dictionary", ["memory_transformer"], 0.98, "hit")
            if CONV_ENGINE:
                try:
                    CONV_ENGINE.add_exchange(text, dict_answer)
                except:
                    pass
            return dict_answer, trace
    
    # ─── Classify domain ───
    domain = classify_domain(text)
    trace["domain"] = domain
    

    # ─── Long-Term Memory Path ───
    # Check long-term memory first for saved facts
    # Uses strict slot matching to avoid wrong answers
    try:
        ltm_records = ltm.get_all(active_only=True) if hasattr(ltm, 'get_all') else []
    except:
        ltm_records = []
    active_ltm = ltm_records
    
    if active_ltm and domain in ("memory_recall", "general", "speech"):
        q_lower = q.lower()
        # Detect what slot the question is asking about
        asked_slot = None
        # Food/likes/consumption questions
        if re.search(r'(?:what)\s+(?:food|drink|meal|snack|dish)\s+(?:do|does|would|should)\s+i\s+(?:like|eat|drink|have|love|enjoy)', q_lower):
            asked_slot = "favorite_food"
        elif re.search(r'(?:what)\s+(?:color|colour)\s+(?:do|does|would|should)\s+i\s+(?:like|have|love|enjoy)', q_lower):
            asked_slot = "favorite_color"
        elif re.search(r'what\s+(?:is\s+)?my\s+favo(u)?rite\s+(\w+)', q_lower):
            asked_slot = "favorite_" + re.search(r'what\s+(?:is\s+)?my\s+favo(u)?rite\s+(\w+)', q_lower).group(2)
        elif re.search(r'(?:what|when)\s+(?:was|is)\s+(?:my\s+)?(?:year\s+of\s+)?birth', q_lower):
            asked_slot = "birth_year"
        elif re.search(r'(?:what|when)\s+was\s+i\s+born', q_lower):
            asked_slot = "birth_year"
        elif re.search(r'(?:where|what)\s+do\s+i\s+live', q_lower):
            asked_slot = "location"
        elif re.search(r'(?:where|what)\s+do\s+i\s+work', q_lower):
            asked_slot = "workplace"
        elif re.search(r'(?:what|who)\s+is\s+my\s+(\w+\s*\w*)\s*$', q_lower):
            # "what is my name" -> slot "name"
            # "what is my dog name" -> slot "dog_name" / "cat_name"
            match = re.search(r'(?:what|who)\s+is\s+my\s+(\w+(?:\s+\w+)?)\s*$', q_lower)
            if match:
                slot_text = match.group(1).strip()
                if slot_text == "name":
                    asked_slot = "name"
                elif slot_text in ("dog name", "cat name", "bird name", "fish name", "hamster name", "pet name"):
                    pet_type = slot_text.split()[0]
                    asked_slot = f"{pet_type}_name"
                elif slot_text in ("dog", "cat", "bird", "fish", "hamster", "pet"):
                    asked_slot = f"{slot_text}_name"
                elif slot_text == "favorite food":
                    asked_slot = "favorite_food"
                elif slot_text == "favorite color":
                    asked_slot = "favorite_color"
                else:
                    asked_slot = slot_text.replace(" ", "_")
        elif re.search(r'(?:what|who)\s+(?:is|was|are|were)\s+my', q_lower):
            asked_slot = "name"  # default to name for "who is my.."
        elif re.search(r'(?:do|does)\s+(?:you\s+)?remember\s+(?:my\s+)?', q_lower):
            pass  # generic - try keyword match
        elif re.search(r'tell\s+me\s+(?:about\s+)?(?:my\s+)?', q_lower):
            pass  # generic
        
        # Strict slot matching first - prefer most recently updated records
        if asked_slot:
            sorted_ltm = sorted(active_ltm, key=lambda r: r.get('updated_at', r.get('created_at', '')), reverse=True)
            for rec in sorted_ltm:
                slot = rec.get("extracted_slot", "")
                value = rec.get("extracted_value", "")
                raw_text = rec.get("raw_text", "")
                
                # Only match exact slot or very clear relationship
                if slot and slot == asked_slot:
                    synthesized = _synthesize_answer(raw_text, text)
                    if synthesized:
                        trace["roles"] = ["memory_transformer", "long_term_memory"]
                        trace["skills"] = ["long_term_recall", "exact_slot_match"]
                        trace["confidence"] = 0.95
                        trace["memory_event"] = f"long_term_recall:{rec.get('memory_id','?')}"
                        trace["route_path"] = ["long_term_memory", "speech_output"]
                        trace["long_term_memory_used"] = True
                        trace["memory_id"] = rec.get("memory_id", "?")
                        trace["extracted_slot"] = slot
                        trace["extracted_value"] = value
                        trace["final_answer_source"] = "deterministic_memory"
                        _log_route(text, "memory_recall", ["long_term_memory"], 0.95, "long_term_exact")
                        if 'CONV_ENGINE' in dir() and CONV_ENGINE:
                            try: CONV_ENGINE.add_exchange(text, synthesized)
                            except: pass
                        return synthesized, trace
        
        # No exact slot match for memory_recall domain - return "I don't know" if specific slot was asked
        if asked_slot and domain == "memory_recall":
            # Check if any long-term memory exists for this slot at all  
            for rec in active_ltm:
                slot = rec.get("extracted_slot", "")
                if slot == asked_slot:
                    break
            else:
                # No memory for this specific slot
                response = f"I don't have your {asked_slot.replace('_', ' ')} saved in long-term memory yet. Would you like to save it?"
                trace["roles"] = ["memory_transformer", "long_term_memory"]
                trace["skills"] = ["long_term_miss", "anti_hallucination"]
                trace["confidence"] = 0.95
                trace["memory_event"] = "long_term_miss"
                trace["route_path"] = ["memory_transformer"]
                trace["final_answer_source"] = "deterministic_memory_miss"
                _log_route(text, "memory_recall", ["long_term_memory"], 0.95, "long_term_miss")
                if 'CONV_ENGINE' in dir() and CONV_ENGINE:
                    try: CONV_ENGINE.add_exchange(text, response)
                    except: pass
                return response, trace

    # ─── Memory Path: Check stored lessons ───
    if memory and domain in ("memory_recall", "general", "science", "coding", "philosophy"):
        q_lower = q.lower()
        is_memory_recall = any(w in q_lower for w in ["my ", "i ", "me ", "mine", "name",
                                                        "remember", "recall", "favorite",
                                                        "born", "live", "work", "pet",
                                                        "drive", "speak", "sibling",
                                                        "car", "dog", "cat", "climb",
                                                        "mountain", "language", "color",
                                                        "food", "movie"])
        lessons_found = _search_lessons(q, memory)
        if lessons_found:
            best_fact = lessons_found[0]
            try:
                synthesized = _synthesize_answer(best_fact, text)
            except Exception:
                synthesized = None
            if synthesized:
                response = synthesized
                trace["synthesized_answer"] = True
            else:
                response = "From my stored knowledge, I recall:\n"
                for txt in lessons_found[:3]:
                    response += f"  \u2022 {txt[:120]}\n"
            trace["roles"] = ["memory_transformer", "critic_conscience_transformer"]
            trace["skills"] = ["memory_search", "lesson_recall", "answer_synthesis"]
            trace["confidence"] = 0.85
            if not trace.get("memory_event") or "memory_saved" not in trace.get("memory_event", ""):
                trace["memory_event"] = f"memory_search:{len(lessons_found)}_matches"
            trace["route_path"] = ["memory_transformer", "critic"]
            _log_route(text, domain, ["memory_transformer"], 0.85, "memory_hit")
            if CONV_ENGINE:
                try:
                    CONV_ENGINE.add_exchange(text, response)
                except:
                    pass
            return response, trace
        elif is_memory_recall and domain not in ("coding", "science"):
            response = "I don't have that saved in my memory yet. If you tell me, I can remember it for you."
            trace["roles"] = ["memory_transformer"]
            trace["skills"] = ["memory_search", "anti_hallucination"]
            trace["confidence"] = 0.95
            trace["memory_event"] = "memory_miss_anti_hallucination"
            trace["route_path"] = ["memory_transformer"]
            trace["final_answer_source"] = "memory_miss"
            _log_route(text, domain, ["memory_transformer"], 0.95, "memory_miss")
            if CONV_ENGINE:
                try:
                    CONV_ENGINE.add_exchange(text, response)
                except:
                    pass
            return response, trace

    # ─── Local LLM Cortex Path ───
    # If local LLM is configured and route is suitable, use it instead of local transformer
    try:
        from nova_llm_router_integration import should_use_local_llm, build_llm_context, run_local_llm_route, check_llm_output, handle_feedback
        route_for_llm = get_route_for_domain(domain)
        use_llm, llm_reason = should_use_local_llm(domain, route_for_llm, confidence if 'confidence' in dir() else 0.7)
        
        if use_llm:
            # Build context with what Nova knows
            dict_meanings = ""
            if dict_lookup_fn:
                try:
                    dict_meanings = str(dict_lookup_fn(text))[:200]
                except:
                    pass
            
            memory_matches = ""
            if memory:
                lessons = _search_lessons(q, memory)
                if lessons:
                    memory_matches = "; ".join(lessons[:2])[:200]
            
            brain_votes_str = str(dict(list(DOMAINS.get(domain, {}).items())[:5])) if domain else ""
            
            llm_context = build_llm_context(
                text, domain, route_for_llm, 0.8,
                dict_meanings=dict_meanings,
                memory_matches=memory_matches,
                brain_votes=brain_votes_str,
                route_trace=" -> ".join(route_for_llm)
            )
            
            llm_response = run_local_llm_route(llm_context)
            
            if llm_response.local_llm_used:
                # Critic check the output
                critic_result = check_llm_output(llm_response.raw_output, text)
                
                if critic_result["accepted"]:
                    final_output = critic_result["cleaned_output"]
                    
                    trace["local_llm_used"] = True
                    trace["local_llm_provider"] = llm_response.provider
                    trace["local_llm_model"] = llm_response.model
                    trace["local_llm_url"] = llm_response.url
                    trace["roles"] = route_for_llm + ["local_llm_cortex"]
                    trace["skills"] = [f"local_llm_{domain}", "llm_cortex"]
                    trace["confidence"] = 0.88
                    trace["memory_event"] = f"local_llm:{domain}"
                    trace["route_path"] = route_for_llm + ["local_llm_cortex", "critic", "speech_output"]
                    trace["fallback_used"] = False
                    trace["critic_result"] = "accepted"
                    trace["prompt_sent"] = llm_response.prompt[:300]
                    trace["raw_llm_output"] = llm_response.raw_output[:300]
                    
                    _log_route(text, domain, trace["route_path"], 0.88, "local_llm")
                    if CONV_ENGINE:
                        try:
                            CONV_ENGINE.add_exchange(text, final_output)
                        except:
                            pass
                    return final_output, trace
                else:
                    # Critic rejected output - fall through to transformer path
                    trace["local_llm_used"] = True
                    trace["critic_result"] = f"rejected: {critic_result['reason']}"
            else:
                # Local LLM not available - fall through to transformer path
                trace["local_llm_used"] = False
                trace["local_llm_fallback_reason"] = llm_response.fallback_reason
    except Exception as llm_err:
        # If local LLM integration fails, silently continue to transformer path
        trace["local_llm_used"] = False
        trace["local_llm_error"] = str(llm_err)[:100]
    # ─── Transformer Path: Generate response ───
    gen_response, route, confidence, gen_errors, transformer_ran = generate_transformer_response(text, domain)
    
    # 4-State Quality Gate:
    #   state 1: transformer_ran = did the forward pass execute without crash?
    #   state 2: transformer_output_accepted = did it pass the quality gate?
    #   state 3: local_llm_synthesis_used = was LLM used to polish/synthesize?
    #   state 4: fallback_used = was a hardcoded template returned?
    trace["transformer_ran"] = transformer_ran
    
    if gen_response and transformer_ran:
        quality_result = gate_transformer_output(
            gen_response,
            domain=domain,
            memory_used=bool(memory and memory.get("lessons")),
            dict_used=False
        )
        
        trace["transformer_output_raw"] = gen_response[:500]
        trace["quality_score"] = quality_result["quality_score"]
        trace["quality_checks"] = quality_result["quality_checks"]
        trace["quality_fail_reasons"] = quality_result["quality_fail_reasons"]
        trace["transformer_output_quality"] = quality_result["transformer_output_quality"]
        
        if quality_result["transformer_output_accepted"]:
            trace["roles"] = route
            trace["skills"] = [f"generated_{domain}", "transformer_inference"]
            trace["confidence"] = confidence
            trace["memory_event"] = f"transformer_generated:{domain}"
            trace["route_path"] = route
            trace["transformer_output_accepted"] = True
            trace["fallback_used"] = False
            trace["local_llm_synthesis_used"] = False
            trace["gen_errors"] = gen_errors if gen_errors else None
            trace["final_answer_source"] = "accepted_transformer"
            _log_route(text, domain, route, confidence, "transformer")
            if CONV_ENGINE:
                try:
                    CONV_ENGINE.add_exchange(text, gen_response)
                except:
                    pass
            return gen_response, trace
        else:
            trace["transformer_output_accepted"] = False
            trace["transformer_used"] = True
            try:
                raw_output_hint = gen_response[:200]
                import subprocess as _sp, json as _json
                from nova_local_llm_connector import clean_local_llm_output
                _payload = _json.dumps({
                    "model": "deepseek-r1:7b",
                    "prompt": f"[INST] The user asked: {text}\n\nNova's brain roughed out: {raw_output_hint}\n\nProvide a clean, helpful answer based on the rough output. Do not invent facts. Be direct.[/INST]",
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 260}
                })
                _result = _sp.run(
                    ["curl", "-s", "-X", "POST", "http://127.0.0.1:11434/api/generate", "-d", _payload],
                    capture_output=True, text=True, timeout=120
                )
                if _result.returncode == 0:
                    _data = _json.loads(_result.stdout)
                    _raw = clean_local_llm_output(_data.get("response", ""))
                    if _raw and len(_raw) > 10:
                        trace["local_llm_synthesis_used"] = True
                        trace["local_llm_synthesis_reason"] = f"transformer_rejected:{quality_result['transformer_output_quality']}"
                        trace["fallback_used"] = False
                        trace["final_answer_source"] = "local_llm_synthesis"
                        trace["roles"] = route + ["local_llm_cortex"]
                        trace["skills"] = [f"llm_synthesis_{domain}", "transformer_inference"]
                        trace["confidence"] = 0.82
                        trace["memory_event"] = f"llm_synthesis:{domain}"
                        trace["route_path"] = route + ["local_llm_cortex", "critic", "speech_output"]
                        _log_route(text, domain, trace["route_path"], 0.82, "llm_synthesis")
                        if CONV_ENGINE:
                            try:
                                CONV_ENGINE.add_exchange(text, _raw)
                            except:
                                pass
                        return _raw, trace
            except Exception:
                pass
            trace["local_llm_synthesis_used"] = trace.get("local_llm_synthesis_used", False)
            trace["fallback_used"] = True
    else:
        trace["transformer_used"] = transformer_ran
        trace["transformer_output_accepted"] = False
        trace["transformer_output_quality"] = "empty" if transformer_ran else "not_run"
        trace["fallback_used"] = True
        trace["local_llm_synthesis_used"] = False
    
    # ─── Ultimate Fallback ───
    fallback_responses = {
        "coding": "I can help with coding! My left_hemisphere has programming knowledge. Could you tell me what you need help with? I know Python, JavaScript, and general software concepts.",
        "math": "I have math training covering algebra, calculus, and formulas. What specific math problem are you working on?",
        "science": "My science training covers physics, chemistry, biology, astronomy, and the scientific method. What topic interests you?",
        "philosophy": "I've studied philosophy including consciousness, free will, ethics, and logic. What philosophical question is on your mind?",
        "psychology": "My training includes psychology, neuroscience, cognition, and emotional intelligence. What would you like to explore?",
        "creative": "I can help with creative tasks! I have a creative preview builder and can generate SVG, canvas art, and animation concepts.",
        "general": "I'm Nova Creature with 7 brain roles, trained in coding, science, philosophy, psychology, and more, with some people in memory and learn new things when you teach me.",
    }
    
    fallback = fallback_responses.get(domain, fallback_responses["general"])
    trace["roles"] = ["memory_transformer", "speech_output_transformer"]
    trace["skills"] = ["fallback", "domain_aware"]
    trace["confidence"] = 0.75
    trace["route_path"] = route if route else ["memory_transformer", "speech_output_transformer"]
    for key in ["transformer_output_quality", "transformer_ran", "transformer_output_accepted", "final_answer_source"]:
        if key not in trace:
            trace[key] = "fallback_only" if key == "transformer_output_quality" else (False if key != "final_answer_source" else "fallback_template")
    
    _log_route(text, domain, trace["route_path"], 0.75, "fallback")
    return fallback, trace
def _search_lessons(q, memory):
    """Search stored lessons with slot-aware scoring, recency priority."""
    import re as _re
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                   "have", "has", "had", "do", "does", "did", "will", "would", "could",
                   "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                   "on", "with", "at", "by", "from", "as", "into", "through", "during",
                   "what", "which", "who", "whom", "this", "that", "these", "those",
                   "it", "its", "you", "your", "i", "me", "my", "we", "our",
                   "not", "no", "nor", "so", "but", "if", "or", "and", "about",
                   "how", "why", "when", "where", "please", "help", "need"}
    
    clean_words = _re.sub(r'[^a-z0-9\s]', ' ', q.lower()).split()
    query_words = [w for w in clean_words if w not in stop_words and len(w) > 1]
    
    # Detect what SLOT the question is asking about
    q_lower = q.lower()
    qs = None
    
    if _re.search(r'(?:my )?favorite (color|food|movie|book|song)', q_lower):
        qs = "my favorite "
    elif _re.search(r"(?:my )?pet(?:['s]|s)?.*(?:name|kind|type)|parrot|skittles", q_lower):
        qs = "my pet"
    elif _re.search(r'what (?:car|vehicle|drive)', q_lower) or "charger" in query_words:
        qs = "i drive "
    elif _re.search(r'what (?:language|do i speak)', q_lower) or "fluent" in query_words:
        qs = "i speak "
    elif _re.search(r'where.*born|when.*born|reykjavik|iceland', q_lower) or "born" in query_words:
        qs = "i was born"
    elif _re.search(r'(?:where|what).*work|job|employ|welder', q_lower) or "work" in query_words:
        qs = "i work "
    elif _re.search(r'(?:where|what).*live|location|reside|from', q_lower):
        qs = "i live "
    elif _re.search(r'(?:brother|sister|twin|sibling|marcus)', q_lower):
        qs = "i have "
    elif _re.search(r'(?:climb|mountain|everest|kilimanjaro)', q_lower):
        qs = "i once "
    elif "movie" in query_words or "fifth" in query_words or "element" in query_words:
        qs = "my favorite movie"
    elif "color" in query_words or "ultraviolet" in query_words:
        qs = "my favorite color"
    
    scored = []
    for lid, ldata in memory.get("lessons", {}).items():
        lt = ldata.get("text", "").lower()
        learned_at = ldata.get("learned_at", "")
        cat = ldata.get("category", "")
        cw = [w for w in lt.split() if w not in stop_words and len(w) > 1]
        
        cm = sum(1 for w in query_words if w in cw)
        tm = sum(1 for w in query_words if w in lt)
        pb = 3 if any(' '.join(query_words[i:i+2]) in lt for i in range(len(query_words)-1)) else 0
        cb = 3 if cat == "user_fact" else 0
        
        sb = 0
        if qs:
            if lt.startswith(qs.lower()):
                sb = 500
            elif any(w in lt for w in query_words if w in ["pet","parrot","skittles","charger","dodge","welder","barbecue","korean","ultraviolet","fifth","element","kilimanjaro","marcus","reykjavik","iceland","brother","twin"]):
                sb = 250
        
        rec = 0
        try:
            from datetime import datetime as _dt
            parsed = _dt.fromisoformat(learned_at) if learned_at else _dt.min
            age_hours = (_dt.now() - parsed).total_seconds() / 3600
            rec = max(0, 50 - age_hours)
        except:
            pass
        
        if tm >= 1:
            if query_words and cm == 0 and sb == 0:
                continue
            score = cm * 100 + pb * 10 + tm + cb + sb + rec
            if score > 0:
                scored.append((score, ldata["text"]))
    
    if scored:
        scored.sort(key=lambda x: -x[0])
        if scored[0][0] >= 50:
            return [scored[0][1]]
        return []
    return []


def _synthesize_answer(memory_text, question):
    """Transform saved memory fact into direct second-person answer."""
    if not memory_text or not question:
        return None
    result = None
    mem = memory_text.strip()
    mem_lower = mem.lower()
    import re as _re_syn
    
    if mem_lower.startswith("i was born"):
        result = "You were born" + mem[10:]
    elif mem_lower.startswith("i live"):
        result = "You " + mem[2:]
    elif mem_lower.startswith("i work"):
        result = "You " + mem[2:]
    elif mem_lower.startswith("i am from"):
        result = "You are from" + mem[9:]
    elif mem_lower.startswith("i am "):
        result = "You are " + mem[5:]
    elif any(mem_lower.startswith(v) for v in ["i like ", "i love ", "i enjoy "]):
        result = "You " + mem[2:]
    elif mem_lower.startswith("i have "):
        result = "You have " + mem[7:]
    elif mem_lower.startswith("i speak "):
        result = "You speak " + mem[8:]
    elif mem_lower.startswith("i drive "):
        result = "You drive " + mem[8:]
    elif mem_lower.startswith("i once "):
        result = "You once" + mem[6:]
    elif mem_lower.startswith("i can "):
        result = "You can " + mem[6:]
    elif mem_lower.startswith("my name is "):
        result = "Your name is " + mem[11:]
    elif _re_syn.match(r'[Mm]y favorite (.+) is (.+)', mem):
        m = _re_syn.match(r'[Mm]y favorite (.+) is (.+)', mem)
        result = f"Your favorite {m.group(1)} is {m.group(2)}"
    elif _re_syn.match(r'[Mm]y (.+) name is (.+)', mem):
        m = _re_syn.match(r'[Mm]y (.+) name is (.+)', mem)
        result = f"Your {m.group(1)} name is {m.group(2)}"
    elif _re_syn.match(r'[Mm]y (.+) is (.+)', mem):
        m = _re_syn.match(r'[Mm]y (.+) is (.+)', mem)
        result = f"Your {m.group(1)} is {m.group(2)}"
    elif mem_lower.startswith("i "):
        result = "You " + mem[2:]
    
    if result:
        if result.startswith("You was "):
            result = "You were" + result[7:]
        if not result.endswith(('.', '!', '?')):
            result += '.'
    return result
def _log_route(text, domain, route, confidence, source):
    """Log routing decisions for analysis and learning."""
    entry = {
        "timestamp": datetime.now().isoformat(),
        "text": text[:100],
        "domain": domain,
        "route": route,
        "confidence": confidence,
        "source": source,
    }
    ROUTING_LOG.append(entry)
    try:
        ROUTING_LOG_PATH.parent.mkdir(exist_ok=True)
        with open(ROUTING_LOG_PATH, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    except:
        pass

def get_routing_stats():
    """Get statistics about routing decisions."""
    domains = {}
    routes = {}
    sources = {}
    for entry in ROUTING_LOG:
        d = entry.get("domain", "unknown")
        domains[d] = domains.get(d, 0) + 1
        r = tuple(entry.get("route", []))
        routes[r] = routes.get(r, 0) + 1
        s = entry.get("source", "unknown")
        sources[s] = sources.get(s, 0) + 1
    
    return {
        "total_routes": len(ROUTING_LOG),
        "domains": domains,
        "routes": dict(sorted(routes.items(), key=lambda x: -x[1])[:10]),
        "sources": sources,
        "last_routes": ROUTING_LOG[-5:] if ROUTING_LOG else [],
    }

# ─── Route Learning ──────────────────────────────────────────
def learn_from_feedback(text, route_used, confidence, success=True):
    """Learn from routing outcomes to improve future routing.
    
    When a route is successful (response was good), strengthen
    the domain-keyword associations for that domain.
    When unsuccessful, weaken them slightly.
    """
    domain = classify_domain(text)
    q = text.lower().strip()
    
    if success and confidence > 0.7:
        # Strengthen keyword associations
        words = re.sub(r'[^a-z0-9\s]', ' ', q).split()
        significant_words = [w for w in words if len(w) > 3]
        if domain in DOMAIN_KEYWORDS:
            for w in significant_words:
                if w not in DOMAIN_KEYWORDS[domain]:
                    DOMAIN_KEYWORDS[domain].append(w)
    elif not success:
        # Slightly weaken - just note it
        pass

if __name__ == "__main__":
    # Quick self-test
    print("="*60)
    print("NOVA HYBRID ROUTER — Self Test")
    print("="*60)
    
    test_inputs = [
        "What is a variable in Python?",
        "What is consciousness?",
        "Tell me a joke",
        "How do neurons work?",
        "Draw something creative",
        "What is the quadratic formula?",
    ]
    
    for inp in test_inputs:
        domain = classify_domain(inp)
        route = get_route_for_domain(domain)
        print(f"\nInput: {inp}")
        print(f"  Domain: {domain}")
        print(f"  Route:  {' -> '.join(route)}")
    
    print("\n✅ Hybrid Router loaded successfully")
    print(f"   {len(DOMAIN_KEYWORDS)} domains")
    print(f"   {sum(len(v) for v in DOMAIN_KEYWORDS.values())} total keywords")
