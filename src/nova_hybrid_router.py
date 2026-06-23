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

import json, sys, re
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_app_navigation import AppNavigationContext, plan_app_navigation

# ─── Imports (lazy) ─────────────────────────────────────────
BRAIN = None
TOKENIZER = None
CONV_ENGINE = None
APP_NAV_CONTEXT = AppNavigationContext()

def _ensure_brain():
    global BRAIN
    if BRAIN is None:
        from nova_transformer_runtime import NovaTransformerRuntime
        BRAIN = NovaTransformerRuntime(ROOT)
    return BRAIN

def _ensure_conv():
    global CONV_ENGINE
    if CONV_ENGINE is None:
        from nova_conversation_engine import ConversationEngine
        CONV_ENGINE = ConversationEngine()
    return CONV_ENGINE

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
    """Generate a response using the live transformer runtime.

    Returns (GenerationResult | None, RoutePrediction, GenerationResult, route_error).
    """
    brain = _ensure_brain()
    if hasattr(brain, "route_with_evidence") and callable(brain.route_with_evidence):
        prediction, route_error = brain.route_with_evidence(text)
    else:
        prediction = brain.route(text)
        route_error = getattr(brain, "last_route_error", None)
    result = brain.generate(prediction.primary_role, text, max_new_tokens=80)
    if not result.ok:
        return None, prediction, result, route_error
    return result, prediction, result, route_error

def route_and_respond(text, dict_lookup_fn=None, memory=None, transformer_only: bool = False):
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

    if not transformer_only:
        app_nav_snapshot = _snapshot_app_navigation_context(APP_NAV_CONTEXT)
        navigation = plan_app_navigation(text, APP_NAV_CONTEXT)
        if navigation.recognized:
            if not _should_accept_app_navigation(text, navigation):
                _restore_app_navigation_context(APP_NAV_CONTEXT, app_nav_snapshot)
            else:
                nav_trace = trace | navigation.trace()
                nav_trace["roles"] = ["planner_transformer", "memory_transformer"]
                nav_trace["skills"] = ["app_navigation", "operator_loop"]
                nav_trace["confidence"] = navigation.intent.confidence if navigation.intent else 0.0
                nav_trace["domain"] = "app_navigation"
                nav_trace["route_path"] = ["planner_transformer", "memory_transformer"]
                _log_route(text, "app_navigation", nav_trace["route_path"], nav_trace["confidence"], "app_navigation")
                return navigation.response, nav_trace
    
    # ─── Fast Path: Dictionary ───
    if dict_lookup_fn and not transformer_only:
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
    
    # ─── Memory Path: Check stored lessons ───
    if memory and not transformer_only and domain in ("memory_recall", "general", "science", "coding", "philosophy"):
        lessons_found = _search_lessons(q, memory)
        if lessons_found:
            response = "From my stored knowledge, I recall:\n"
            for txt in lessons_found[:3]:
                response += f"  \u2022 {txt[:120]}\n"
            trace["roles"] = ["memory_transformer", "critic_conscience_transformer"]
            trace["skills"] = ["memory_search", "lesson_recall"]
            trace["confidence"] = 0.85
            trace["memory_event"] = f"memory_search:{len(lessons_found)}_matches"
            trace["route_path"] = ["memory_transformer", "critic"]
            _log_route(text, domain, ["memory_transformer"], 0.85, "memory_hit")
            if CONV_ENGINE:
                try:
                    CONV_ENGINE.add_exchange(text, response)
                except:
                    pass
            return response, trace
    
    # ─── Transformer Path: Generate response ───
    gen_result, prediction, attempted_generation, route_error = generate_transformer_response(text, domain)
    route = _dedupe_roles([prediction.primary_role, *prediction.support_roles])
    generation_trace = attempted_generation.to_trace()

    if gen_result:
        trace["roles"] = route
        trace["skills"] = [f"generated_{prediction.domain}", "transformer_inference"]
        trace["confidence"] = prediction.confidence
        trace["memory_event"] = f"transformer_generated:{prediction.domain}"
        trace["route_path"] = route
        trace.update({
            "source": "transformer",
            "domain": prediction.domain,
            "roles": route,
            "confidence": prediction.confidence,
            "route_source": prediction.source,
            "route_model_hash": prediction.model_hash,
            "route_error": route_error,
            "checkpoint_hash": gen_result.checkpoint_hash,
            "checkpoint_path": gen_result.checkpoint_path,
            "generation": generation_trace,
        })
        _log_route(text, prediction.domain, route, prediction.confidence, "transformer")
        if CONV_ENGINE:
            try:
                CONV_ENGINE.add_exchange(text, gen_result.text)
            except:
                pass
        return gen_result.text, trace

    if transformer_only:
        error = generation_trace.get("error")
        error_text = (
            "Transformer generation failed, and transformer_only=True prevented "
            "dictionary or memory fallback."
        )
        if error:
            error_text += f" Error: {error}"
        trace.update({
            "source": "transformer_error",
            "domain": prediction.domain,
            "roles": route,
            "confidence": prediction.confidence,
            "route_source": prediction.source,
            "route_model_hash": prediction.model_hash,
            "route_error": route_error,
            "checkpoint_hash": generation_trace.get("checkpoint_hash"),
            "checkpoint_path": generation_trace.get("checkpoint_path"),
            "generation": generation_trace,
            "route_path": route,
            "skills": ["transformer_inference"],
            "memory_event": "transformer_failed",
        })
        _log_route(text, prediction.domain, route, prediction.confidence, "transformer_error")
        return error_text, trace
    
    # ─── Ultimate Fallback ───
    # Even transformers failed — provide intelligent fallback
    fallback_responses = {
        "coding": "I can help with coding! My left_hemisphere has programming knowledge. Could you tell me what you need help with? I know Python, JavaScript, and general software concepts.",
        "math": "I have math training covering algebra, calculus, and formulas. What specific math problem are you working on?",
        "science": "My science training covers physics, chemistry, biology, astronomy, and the scientific method. What topic interests you?",
        "philosophy": "I've studied philosophy including consciousness, free will, ethics, and logic. What philosophical question is on your mind?",
        "psychology": "My training includes psychology, neuroscience, cognition, and emotional intelligence. What would you like to explore?",
        "creative": "I can help with creative tasks! I have a creative preview builder and can generate SVG, canvas art, and animation concepts.",
        "general": "I'm Nova Creature with 7 brain roles, trained in coding, science, philosophy, psychology, and more. I have %s people in memory and learn new things when you teach me. Try: 'Learn this: [fact]' or ask me about any topic!",
    }
    
    fallback_domain = prediction.domain
    fallback = fallback_responses.get(fallback_domain, fallback_responses["general"])
    if fallback_domain == "general" and memory:
        pcount = len(memory.get("people", {}))
        fallback = fallback % f"{pcount}"
    
    trace["roles"] = ["memory_transformer", "speech_output_transformer"]
    trace["skills"] = ["fallback", "domain_aware"]
    trace["confidence"] = 0.75
    trace["source"] = "fallback"
    trace["domain"] = prediction.domain
    trace["route_path"] = route
    trace["route_source"] = prediction.source
    trace["route_model_hash"] = prediction.model_hash
    trace["route_error"] = route_error
    trace["checkpoint_hash"] = generation_trace.get("checkpoint_hash")
    trace["checkpoint_path"] = generation_trace.get("checkpoint_path")
    trace["generation"] = generation_trace
    
    _log_route(text, prediction.domain, route, 0.75, "fallback")
    return fallback, trace

def _dedupe_roles(roles):
    deduped = []
    seen = set()
    for role in roles:
        if role not in seen:
            deduped.append(role)
            seen.add(role)
    return deduped

def _should_accept_app_navigation(text, navigation):
    if not navigation.intent or navigation.intent.action != "verify":
        return True
    if plan_app_navigation(text, AppNavigationContext()).recognized:
        return True
    return _is_contextual_app_verify(text)

def _is_contextual_app_verify(text):
    q = text.lower().strip()
    app_targets = r"(?:page|build|test|tests|app|screen|view|workflow|navigation|button|form|preview)"
    return (
        re.fullmatch(r"check\s+if\s+it\s+works\s*[?.!]*", q) is not None
        or re.fullmatch(rf"(?:verify|check|test|run)\s+(?:the\s+)?{app_targets}\s*[?.!]*", q) is not None
        or re.fullmatch(
            r"(?:verify|check|test|run)\s+(?:that\s+)?(?:it|this)\s+(?:works|loads|opens|runs|saves)\s*[?.!]*",
            q,
        )
        is not None
    )

def _snapshot_app_navigation_context(context):
    return AppNavigationContext(
        last_surface=context.last_surface,
        active_project=context.active_project,
        active_agent=context.active_agent,
        active_draft=context.active_draft,
        pending_action=context.pending_action,
        verification_target=context.verification_target,
        last_blocker=context.last_blocker,
    )

def _restore_app_navigation_context(context, snapshot):
    context.last_surface = snapshot.last_surface
    context.active_project = snapshot.active_project
    context.active_agent = snapshot.active_agent
    context.active_draft = snapshot.active_draft
    context.pending_action = snapshot.pending_action
    context.verification_target = snapshot.verification_target
    context.last_blocker = snapshot.last_blocker

def _search_lessons(q, memory):
    """Search stored lessons for relevant content."""
    import re as _re
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                   "have", "has", "had", "do", "does", "did", "will", "would", "could",
                   "should", "may", "might", "can", "shall", "to", "of", "in", "for",
                   "on", "with", "at", "by", "from", "as", "into", "through", "during",
                   "what", "which", "who", "whom", "this", "that", "these", "those",
                   "it", "its", "you", "your", "i", "me", "my", "we", "our",
                   "not", "no", "nor", "so", "but", "if", "or", "and", "about",
                   "how", "why", "when", "where", "please", "help", "need"}
    lessons_found = []
    clean_words = _re.sub(r'[^a-z0-9\s]', ' ', q.lower()).split()
    query_words = [w for w in clean_words if w not in stop_words and len(w) > 1]
    
    for lid, ldata in memory.get("lessons", {}).items():
        text = ldata.get("text", "").lower()
        matches = sum(1 for w in query_words if w in text)
        if matches >= 2 or (matches >= 1 and (any(len(w) >= 2 for w in query_words) or len(query_words) <= 2)):
            lessons_found.append((matches, ldata["text"]))
    
    if lessons_found:
        lessons_found.sort(key=lambda x: -x[0])
        return [t for _, t in lessons_found[:3]]
    return []

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
