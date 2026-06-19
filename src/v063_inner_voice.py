from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def root() -> Path:
    return ROOT


def inner_voice_reflect(
    question: str,
    route: str | None = None,
    answer: str | None = None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Simulate an inner monologue/reflection before answering."""
    q = question.strip().lower()

    reflection_steps = []

    # Step 1: Identify question type
    if any(w in q for w in ["what", "who", "where", "when", "why", "how"]):
        reflection_steps.append("Identified as factual/informational question")
    elif any(w in q for w in ["imagine", "create", "design", "invent"]):
        reflection_steps.append("Identified as creative/imaginative question")
    elif any(w in q for w in ["next", "plan", "build", "step"]):
        reflection_steps.append("Identified as planning/action question")
    elif any(w in q for w in ["remember", "save", "keep"]):
        reflection_steps.append("Identified as memory storage request")
    elif any(w in q for w in ["do that", "ok", "go", "continue"]):
        reflection_steps.append("Identified as follow-up/continuation")
    else:
        reflection_steps.append("Identified as general query")

    # Step 2: Check if a fact is known
    dict_path = root() / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    known_facts = {}
    if dict_path.exists():
        try:
            known_facts = json.loads(dict_path.read_text())
        except Exception:
            pass

    fact_match = None
    for known_q, known_a in known_facts.items():
        if known_q.lower() in q or q in known_q.lower():
            fact_match = {"question": known_q, "answer": known_a}
            reflection_steps.append(f"Dictionary fact found: '{known_q}'")
            break

    if not fact_match:
        reflection_steps.append("No exact dictionary match — will route to role brain")

    # Step 3: Consider route if provided
    if route:
        reflection_steps.append(f"Routing to: {route}")
    else:
        reflection_steps.append("Route not yet determined")

    # Step 4: Formulate response approach
    if answer and answer != "I do not know.":
        reflection_steps.append(f"Answer ready: {answer[:60]}...")
    else:
        reflection_steps.append("No confident answer — will return safe default")

    return {
        "version": "v063_inner_voice",
        "created_at": datetime.now().isoformat(),
        "question": question,
        "reflection_steps": reflection_steps,
        "fact_match": fact_match,
        "known": fact_match is not None,
        "reflection_count": len(reflection_steps),
        "suggested_route": route,
    }


def main() -> int:
    import sys
    ap = __import__("argparse").ArgumentParser()
    ap.add_argument("--prompt", required=True)
    args = ap.parse_args()

    reflection = inner_voice_reflect(args.prompt)
    print(f"INNER VOICE v063 — Reflection on: {args.prompt}\n")
    for i, step in enumerate(reflection["reflection_steps"], 1):
        print(f"  [{i}] {step}")
    print(f"\n  Known fact: {reflection['known']}")
    print(f"  Suggested route: {reflection['suggested_route']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
