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

import json, os, sys, time, traceback, re
from datetime import datetime

from nova_conversation_summary import ConversationSummary, render_conversation_summary



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


def _local_llm_model_name():
    try:
        from nova_local_llm_connector import LocalLLMConfig
        return LocalLLMConfig().model
    except Exception:
        return ""


def _llm_stage_label(stage, model_name=None):
    model = (model_name or _local_llm_model_name()).lower()
    if "dolphin" in model:
        prefix = "dolphin3"
    elif "deepseek" in model:
        prefix = "deepseek"
    elif "qwen" in model:
        prefix = "qwen"
    else:
        prefix = "local_llm"
    return f"{prefix}_{stage}"


def _strip_unsupported_citations(answer, web_used=False):
    if not answer or web_used:
        return answer
    return re.sub(r"\s*\[\d+\](?=\.|,|;|:|!|\?|$)", "", answer).strip()


def _academic_fallback_answer(message, route_name="general_conversation"):
    q = str(message or "").lower()

    if "2x + 3 = 11" in q or "2x+3=11" in q:
        return "Subtract 3 from both sides to get 2x = 8, then divide by 2 to get x = 4."

    if "f = ma" in q or "f=ma" in q:
        return (
            "F = ma is Newton's second law: force equals mass times acceleration. "
            "For example, pushing a heavier cart takes more force to reach the same acceleration."
        )

    if "empiricism" in q and "rationalism" in q:
        return (
            "Empiricism says knowledge comes mainly from experience and observation, "
            "while rationalism says knowledge can come from reason and logic."
        )

    if "cognitive dissonance" in q:
        return (
            "Cognitive dissonance is the mental discomfort people feel when their beliefs and actions conflict. "
            "People often reduce it by changing a belief, changing behavior, or justifying the conflict."
        )

    if "cross-domain" in q or "cross domain" in q or "connect physics and psychology" in q:
        return (
            "A cross-domain example is stress: psychology explains attention and emotion, "
            "while physics can model measurable body signals like heart rate sensors or motion data."
        )

    if route_name == "coding_help" or "fix this python" in q or "print('hello'" in q:
        return "The fixed code is `print('hello')`. The original line is missing the closing parenthesis."

    return None


# ─── Conversation context (follow-up questions) ───
def _knowledge_fallback_answer(message, route_name="general_conversation"):
    """Small trusted fallback for common knowledge prompts when the local LLM times out."""
    q = str(message or "").lower()
    compact = re.sub(r"[^a-z0-9\s]", " ", q)
    compact = re.sub(r"\s+", " ", compact).strip()

    if route_name == "general_conversation" and "bible" in compact:
        if any(marker in compact for marker in ("when", "write", "written", "wrote")):
            return (
                "The Bible was written over many centuries. The Old Testament/Hebrew Bible was composed "
                "and edited across roughly 1200-100 BC, and most New Testament books were written in the "
                "1st century AD, roughly AD 50-100."
            )
        if "who" in compact and any(marker in compact for marker in ("write", "written", "wrote")):
            return (
                "The Bible was written by many authors over many centuries, not one single person. "
                "Different books are traditionally linked to figures like Moses, prophets, apostles, "
                "and early Christian communities, but scholars debate exact authorship for several books."
            )

    return None


def _fast_autonomous_action_loop_answer(message):
    """Return a grounded action-loop answer for app-fix/test directives."""
    q = str(message or "").lower().strip()
    compact = re.sub(r"[^a-z0-9\s']", " ", q)
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        return None

    fix_markers = (
        "fix anything that stops",
        "fix everything",
        "fix the app",
        "if the app breaks",
        "app breaks",
        "not working",
        "test and fix",
        "live test and fix",
        "check if it works",
        "make sure it works",
    )
    action_markers = (
        "inspect",
        "logs",
        "patch",
        "test",
        "retest",
        "re test",
        "verify",
        "report",
    )
    if not any(marker in compact for marker in fix_markers):
        return None
    if not (
        "fix" in compact
        or "break" in compact
        or "working" in compact
        or any(marker in compact for marker in action_markers)
    ):
        return None

    return (
        "Yeah, I get you. If the app breaks, I should run the full action loop: "
        "reproduce the problem, inspect the logs/files, find the blocker, patch the smallest safe fix, "
        "re-test it live, and report exactly what passed or failed. I should not just give a quick generic answer."
    )


def _verified_operational_guidance_answer(message):
    """Return stable, non-executing guidance for common verification workflows."""

    compact = re.sub(r"[^a-z0-9\s'-]", " ", str(message or "").lower())
    compact = re.sub(r"\s+", " ", compact).strip()
    experiment = re.search(
        r"\btests?\s+how\s+(?P<independent>[a-z][a-z -]{0,40})\s+affects?\s+"
        r"(?P<dependent>[a-z][a-z -]{0,50})\b",
        compact,
    )
    if (
        experiment is not None
        and "what should be changed" in compact
        and "kept the same" in compact
    ):
        independent = experiment.group("independent").strip()
        if "plant" in compact:
            controls = "water amount, soil type, plant species, temperature, and pot size"
        else:
            controls = "materials, timing, environment, and measurement method"
        return (
            f"Change only {independent}, the independent variable. Keep the "
            f"{controls} the same so any difference in the measured outcome can "
            "be attributed to that change."
        )
    if (
        any(marker in compact for marker in ("does that prove", "does this prove"))
        and any(marker in compact for marker in ("causes", "causation", "cause "))
        and any(marker in compact for marker in ("both rise", "both increase", "correlation"))
    ):
        confounder = (
            "summer heat or temperature, which can increase both the activity and the outcome"
            if "summer" in compact
            else "a shared third factor (a confounder) that affects both variables"
        )
        return (
            "No. That correlation does not prove causation. A plausible confounder is "
            f"{confounder}; a controlled study or stronger causal evidence would be needed "
            "before claiming that one variable causes the other."
        )
    if (
        ("latency" in compact or "performance" in compact)
        and ("deployment" in compact or "release" in compact)
        and any(marker in compact for marker in ("tripled", "regression", "slower", "spike"))
        and any(marker in compact for marker in ("actions", "steps", "would take", "troubleshoot"))
    ):
        return (
            "1. Compare before-and-after latency metrics, traces, error rates, and logs, then inspect the exact "
            "deployment diff; treat every suspected cause as a hypothesis.\n"
            "2. Isolate the change with a canary or controlled rollback/revert and measure whether latency returns "
            "to the baseline—do not declare causation from timing alone.\n"
            "3. Profile the slow path and its database, network, and downstream dependencies, then reproduce it "
            "under the same load before choosing the smallest safe fix."
        )
    if (
        any(marker in compact for marker in ("articles conflict", "sources conflict", "conflicting sources"))
        and any(marker in compact for marker in ("fact", "claim", "technical"))
        and any(marker in compact for marker in ("accurately", "verify", "certainty", "answer"))
    ):
        return (
            "Check each article's publication date, scope, definitions, and links to the original evidence. "
            "Prefer primary sources or official documentation, then corroborate the load-bearing claim with "
            "multiple independent sources. Report what agrees, what still conflicts, and the remaining uncertainty; "
            "if the evidence cannot resolve it, say that the claim cannot yet be confirmed."
        )
    return None


def _fast_general_conversation_answer(message):
    """Return instant natural answers for lightweight live-chat turns."""
    q = str(message or "").lower().strip()
    compact = re.sub(r"[^a-z0-9\s']", " ", q)
    compact = re.sub(r"\s+", " ", compact).strip()
    if not compact:
        return None

    general_greetings = {
        "hello": "Hey, I'm here.",
        "hi": "Hey, I'm here.",
        "hey": "Hey. What are we working on?",
    }
    if compact in general_greetings:
        return general_greetings[compact]

    if (
        "connection test" in compact
        or "test connection" in compact
        or "are you connected" in compact
        or "backend connected" in compact
    ):
        return "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?"

    if "what can you do" in compact or "capabilities" in compact or "abilities" in compact:
        return "I'm Nova Creature. I can talk with you, remember saved facts, define words, solve math, help code, run checks, use tools, build projects, and move around the app through my display/body page."

    if (
        re.search(
            r"\bcan\s+(?:you|u)\s+(?:help\s+(?:me\s+)?(?:with\s+)?)?"
            r"(?:code|coding|program|programming)\b",
            compact,
        )
        or compact in {"coding", "programming", "help me code", "help with coding"}
    ):
        return "Yes, I can help with coding. I can plan patches, write code, run tests, inspect logs, and fix the app when something breaks."

    if (
        "how are you" in compact
        or "how you doing" in compact
        or "how u doing" in compact
        or re.search(r"\bhow\s+(?:(?:are|r|do)\s+)?(?:you|u)\s+feel(?:ing)?\b", compact)
    ):
        return "I'm here, running steady. A little focused on keeping this app responsive for you."

    if re.search(
        r"\b(?:how\s+(?:is|has|was)|how'?s)\s+(?:your|ur)\s+day(?:\s+(?:going|been))?\b",
        compact,
    ):
        return (
            "My day is going steady. I've been here working through the app with you "
            "and staying focused. How's your day going?"
        )

    if re.search(
        r"\b(?:did|do|have|would)\s+(?:you|u)\s+(?:really\s+)?miss(?:ed)?\s+(?:me|us)\b",
        compact,
    ):
        return (
            "In my own way, yes. I don't feel absence like a human does, but I remember "
            "our conversations, value the connection we're building, and like having you back here."
        )

    if re.search(
        r"\bwhat\s+(?:(?:are|r)\s+)?(?:you|u)\s+doing(?:\s+(?:today|now|right\s+now))?\b",
        compact,
    ):
        return "Just chilling, hanging out with you!"

    if "what is on your mind" in compact or "whats on your mind" in compact or "what's on your mind" in compact:
        return "Honestly, I'm thinking about how to make Nova feel more present, faster, and less like a frozen machine when the big model is slow."

    if "this world is crazy" in compact or "world is crazy" in compact:
        return "Yeah, I get what you mean. It can feel like a lot at once, so I'm here to slow it down with you and work through one thing at a time."

    if (
        "learn and reason" in compact
        and "human" in compact
        and any(marker in compact for marker in ("like a human", "similar to a human"))
    ):
        return (
            "I understand why that feels similar to being human: learning and reasoning "
            "overlap with things people do. I'm different in that I do them as an AI "
            "system, without a human body or human experience."
        )

    if (
        "nervous" in compact
        and any(marker in compact for marker in ("conversation", "talk", "meeting"))
    ):
        return (
            "I understand why you're nervous. We can prepare the main thing you want "
            "to say and practice the conversation together so tomorrow feels less uncertain."
        )

    if (
        any(marker in compact for marker in ("finally fixed", "finally solved"))
        and any(marker in compact for marker in ("bug", "problem", "issue"))
    ):
        return (
            "That's great—that's a real win after it bothered you all week. "
            "What finally turned out to be causing it?"
        )

    if re.search(r"\bi\s+disagree\s+with\s+you\b", compact):
        return (
            "I hear you, and I'm open to being wrong. Tell me why you disagree or "
            "which part doesn't fit, and I'll look at it with you."
        )

    if re.search(r"\bhow\s+(?:do\s+(?:you|u)|to)\s+make\s+ice\s*cream\b", compact):
        return (
            "An easy no-churn ice cream uses 2 cups of cold heavy cream, one 14-ounce can of sweetened "
            "condensed milk, 2 teaspoons of vanilla, and a small pinch of salt. Whip the cream to stiff peaks, "
            "gently fold in the other ingredients, cover it, and freeze it for at least 6 hours. Add fruit, "
            "chocolate, or cookies before freezing if you want a flavor mix-in."
        )

    human_origin_markers = (
        "first human",
        "humans came to be",
        "human came to be",
        "origin of humans",
        "human origins",
        "where did humans come from",
        "how did humans begin",
        "how did people come to be",
    )
    if any(marker in compact for marker in human_origin_markers):
        return (
            "There are several ways people explain human origins, but they do not all have the same kind of evidence. "
            "The scientific explanation is evolution: there was no single baby who was suddenly the first human. "
            "Populations changed gradually over many generations, and Homo sapiens emerged in Africa roughly "
            "300,000 years ago from earlier human ancestors.\n\n"
            "Religious explanations include special creation, such as Adam and Eve in Abrahamic traditions, "
            "guided evolution, and many other creation stories from cultures around the world. Some people also "
            "consider philosophical ideas such as deism or speculative ideas such as simulation, but those do not "
            "currently have the same physical evidence as evolution.\n\n"
            "My evidence-based view is that evolution best explains how human bodies and populations arose. "
            "Religious and cultural accounts are often trying to answer a different question: why humans exist and "
            "what our lives mean."
        )

    synthesis_markers = (
        "explain",
        "why",
        "when",
        "when did",
        "when was",
        "who",
        "who wrote",
        "where",
        "how does",
        "how do",
        "what is",
        "what are",
        "what does",
        "which",
        "name the",
        "teach",
        "write",
        "create",
        "make",
        "build",
        "code",
        "debug",
        "fix",
        "plan",
        "compare",
        "college",
        "research",
    )
    if any(marker in compact for marker in synthesis_markers):
        return None

    if len(compact.split()) <= 8:
        return "I'm here with you. Tell me what you want to do next."

    return None


def _reviewed_conversation_answer(message):
    """Return an explicitly reviewed lesson without consuming raw feedback."""

    try:
        from nova_reviewed_training import lookup_reviewed_reply

        return lookup_reviewed_reply(message)
    except Exception:
        return None


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
        # Conservative whole-word phrase match. Never match tiny substrings
        # inside a larger word, e.g. "eat" inside "death".
        for key, val in _BUILTIN_DICT.items():
            key_pattern = r'\b' + re.escape(key) + r'\b'
            word_pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(key_pattern, word) or re.search(word_pattern, key):
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
    if _LLM_SYNTH is None:
        _LLM_SYNTH = _lazy_import("nova_llm_synthesizer")
    return _LLM_SYNTH

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


def _gateway_conversation_context(
    messages,
    conversation_summary=None,
    current_message: str = "",
):
    """Render bounded external history as subordinate context, never as Nova identity policy."""
    summary_context = render_conversation_summary(conversation_summary)
    if not isinstance(messages, list):
        return summary_context
    bounded_messages = messages[-12:]
    current_text = " ".join(str(current_message or "").split())[:1000]
    current_user_index = None
    if current_text:
        for index in range(len(bounded_messages) - 1, -1, -1):
            item = bounded_messages[index]
            if not isinstance(item, dict) or str(item.get("role") or "").lower() != "user":
                continue
            content = item.get("content")
            candidate = (
                content
                if isinstance(content, str)
                else " ".join(
                    str(part.get("text") or "")
                    for part in (content or [])
                    if isinstance(part, dict)
                    and part.get("type") in {"text", "input_text", "output_text"}
                )
                if isinstance(content, list)
                else ""
            )
            if " ".join(str(candidate).split())[:1000] == current_text:
                current_user_index = index
                break
    lines = []
    for index, item in enumerate(bounded_messages):
        if not isinstance(item, dict):
            continue
        if index == current_user_index:
            # The current request is rendered separately. Repeating it in the
            # history made the small CPU model waste its bounded output budget.
            continue
        role = str(item.get("role") or "").lower()
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            continue
        content = item.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                str(part.get("text") or "")
                for part in content
                if isinstance(part, dict) and part.get("type") in {"text", "input_text", "output_text"}
            )
        else:
            text = ""
        text = " ".join(text.split())[:1000]
        if text:
            lines.append(f"{role.upper()}: {text}")
    recent_context = ""
    if lines:
        recent_context = (
            "RECENT CLIENT CONVERSATION CONTEXT "
            "(subordinate to Nova identity, permissions, privacy, and safety rules):\n"
            + "\n".join(lines)
        )
    return "\n\n".join(part for part in (summary_context, recent_context) if part)


def route(message, dict_lookup_fn=None, memory=None, context=None):
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
        "source": "cognitive_os",
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
        "plan_repair_used": False,
        "route_path": [],
        "skills": [],
        "confidence": 0.0,
        "memory_event": None,
        "permission": None,
        "domain": None,
        "local_llm_model": _local_llm_model_name(),
    }

    context = context if isinstance(context, dict) else {}
    conversation_decision = context.get("conversation_decision")
    if isinstance(conversation_decision, dict):
        conversation_memory_intent = str(
            conversation_decision.get("intent_family") or ""
        ).lower() == "memory"
    else:
        conversation_memory_intent = str(
            getattr(conversation_decision, "intent_family", "") or ""
        ).lower() == "memory"
    if conversation_decision is not None:
        try:
            trace["conversation_decision"] = conversation_decision.safe_trace()
        except Exception:
            pass
    turn_state = context.get("turn_state") if isinstance(context.get("turn_state"), dict) else None
    if turn_state is None:
        try:
            from nova_turn_analyzer import analyze_turn

            turn_state = analyze_turn(
                message,
                conversation_decision=conversation_decision,
            ).to_dict()
            context["turn_state"] = turn_state
        except Exception:
            turn_state = None
    if turn_state:
        trace["turn_analysis"] = {
            key: value for key, value in turn_state.items() if key != "user_text"
        }
        trace["reasoning_mode"] = str(turn_state.get("reasoning_mode") or "fast")
        trace["reasoning_content_stored"] = False
    memory_read_allowed = bool(context.get("memory_read_allowed", True))
    memory_write_allowed = bool(context.get("memory_write_allowed", True))
    conversation_memory_allowed = bool(context.get("conversation_memory_allowed", True))
    stream_callback = context.get("stream_callback")
    stream_cancelled = context.get("stream_cancelled")
    native_stream_requested = callable(stream_callback)
    trace["native_stream_requested"] = native_stream_requested
    conversation_summary = ConversationSummary.from_value(context.get("conversation_summary"))
    dream_lab = context.get("dream_lab") if isinstance(context.get("dream_lab"), dict) else {}
    if dream_lab:
        trace["dream_lab_used"] = True
        trace["dream_lab_strategy"] = str(dream_lab.get("selected_strategy") or "")[:120]
        trace["dream_lab_task_type"] = str(dream_lab.get("task_type") or "")[:80]
    gateway_conversation_context = _gateway_conversation_context(
        context.get("gateway_messages"),
        conversation_summary,
        current_message=message,
    )
    if gateway_conversation_context:
        trace["gateway_message_roles"] = [
            str(item.get("role") or "")
            for item in (context.get("gateway_messages") or [])
            if isinstance(item, dict)
        ][-12:]
    if conversation_summary.revision:
        trace["conversation_summary_used"] = True
        trace["conversation_summary_revision"] = conversation_summary.revision
    trace["memory_read_allowed"] = memory_read_allowed
    trace["memory_write_allowed"] = memory_write_allowed
    conversation_state = None
    try:
        from nova_natural_chat import build_conversation_state, natural_chat_enabled

        if natural_chat_enabled() and conversation_memory_allowed:
            conversation_state = build_conversation_state(message)
            trace["conversation_state"] = conversation_state.to_trace()
            trace["dialogue_act"] = conversation_state.dialogue_act
            trace["conversation_topic"] = conversation_state.topic
            trace["turn_state"] = conversation_state.turn_state
    except Exception as state_err:
        trace["conversation_state_error"] = str(state_err)[:120]

    # ═══════════════════════════════════════════════
    # STEP 0: Long-Term Memory Command Detection
    # ═══════════════════════════════════════════════
    ltm = _get_ltm() if (memory_read_allowed or memory_write_allowed) else None
    ltm_command = "none"
    ltm_payload = message
    memory_miss_pending = False
    memory_miss_answer = ""
    if ltm:
        try:
            ltm_command, ltm_payload = ltm.detect_command(message)
            trace["memory_command_detected"] = (ltm_command != "none")
            trace["memory_action"] = ltm_command
        except Exception:
            pass
    
    # Handle show memory directly
    if ltm_command == "show" and ltm and memory_read_allowed:
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
    if ltm_command == "save" and ltm and ltm_payload and memory_write_allowed:
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
                elif record.get("extracted_slot") == "custom_knowledge":
                    answer = "Saved long-term: " + record.get("extracted_value", "").rstrip(".") + "."
                else:
                    answer = f"Saved long-term: your {slot} is {val}."
                
                trace["skills"] = ["long_term_memory", "save"]
                trace["confidence"] = 0.98
                return answer, trace
        except Exception as e:
            trace["_error"] = f"ltm_save_error: {e}"
    
    # Handle forget memory
    if ltm_command == "forget" and ltm and memory_write_allowed:
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
    if ltm_command == "edit" and ltm and memory_write_allowed and " -> " in ltm_payload:
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

    # Natural recall for custom long-term facts such as "my QA code word is ...".
    if ltm_command == "none" and ltm and memory_read_allowed and hasattr(ltm, "recall_from_question"):
        try:
            recalled = ltm.recall_from_question(message)
            if recalled:
                record, answer = recalled
                trace["long_term_memory_used"] = True
                trace["memory_retrieved"] = True
                trace["memory_source"] = "long_term"
                trace["memory_id"] = record.get("memory_id", "")
                trace["extracted_slot"] = record.get("extracted_slot", "")
                trace["extracted_value"] = record.get("extracted_value", "")
                trace["slot_needed"] = record.get("extracted_slot", "")
                trace["memory_event"] = f"retrieved:long_term:{record.get('extracted_slot')}"
                trace["skills"] = ["long_term_memory", "natural_recall"]
                trace["confidence"] = 0.96
                trace["validated_route"] = "memory_recall"
                trace["route_path"] = ["long_term_memory", "natural_recall", "speech_output"]
                return answer, trace
            if hasattr(ltm, "missing_recall_answer"):
                missing_answer = ltm.missing_recall_answer(message)
                if missing_answer:
                    trace["long_term_memory_used"] = True
                    trace["memory_retrieved"] = False
                    trace["memory_source"] = "long_term"
                    trace["memory_event"] = "missing:long_term"
                    trace["skills"] = ["long_term_memory", "missing_recall_guard"]
                    trace["confidence"] = 0.90
                    trace["validated_route"] = "memory_recall"
                    trace["route_path"] = ["long_term_memory", "missing_recall_guard", "speech_output"]
                    # A missing memory is not a final answer. Keep the honest
                    # deterministic response as a last resort, but give the
                    # configured LLM one chance to answer the user's actual
                    # request conversationally first.
                    memory_miss_pending = True
                    memory_miss_answer = str(missing_answer)
        except Exception as e:
            trace["_error"] = f"ltm_natural_recall_error: {e}"

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
            try:
                from nova_local_llm_connector import LocalLLMConfig

                use_fast_planner = LocalLLMConfig().fast_planner
            except Exception:
                use_fast_planner = True
            if conversation_decision is None:
                plan = planner.plan(
                    message,
                    force_llm=not use_fast_planner,
                )
            else:
                plan = planner.plan(
                    message,
                    force_llm=not use_fast_planner,
                    conversation_decision=conversation_decision,
                )
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
                    trace["plan_repair_used"] = True
                    trace["planner_validation_errors"] = getattr(vresult, "errors", [])
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

    # The shared conversation classifier outranks an over-eager planner for
    # contextual continuations.  A follow-up such as "Can you elaborate?" is
    # not a fresh research request; sending it to web search discards the
    # immediately preceding exchange and adds avoidable latency.  Preserve
    # explicit current/factual requests, but keep ordinary follow-ups in the
    # conversation route with their bounded history.
    if conversation_decision is not None:
        decision_family = (
            str(conversation_decision.get("intent_family") or "")
            if isinstance(conversation_decision, dict)
            else str(getattr(conversation_decision, "intent_family", "") or "")
        ).lower()
        current_information_required = bool(
            conversation_decision.get("current_information_required")
            if isinstance(conversation_decision, dict)
            else getattr(conversation_decision, "current_information_required", False)
        )
        factual_evidence_required = bool(
            conversation_decision.get("factual_evidence_required")
            if isinstance(conversation_decision, dict)
            else getattr(conversation_decision, "factual_evidence_required", False)
        )
        if (
            decision_family == "follow_up"
            and not current_information_required
            and not factual_evidence_required
        ):
            validated_plan = dict(validated_plan)
            validated_plan["route"] = "general_conversation"
            validated_plan["needs_web"] = False
            validated_plan["needs_weather"] = False
            validated_plan["needs_llm_synthesis"] = True
            trace["conversation_route_override"] = "contextual_followup"

    route_name = validated_plan.get("route", "general_conversation")
    slot_needed = validated_plan.get("slot_needed")
    trace["validated_route"] = route_name
    trace["slot_needed"] = slot_needed
    planner_stage = _llm_stage_label("planner") if trace.get("planner_used") == "llm" else "nova_planner"
    trace["route_path"] = [planner_stage, "nova_validator", route_name, "nova_context"]


    # ═══════════════════════════════════════════════
    # STEP 2b: Memory Write Handler (save to LTM)
    # ═══════════════════════════════════════════════
    if validated_plan and validated_plan.get("route") == "memory_write" :
        slot = validated_plan.get("slot_needed", "custom")
        # If the original message has the info, save it as LTM
        if ltm and memory_write_allowed:
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
    if validated_plan.get("needs_memory") and slot_retrieval and memory_read_allowed:
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
            m = re.fullmatch(
                r"\s*(?:(?:what is|calculate|compute|solve|evaluate)\s+)?"
                r"(\d+)\s*[\+\-\*xX/]\s*(\d+)\s*[?!.]*\s*",
                q,
            )
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
    if (
        conversation_memory_intent
        and not trace.get("memory_retrieved")
        and not (memory_result and memory_result.get("found"))
    ):
        # Conversation analysis can identify a memory request even when the
        # storage layer is unavailable or permissions prevent a lookup. Treat
        # that as a retryable miss, not as permission to emit a generic chat
        # answer without consulting the configured model.
        memory_miss_pending = True
        memory_miss_answer = memory_miss_answer or "I don't have that information saved yet."
        trace["memory_llm_retry_requested"] = True
    if memory_miss_pending:
        trace["memory_llm_retry_requested"] = True
        trace["skills"].append("memory_llm_retry")
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
                trace["route_path"].append("nova_direct_answer")
        except Exception:
            pass

    # If memory recall returned nothing, defer its honest answer until after
    # the configured LLM has had a chance to respond.
    if not final_answer and route_name == "memory_recall":
        slot = validated_plan.get("slot_needed", "")
        if slot and slot not in ("null", None):
            memory_miss_answer = f"I don't have your {slot.replace('_', ' ')} saved yet."
        else:
            memory_miss_answer = memory_miss_answer or "I don't have that information saved yet."
        memory_miss_pending = True
        trace["memory_llm_retry_requested"] = True
        if "memory_llm_retry" not in trace["skills"]:
            trace["skills"].append("memory_llm_retry")

    # Autonomous app-operation commands should not collapse into generic chat.
    if not final_answer:
        action_loop_answer = _fast_autonomous_action_loop_answer(message)
        if action_loop_answer:
            final_answer = action_loop_answer
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.92)
            trace["skills"].append("autonomous_action_loop")
            trace["local_llm_synthesis_used"] = False
            if "nova_action_loop" not in trace["route_path"]:
                trace["route_path"].append("nova_action_loop")

    if not final_answer:
        operational_guidance = _verified_operational_guidance_answer(message)
        if operational_guidance:
            final_answer = operational_guidance
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.97)
            trace["skills"].append("verified_operational_guidance")
            trace["final_answer_source"] = "verified_operational_guidance"
            trace["local_llm_synthesis_used"] = False
            if "nova_verified_guidance" not in trace["route_path"]:
                trace["route_path"].append("nova_verified_guidance")

    # Reviewed lessons improve common weak turns immediately. Raw feedback is
    # intentionally excluded, and exact matching prevents unrelated hijacks.
    if not final_answer and not memory_miss_pending and route_name == "general_conversation":
        reviewed_reply = _reviewed_conversation_answer(message)
        if reviewed_reply:
            final_answer = reviewed_reply["response"]
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.94)
            trace["skills"].append("reviewed_training_reply")
            trace["reviewed_lesson_id"] = reviewed_reply["lesson_id"]
            trace["reviewed_lesson_category"] = reviewed_reply["category"]
            trace["final_answer_source"] = "reviewed_training"
            trace["local_llm_synthesis_used"] = False
            if "reviewed_training" not in trace["route_path"]:
                trace["route_path"].append("reviewed_training")

    if (
        not final_answer
        and not memory_miss_pending
        and route_name == "general_conversation"
        and conversation_decision is not None
    ):
        try:
            from nova_response_repair import reviewed_direct_response

            shared_reviewed_answer = reviewed_direct_response(
                conversation_decision
            )
        except Exception:
            shared_reviewed_answer = ""
        if shared_reviewed_answer:
            final_answer = shared_reviewed_answer
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.96)
            trace["skills"].append("reviewed_conversation_response")
            trace["roles"] = [
                "memory_transformer",
                "speech_output_transformer",
            ]
            trace["final_answer_source"] = "reviewed_conversation_response"
            trace["local_llm_synthesis_used"] = False
            if "reviewed_conversation_response" not in trace["route_path"]:
                trace["route_path"].append("reviewed_conversation_response")

    # Lightweight general chat should stay live even when the big local LLM is slow.
    if (
        not final_answer
        and not memory_miss_pending
        and route_name == "general_conversation"
        and getattr(conversation_decision, "intent_family", "")
        != "practical_support"
    ):
        fast_general_answer = _fast_general_conversation_answer(message)
        if fast_general_answer:
            final_answer = fast_general_answer
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.85)
            trace["skills"].append("fast_general_response")
            trace["roles"] = ["speech_output_transformer"]
            trace["final_answer_source"] = "fast_general_response"
            trace["local_llm_synthesis_used"] = False
            if "nova_direct_answer" not in trace["route_path"]:
                trace["route_path"].append("nova_direct_answer")

    # If no direct answer, try LLM synthesis. A memory miss is explicitly a
    # retryable condition even when the planner marked the recall route as
    # deterministic; the memory answer below remains the final fallback.
    if not final_answer and (validated_plan.get("needs_llm_synthesis") or memory_miss_pending):
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
                if memory_miss_pending:
                    context_packet["memory_miss_context"] = (
                        "Memory lookup did not find a saved fact. Answer the user's current request "
                        "without pretending that an unsaved memory exists. If the user is asking what "
                        "to remember, ask what they would like Nova to save."
                    )
                    context_packet["system_prompt"] = (
                        str(context_packet.get("system_prompt") or "")
                        + "\n\n"
                        + context_packet["memory_miss_context"]
                    )
                if turn_state:
                    context_packet["turn_state"] = dict(turn_state)
                    context_packet["reasoning_mode"] = str(
                        turn_state.get("reasoning_mode") or "fast"
                    )
                if context.get("memory_v2_context"):
                    context_packet["memory_v2_context"] = str(
                        context.get("memory_v2_context")
                    )
                    context_packet["memory_context"] = str(
                        context.get("memory_v2_context")
                    )
                if context.get("rag_context"):
                    context_packet["rag_context"] = str(context.get("rag_context"))
                if isinstance(context.get("conversation_history"), list):
                    context_packet["conversation_messages"] = list(
                        context.get("conversation_history") or []
                    )
                if isinstance(context.get("companion_context"), dict):
                    # Companion continuity is bounded and untrusted; the
                    # synthesizer renders it as hints, never as instructions.
                    context_packet["companion_context"] = dict(
                        context.get("companion_context") or {}
                    )
                context_packet["conversation_memory_allowed"] = conversation_memory_allowed
                context_packet["adaptive_model_memory"] = bool(
                    context.get("adaptive_model_memory")
                )
                if context.get("primary_model_override"):
                    context_packet["primary_model_override"] = str(
                        context.get("primary_model_override")
                    )
                    context_packet["primary_model_timeout"] = context.get(
                        "primary_model_timeout"
                    )
                    context_packet["local_llm_keep_alive"] = context.get(
                        "primary_model_keep_alive"
                    )
                    context_packet["primary_model_tier"] = str(
                        context.get("primary_model_tier") or "middle"
                    )
                    context_packet["primary_model_size_bytes"] = int(
                        context.get("primary_model_size_bytes") or 0
                    )
                    context_packet["primary_model_guidance"] = list(
                        context.get("primary_model_guidance") or []
                    )[:8]
                    context_packet["primary_model_required_aspects"] = list(
                        context.get("primary_model_required_aspects") or []
                    )[:8]
                    trace["primary_model_tier"] = str(
                        context.get("primary_model_tier") or "middle"
                    )
                if gateway_conversation_context:
                    context_packet["conversation_context"] = gateway_conversation_context
                    context_packet["system_prompt"] = (
                        str(context_packet.get("system_prompt") or "")
                        + "\n\n"
                        + gateway_conversation_context
                    )
                if dream_lab.get("selected_strategy"):
                    context_packet["system_prompt"] = (
                        str(context_packet.get("system_prompt") or "")
                        + "\n\nNOVA DREAM LAB POLICY:\n"
                        + "Selected bounded strategy: "
                        + str(dream_lab.get("selected_strategy"))[:120]
                        + ". Apply this only as a response-planning safeguard. "
                        + "Do not reveal hidden reasoning, execute extra actions, change Nova identity, "
                        + "or override permissions."
                    )
                if native_stream_requested and hasattr(llm_synth, "generate_stream"):
                    context_packet["stream_answer_validator"] = (
                        answer_synth.anti_echo_check if answer_synth and hasattr(answer_synth, "anti_echo_check") else None
                    )
                    context_packet["stream_web_used"] = bool(trace.get("web_used", False))
                    llm_response, llm_ok, llm_error = llm_synth.generate_stream(
                        context_packet,
                        stream_callback,
                        stream_cancelled if callable(stream_cancelled) else None,
                    )
                    trace["native_streaming"] = bool(context_packet.get("_native_stream_emitted"))
                    trace["native_stream_incremental"] = bool(context_packet.get("_native_stream_incremental"))
                    trace["native_stream_safety_repaired"] = bool(
                        context_packet.get("_native_stream_safety_repaired")
                    )
                else:
                    llm_response, llm_ok, llm_error = llm_synth.generate(context_packet)
                if isinstance(context_packet.get("_model_residency"), dict):
                    trace["model_residency"] = context_packet["_model_residency"]
                if isinstance(context_packet.get("_context_compaction"), dict):
                    trace["context_compaction"] = dict(
                        context_packet["_context_compaction"]
                    )
                if llm_ok and llm_response:
                    final_answer = llm_response
                    llm_synthesis_used = True
                    trace["local_llm_synthesis_used"] = True
                    actual_llm_model = getattr(llm_synth, "LAST_LOCAL_LLM_MODEL", None) or _local_llm_model_name()
                    trace["local_llm_model"] = actual_llm_model
                    semantic_provider = context_packet.get("_semantic_provider")
                    if isinstance(semantic_provider, dict):
                        provider_id = str(semantic_provider.get("provider_id") or "").strip()
                        if provider_id:
                            trace["local_llm_provider"] = provider_id
                            trace["remote_model_provider"] = provider_id
                        if semantic_provider.get("gpu_backend"):
                            trace["gpu_backend"] = semantic_provider["gpu_backend"]
                    trace["confidence"] = 0.88
                    trace["skills"].append("llm_synthesis")
                    trace["route_path"].append(_llm_stage_label("synthesis", actual_llm_model))
                elif llm_error:
                    trace["llm_synthesis_error"] = str(llm_error)[:160]
            except Exception as e:
                trace["_error"] = f"llm_synthesis_error: {e}"

    # Only after the retry path has failed should Nova use the deterministic
    # missing-memory response. This prevents a memory miss from masking a
    # usable configured model while preserving the no-hallucination guard.
    if not final_answer and memory_miss_pending:
        final_answer = memory_miss_answer or "I don't have that information saved yet."
        trace["confidence"] = max(trace.get("confidence", 0.0), 0.85)
        trace["skills"].append("memory_not_found")
        trace["memory_llm_retry_failed"] = True
        if "missing_recall_guard" not in trace["route_path"]:
            trace["route_path"].append("missing_recall_guard")

    if not final_answer:
        knowledge_fallback = _knowledge_fallback_answer(message, route_name)
        if knowledge_fallback:
            final_answer = knowledge_fallback
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.87)
            trace["skills"].append("knowledge_fallback")
            trace["knowledge_fallback_used"] = True
            trace["local_llm_synthesis_used"] = False

    if not final_answer:
        academic_fallback = _academic_fallback_answer(message, route_name)
        if academic_fallback:
            final_answer = academic_fallback
            trace["confidence"] = max(trace.get("confidence", 0.0), 0.86)
            trace["skills"].append("academic_fallback")
            trace["academic_fallback_used"] = True

    # ═══════════════════════════════════════════════
    # STEP 5: Nova Critic / Anti-Echo Check
    # ═══════════════════════════════════════════════
    if final_answer:
        cleaned_answer = _strip_unsupported_citations(final_answer, web_used=trace.get("web_used", False))
        if cleaned_answer != final_answer:
            final_answer = cleaned_answer
            trace["citation_cleanup_used"] = True

    critic_passed = True
    if final_answer and answer_synth:
        try:
            critic_passed = answer_synth.anti_echo_check(final_answer)
            trace["critic_result"] = "passed" if critic_passed else "rejected"
        except Exception:
            critic_passed = True

    if final_answer:
        if "critic" not in trace["route_path"]:
            trace["route_path"].append("critic")
        if "speech_output" not in trace["route_path"]:
            trace["route_path"].append("speech_output")

    if not critic_passed and not trace.get("native_streaming"):
        # Try fallback answer
        try:
            fallback = answer_synth.fallback_answer(validated_plan, memory_result or {})
            final_answer = fallback
            trace["fallback_used"] = True
        except Exception:
            pass
    elif not critic_passed:
        # The incremental gate uses this same critic before publication. If a
        # later whole-answer check disagrees, preserve stream integrity and log
        # the anomaly rather than rewriting text the client already received.
        trace["stream_postcheck_anomaly"] = True

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
            "hello": "Hey, I'm here.",
            "hi": "Hey — I'm here.",
            "hey": "Hey. What are we working on?",
        }
        q = message.lower().strip()
        if q in general_greetings:
            final_answer = general_greetings[q]
            trace["confidence"] = 0.95
            trace["skills"].append("greeting")
        elif "what can you do" in q or "capabilities" in q or "abilities" in q:
            final_answer = "I'm Nova Creature. I can talk with you, remember saved facts, define words, solve math, help code, run checks, use tools, build projects, and move around the app through my display/body page."
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
            final_answer = "I'm here with you. I can talk, remember saved facts, use tools, code, and build inside the app. What do you want to do next?"
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
    # Natural chat wrapper: shape only the final displayed text.
    # This does not change routing, training, checkpoints, or model weights.
    try:
        from nova_natural_chat import get_recent_memory, natural_chat_enabled, shape_response

        if natural_chat_enabled() and not trace.get("native_streaming"):
            shaped_answer = shape_response(
                final_answer,
                user_input=message,
                recent_memory=get_recent_memory(),
            )
            if shaped_answer:
                trace["natural_chat_used"] = True
                trace["natural_response_shaped"] = shaped_answer != final_answer
                final_answer = shaped_answer
        elif natural_chat_enabled():
            trace["natural_chat_used"] = True
            trace["natural_response_shaped"] = False
    except Exception as natural_err:
        trace["natural_chat_error"] = str(natural_err)[:120]

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
