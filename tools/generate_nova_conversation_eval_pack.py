"""Generate Nova's reviewed 500+ case conversation-routing evaluation pack."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_conversation_eval import CONVERSATION_EVAL_VERSION  # noqa: E402


OUTPUT = ROOT / "data" / "evals" / "nova_conversation_variations_v1.json"
VARIANTS = (
    "{prompt}",
    "Please: {prompt}",
    "Question: {prompt}",
    "Plainly: {prompt}",
    "Be direct: {prompt}",
    "For me: {prompt}",
    "In one sentence: {prompt}",
    "Just answer this: {prompt}",
)


def _seed(
    category: str,
    expected: str,
    signal: str,
    prompts: tuple[str, ...],
) -> list[tuple[str, str, str, str]]:
    return [(category, expected, signal, prompt) for prompt in prompts]


SEEDS = (
    _seed(
        "social",
        "social",
        "social_checkin",
        (
            "How is your day going?",
            "How has your day been?",
            "How was your day?",
            "How's your day today?",
            "What are you doing?",
            "What you doing right now?",
            "What's on your mind?",
            "Hi",
            "Hello Nova",
            "Hey there",
            "Yo Nova",
            "What's up?",
        ),
    )
    + _seed(
        "relationship",
        "relationship",
        "relationship_phrase",
        (
            "Did you miss me?",
            "Do you miss me?",
            "Have you missed me?",
            "Would you miss me?",
            "Did u miss us?",
            "Do u miss me today?",
            "Were you thinking about me?",
            "Were u thinking about us?",
            "Do you love me?",
            "Do u love us?",
            "What do I mean to you?",
            "What would we mean to u?",
        ),
    )
    + _seed(
        "recovery",
        "emotional",
        "emotional_checkin",
        (
            "How are you feeling?",
            "How do you feel?",
            "How you feeling today?",
            "How r u feeling?",
            "Are you happy?",
            "Are you sad?",
            "Are u okay?",
            "Are u excited?",
        ),
    )
    + _seed(
        "followup",
        "follow_up",
        "followup_phrase",
        (
            "Why?",
            "Why did you say that?",
            "What do you mean?",
            "Tell me more.",
            "Another one.",
            "What if?",
            "And then?",
            "How so?",
        ),
    )
    + _seed(
        "current_fact",
        "current_fact",
        "volatile_entity",
        (
            "Who is the current mayor?",
            "Who is the president right now?",
            "What is today's weather?",
            "What is the latest news?",
            "What is the current price?",
            "What is the live score?",
            "What is the current law?",
            "What is the newest regulation?",
            "Who is the current CEO?",
            "What is today's schedule?",
            "What is the latest version?",
            "Who is the governor currently?",
        ),
    )
    + _seed(
        "stable_reasoning",
        "stable_reasoning",
        "question_or_reasoning",
        (
            "Why do leaves fall?",
            "What is photosynthesis?",
            "How many sides does a hexagon have?",
            "Explain gravity.",
            "Compare cats and dogs.",
            "Analyze this tradeoff.",
            "Calculate two plus two.",
            "Design a safe architecture.",
            "What is a molecule?",
            "Why is the Earth round?",
        ),
    )
    + _seed(
        "recovery",
        "open_ended",
        "fallback",
        (
            "Did the mayor miss the meeting?",
            "Tell me another joke.",
            "I love her.",
            "To me that would make you human.",
            "Keep talking with me.",
            "That answer felt robotic.",
            "Give me a kinder reply.",
            "Stay on this subject with me.",
        ),
    )
)


def _canonical(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def build_pack() -> dict:
    cases = []
    seen: set[tuple[str, str]] = set()
    for seed_index, (category, expected, signal, base_prompt) in enumerate(SEEDS):
        for variant_index, template in enumerate(VARIANTS):
            prompt = template.format(prompt=base_prompt)
            key = (_canonical(prompt), expected)
            if key in seen:
                continue
            seen.add(key)
            cases.append(
                {
                    "case_id": (
                        f"{category}-{seed_index + 1:03d}-{variant_index + 1:02d}"
                    ),
                    "category": category,
                    "prompt": prompt,
                    "expected_intent_family": expected,
                    "required_signals": [signal],
                    "prohibited_signals": (
                        [] if expected == "current_fact" else ["volatile_entity"]
                    ),
                }
            )
    if len(cases) < 520:
        raise RuntimeError(f"Expected at least 520 unique cases, built {len(cases)}.")
    return {
        "version": CONVERSATION_EVAL_VERSION,
        "description": (
            "Evaluation-only conversation-routing variations. Never use as "
            "training data or automatic memory."
        ),
        "training_allowed": False,
        "case_count": len(cases),
        "cases": cases,
    }


def main() -> int:
    payload = build_pack()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {payload['case_count']} cases to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
