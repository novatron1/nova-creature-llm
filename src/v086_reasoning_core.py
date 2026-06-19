"""v086 — Reasoning Core. Structured internal reasoning before final answer."""
from __future__ import annotations
import json, re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PROBLEM_TYPES = {
    "unknown_personal_fact": ["my favorite", "my name", "my age", "my birthday", "my phone", "my address"],
    "math": ["times", "plus", "minus", "divided", "multiply", "calculate", "=", "+", "-", "*", "x "],
    "code": ["code", "script", "function", "python", "debug", "error", "fix", "write"],
    "project_status": ["version", "status", "current", "installed", "stack", "roadmap"],
    "planning": ["next", "build", "upgrade", "plan", "step", "after", "improve"],
    "memory_lookup": ["who", "name", "created", "remember", "what is the", "where"],
    "concept_explanation": ["what is", "explain", "define", "how does", "describe"],
    "strategy": ["should", "best", "prioritize", "what to do", "recommend"],
    "error_debugging": ["error", "fail", "bug", "traceback", "doesn't work", "broken"],
    "ambiguous_request": ["do that", "do it", "go", "continue", "run it", "ok"],
    "speculative_question": ["maybe", "what if", "could", "possibly", "might", "imagine"],
}


def detect_problem_type(question: str) -> str:
    q = question.lower().strip()
    for ptype, keywords in PROBLEM_TYPES.items():
        if any(kw in q for kw in keywords):
            return ptype
    return "concept_explanation"


def reason_about_question(question: str, context: dict | None = None) -> dict[str, Any]:
    cleaned = " ".join(question.strip().split())
    intent = "answer" if "?" in cleaned else "respond"
    problem_type = detect_problem_type(cleaned)

    reasoning_steps = [
        f"Received question: {cleaned[:80]}",
        f"Detected problem type: {problem_type}",
    ]

    known_facts = []
    unknowns = []
    assumptions = []
    critic_notes = []

    # Check dictionary memory for known facts
    dict_path = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    if dict_path.exists():
        try:
            facts = json.loads(dict_path.read_text())
            for k, v in facts.items():
                if any(word in cleaned for word in k.lower().split()):
                    known_facts.append({"question": k, "answer": str(v)[:200]})
        except Exception:
            pass

    # Check for personal/unknown fact patterns
    if problem_type == "unknown_personal_fact":
        unknowns.append("Personal fact not in memory")
        critic_notes.append("Do not guess personal facts")
    elif problem_type == "speculative_question":
        unknowns.append("Speculative question — cannot confirm")
        critic_notes.append("Flag as uncertain, do not train")

    # Route recommendation
    route_map = {
        "math": "left_hemisphere",
        "code": "left_hemisphere",
        "project_status": "memory_transformer",
        "planning": "planner_transformer",
        "memory_lookup": "memory_transformer",
        "unknown_personal_fact": "critic_conscience_transformer",
        "concept_explanation": "right_hemisphere",
        "strategy": "planner_transformer",
        "error_debugging": "left_hemisphere",
        "ambiguous_request": "memory_transformer",
        "speculative_question": "critic_conscience_transformer",
    }
    route_recommendation = route_map.get(problem_type, "memory_transformer")

    reasoning_steps.append(f"Route recommendation: {route_recommendation}")
    if known_facts:
        reasoning_steps.append(f"Found {len(known_facts)} matching fact(s) in dictionary memory")
    if unknowns:
        reasoning_steps.append(f"Unknowns identified: {len(unknowns)}")

    answer_candidate = ""
    if problem_type == "math":
        # Simple math extraction
        numbers = re.findall(r'\d+', cleaned)
        if "times" in cleaned or "x " in cleaned:
            if len(numbers) >= 2:
                answer_candidate = str(int(numbers[0]) * int(numbers[1]))
        elif "plus" in cleaned:
            if len(numbers) >= 2:
                answer_candidate = str(int(numbers[0]) + int(numbers[1]))

    confidence = 0.9 if known_facts else (0.5 if unknowns else 0.7)

    # Final answer
    if problem_type == "unknown_personal_fact":
        final_answer = "I do not know."
    elif answer_candidate:
        final_answer = answer_candidate
    elif known_facts:
        final_answer = str(known_facts[0]["answer"])
    elif problem_type == "speculative_question":
        final_answer = "I am not sure. That seems uncertain."
    else:
        final_answer = None  # will be routed to role brain

    return {
        "version": "v086_reasoning_core",
        "created_at": datetime.now().isoformat(),
        "original_question": question,
        "cleaned_question": cleaned,
        "detected_intent": intent,
        "problem_type": problem_type,
        "known_facts": known_facts,
        "assumptions": assumptions,
        "unknowns": unknowns,
        "reasoning_steps": reasoning_steps,
        "answer_candidate": answer_candidate,
        "confidence": confidence,
        "critic_notes": critic_notes,
        "final_answer": final_answer,
        "route_recommendation": route_recommendation,
        "should_use_memory": problem_type in ("memory_lookup", "project_status"),
        "should_use_dictionary": bool(known_facts),
        "should_use_planner": problem_type == "planning",
        "should_use_critic": problem_type in ("unknown_personal_fact", "speculative_question"),
        "should_request_clarification": problem_type == "ambiguous_request",
    }


def main() -> int:
    print("Nova v086 -- Reasoning Core\n")
    tests = [
        "What is 12 times 12?",
        "Who created you?",
        "What is my favorite color?",
        "Build the next upgrade after v061.",
        "Maybe this checkpoint is better.",
    ]
    for t in tests:
        r = reason_about_question(t)
        print(f"Q: {t}")
        print(f"  Type: {r['problem_type']}")
        print(f"  Route: {r['route_recommendation']}")
        print(f"  Final: {r['final_answer'] or '(routed)'}")
        if r['critic_notes']:
            print(f"  Critic: {r['critic_notes']}")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
