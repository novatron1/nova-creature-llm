"""v088 — Deep Question Decomposer. Breaks messy questions into sub-questions."""
from __future__ import annotations
from datetime import datetime
from typing import Any

SUBQ_PATTERNS = {
    "robot": {
        "subquestions": [
            "Can it write scripts?",
            "Can it run robot commands?",
            "Does it have capability self-map?",
            "What is missing?",
            "What safety gate is required?",
        ],
        "routes": ["memory_transformer", "left_hemisphere", "right_hemisphere", "critic_conscience_transformer", "planner_transformer"],
    },
    "smarter": {
        "subquestions": [
            "What improves reasoning?",
            "What improves self-checking?",
            "What improves benchmarks?",
        ],
        "routes": ["planner_transformer", "planner_transformer", "planner_transformer"],
    },
    "stack": {
        "subquestions": [
            "What is already stacked?",
            "What would make it smarter?",
        ],
        "routes": ["memory_transformer", "planner_transformer"],
    },
    "default": {
        "subquestions": ["What is the main topic?", "What is the specific question?", "What context is needed?"],
        "routes": ["memory_transformer", "memory_transformer", "memory_transformer"],
    },
}


def decompose_question(question: str, context: dict | None = None) -> dict[str, Any]:
    q = question.lower().strip()
    key = "default"
    if "robot" in q or "move" in q or "script" in q:
        key = "robot"
    elif "smart" in q or "intelligence" in q or "reasoning" in q:
        key = "smarter"
    elif "stack" in q or "version" in q or "upgrade" in q:
        key = "stack"

    pattern = SUBQ_PATTERNS.get(key, SUBQ_PATTERNS["default"])
    subqs = pattern["subquestions"]
    routes = pattern["routes"]

    ambiguity_flags = []
    if q in ("do that", "do it", "go", "continue", "run it", "ok"):
        if context:
            subqs = ["Continue based on previous context."]
            routes = ["memory_transformer"]
        else:
            ambiguity_flags.append("No conversation context available")
            subqs = ["Could you clarify what you mean?"]
            routes = ["critic_conscience_transformer"]

    return {
        "version": "v088_question_decomposer",
        "created_at": datetime.now().isoformat(),
        "original_question": question,
        "cleaned_question": q,
        "subquestions": subqs,
        "dependencies": [],
        "answer_order": list(range(len(subqs))),
        "route_for_each_subquestion": routes[:len(subqs)],
        "ambiguity_flags": ambiguity_flags,
        "clarification_needed": len(ambiguity_flags) > 0,
        "final_summary_prompt": "Summarize the answers in order." if len(subqs) > 1 else "",
    }


def main() -> int:
    print("Nova v088 -- Question Decomposer\n")
    tests = [
        "Can it run a robot and write scripts and know what it can do?",
        "What else can we stack with it and what would make it smarter?",
        "Do that",
    ]
    for t in tests:
        r = decompose_question(t)
        print(f"Q: {t}")
        for i, sq in enumerate(r["subquestions"]):
            print(f"  [{i}] {sq} -> {r['route_for_each_subquestion'][i] if i < len(r['route_for_each_subquestion']) else '?'}")
        if r["ambiguity_flags"]:
            print(f"  Ambiguity: {r['ambiguity_flags']}")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
