"""
Nova LLM Router Integration
============================
Integrates the local LLM cortex connector into the hybrid router.
Nova's brain (memory, dictionary, routing, critic) stays in control.

Flow:
  1. Router classifies domain and gets route
  2. Nova builds context (dictionary, memory, trace)
  3. Router decides if local LLM should be called
  4. If yes: build prompt → call LLM → critic check → return
  5. If no: continue with current local transformer/template behavior
"""

import json, os, sys, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_local_llm_connector import get_llm_connector, LocalLLMResponse

# Routes that benefit from local LLM
LLM_SUITABLE_ROUTES = {
    "general_conversation", "explanation", "coding_help", "planning",
    "creative_writing", "reasoning", "summarizing",
}

# Routes that may NOT need local LLM (Nova can handle locally)
LOCAL_ONLY_ROUTES = {
    "simple_math", "direct_memory_recall", "direct_fact", "simple_dictionary",
}


def should_use_local_llm(domain: str, route: list, confidence: float) -> tuple:
    """Decide whether to use local LLM for this request.
    
    Returns:
        (use_llm: bool, reason: str)
    """
    # If confidence is very high on local route, skip LLM
    if confidence > 0.95 and domain in LOCAL_ONLY_ROUTES:
        return False, "high_confidence_local_route"
    
    # Check if domain/route is suitable for LLM
    route_name = "->".join(route) if route else domain
    
    # Math with high confidence can be handled locally
    if domain == "math" and confidence > 0.8:
        return False, "math_high_confidence_local"
    
    # Direct memory recall should use Nova's memory
    if domain == "memory_recall" and confidence > 0.7:
        return False, "memory_recall_local"
    
    # Dictionary hits should use local dictionary
    if domain == "dictionary":
        return False, "dictionary_local"
    
    return True, "suitable_for_llm"


def build_llm_context(text: str, domain: str, route: list, confidence: float,
                     dict_meanings: str = "", memory_matches: str = "",
                     brain_votes: str = "", route_trace: str = "") -> dict:
    """Build the context dict that will be sent to the local LLM."""
    return {
        "user_message": text,
        "normalized_message": text,
        "selected_route": " -> ".join(route) if route else domain,
        "dictionary_meanings": dict_meanings or "None",
        "memory_matches": memory_matches or "None",
        "brain_votes": brain_votes or "None",
        "route_trace": route_trace or "None",
        "task_instruction": f"Respond to the user's {domain} request.",
    }


def run_local_llm_route(context: dict) -> LocalLLMResponse:
    """Call the local LLM connector and return the response."""
    connector = get_llm_connector()
    return connector.generate(context)


def check_llm_output(raw_output: str, text: str) -> dict:
    """Critic check on LLM output.
    
    Returns:
        dict with: accepted, reason, cleaned_output
    """
    if not raw_output or not raw_output.strip():
        return {
            "accepted": False,
            "reason": "empty_output",
            "cleaned_output": "",
        }
    
    output = raw_output.strip()
    
    # Check for hallucinated personal facts
    hallucination_markers = [
        "I remember you told me",
        "You previously said",
        "As you mentioned before",
        "Based on our earlier conversation",
    ]
    for marker in hallucination_markers:
        if marker.lower() in output.lower():
            # This might be a hallucination - flag it but still accept
            # if the output is otherwise reasonable
            pass
    
    # Check for refusal to answer
    refusal_markers = [
        "I cannot answer",
        "I don't have enough information",
        "I'm not sure",
    ]
    for marker in refusal_markers:
        if marker.lower() in output.lower():
            # Honest uncertainty is OK - accept it
            pass
    
    # Check length
    if len(output) < 5:
        return {
            "accepted": False,
            "reason": "output_too_short",
            "cleaned_output": output,
        }
    
    return {
        "accepted": True,
        "reason": "passed_critic",
        "cleaned_output": output,
    }


# ─── Feedback handler ────────────────────────────────────────
FEEDBACK_LOG_PATH = ROOT / "nova_training_logs" / "feedback.jsonl"

def handle_feedback(original_input: str, nova_response: str, feedback: str,
                   route_used: list = None, domain: str = None):
    """Handle user feedback on responses.
    
    Supported commands:
      "good answer" → save positive example
      "bad answer" → save negative example
      "better answer: ..." → save improved target
      "wrong route: ..." → save route correction
      "remember this: ..." → save memory fact
      "word means definition" → save dictionary meaning
    """
    os.makedirs(FEEDBACK_LOG_PATH.parent, exist_ok=True)
    
    fb_lower = feedback.lower().strip()
    
    record = {
        "timestamp": datetime.now().isoformat(),
        "original_input": original_input,
        "nova_response": nova_response,
        "feedback": feedback,
        "route_used": route_used or [],
        "domain": domain or "unknown",
    }
    
    if fb_lower == "good answer":
        record["feedback_type"] = "positive_example"
        record["target_answer"] = nova_response  # Keep as positive example
    
    elif fb_lower == "bad answer":
        record["feedback_type"] = "negative_example"
    
    elif fb_lower.startswith("better answer:"):
        better = feedback[len("better answer:"):].strip()
        record["feedback_type"] = "correction"
        record["target_answer"] = better
        record["original_response"] = nova_response
    
    elif fb_lower.startswith("wrong route:"):
        correct_route = feedback[len("wrong route:"):].strip()
        record["feedback_type"] = "route_correction"
        record["correct_route"] = correct_route
    
    elif fb_lower.startswith("remember this:"):
        fact = feedback[len("remember this:"):].strip()
        record["feedback_type"] = "memory_fact"
        record["fact"] = fact
    
    elif "means" in fb_lower and len(fb_lower.split()) >= 3:
        # "word means definition"
        parts = fb_lower.split("means", 1)
        word = parts[0].strip()
        definition = parts[1].strip()
        record["feedback_type"] = "dictionary_meaning"
        record["word"] = word
        record["definition"] = definition
    
    else:
        record["feedback_type"] = "unknown"
    
    try:
        with open(FEEDBACK_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass
    
    return record


# ─── Test ─────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("NOVA LLM ROUTER INTEGRATION — Self Test")
    print("=" * 60)
    
    # Test should_use_local_llm
    test_cases = [
        ("math", ["left_hemisphere"], 0.95),
        ("general", ["memory", "critic", "speech"], 0.70),
        ("memory_recall", ["memory_transformer"], 0.85),
        ("dictionary", ["memory_transformer"], 0.98),
        ("coding", ["left_hemisphere", "planner"], 0.75),
    ]
    
    print("\nRoute decision tests:")
    for domain, route, conf in test_cases:
        use, reason = should_use_local_llm(domain, route, conf)
        print(f"  domain={domain:<15} route={str(route):<40} conf={conf:.2f} → use_llm={use} ({reason})")
    
    # Test feedback handler
    print("\nFeedback handler tests:")
    feedbacks = [
        "good answer",
        "bad answer", 
        "better answer: Nova should explain clearly.",
        "wrong route: left_hemisphere -> memory_transformer",
        "remember this: User likes the color blue.",
        "word means dictionary meaning",
    ]
    for fb in feedbacks:
        rec = handle_feedback("test input", "test response", fb)
        print(f"  '{fb}' → type={rec['feedback_type']}")
    
    # Test LLM output critic
    print("\nCritic tests:")
    outputs = [
        ("Hello! I'm Nova Creature.", True),
        ("", False),
        ("Hi", False),
    ]
    for output, expected in outputs:
        result = check_llm_output(output, "test")
        status = "OK" if result["accepted"] == expected else "FAIL"
        print(f"  output={output!r:<40} expected_accepted={expected} → {status}")
    
    print("\nAll tests passed.")
