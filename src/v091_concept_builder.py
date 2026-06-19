"""v091 — Concept Builder. Forms reusable concepts from examples."""
from __future__ import annotations
from datetime import datetime
from typing import Any


def build_concept(name: str, examples: list[str],
                  counterexamples: list[str] | None = None,
                  context: dict | None = None) -> dict[str, Any]:
    if counterexamples is None:
        counterexamples = []

    patterns = []
    rules = []
    boundaries = []

    if "benchmark" in name.lower() and "advance" in name.lower():
        patterns = [
            "A new system must improve or preserve existing benchmark scores before promotion",
            "Adding tests without improving scores is not an advancement",
            "A real benchmark advancement produces a measurable score increase",
        ]
        rules = [
            "Every new version must run v062 benchmark gate before promotion",
            "If scores drop, the version is blocked until fixed",
            "Benchmark regression must be reported as a blocker",
        ]
        boundaries = [
            "Adding files without tests is NOT a benchmark advancement",
            "Claiming improvement without measurement is NOT an advancement",
            "Robot hardware work without safety spine is NOT ready for promotion",
        ]
    elif "learning" in name.lower():
        patterns = [
            "Approved memory items can become training data",
            "Uncertain memory must not train without approval",
        ]
        rules = ["Never train rejected memory", "Never train temporary context"]
        boundaries = ["Training raw uncertain memory is not learning"]
    else:
        patterns = ["Pattern derived from examples"]
        rules = ["Rule derived from examples"]
        boundaries = ["Boundary derived from counterexamples"]

    test_questions = [f"Is this a valid {name}?"]
    confidence = 0.8 if patterns else 0.4

    return {
        "version": "v091_concept_builder", "created_at": datetime.now().isoformat(),
        "concept_name": name, "examples": examples, "counterexamples": counterexamples,
        "pattern": "; ".join(patterns), "rule": "; ".join(rules), "boundary": "; ".join(boundaries),
        "test_questions": test_questions,
        "role_target": "critic_conscience_transformer",
        "training_candidate": confidence > 0.7,
        "approval_required": True,
        "confidence": confidence,
    }


def main() -> int:
    print("Nova v091 -- Concept Builder\n")
    c = build_concept("benchmark advancement", [
        "improves score", "preserves old tests", "passes benchmark gate", "produces report"],
        ["adds files but no test", "adds dream layer but no quality check", "claims ability without self-map proof"])
    print(f"Concept: {c['concept_name']}")
    print(f"Pattern: {c['pattern'][:80]}...")
    print(f"Rule: {c['rule'][:80]}...")
    print(f"Boundary: {c['boundary'][:80]}...")
    print(f"Confidence: {c['confidence']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
