"""v063 — Dream Critic

Reviews dream-generated lessons, approves safe variants, rejects distorted ones.
"""

from __future__ import annotations

import json, re
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROLES = [
    "left_hemisphere", "right_hemisphere", "memory_transformer",
    "planner_transformer", "critic_conscience_transformer",
    "dream_simulation_transformer", "speech_output_transformer",
]

STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
              "being", "have", "has", "had", "do", "does", "did", "will",
              "would", "could", "should", "may", "might", "shall", "can",
              "to", "of", "in", "for", "on", "with", "at", "by", "from",
              "as", "into", "through", "during", "before", "after", "above",
              "below", "between", "out", "off", "over", "under", "again",
              "further", "then", "once", "here", "there", "when", "where",
              "why", "how", "all", "each", "every", "both", "few", "more",
              "most", "some", "any", "no", "not", "only", "own", "same",
              "so", "than", "too", "very", "just", "also"}


def root() -> Path:
    return ROOT


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r'[^a-z0-9+\-*x ]+', " ", s)
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def tokenize(text: str) -> set[str]:
    return {w for w in normalize(text).split() if w not in STOP_WORDS and len(w) > 1}


def jaccard_similarity(a: str, b: str) -> float:
    ta = tokenize(a)
    tb = tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def review_dream(dream: dict[str, Any]) -> dict[str, Any]:
    """Review a single dream lesson and decide approve/reject."""
    prompt = dream.get("prompt", "")
    answer = dream.get("answer", "")
    source = dream.get("source_text", dream.get("source", ""))

    # Check for distortion
    reasons = []
    distorted = False

    # Rule 1: Answer must contain key content words from source
    if source:
        sim = jaccard_similarity(answer, source)
        if sim < 0.15:
            distorted = True
            reasons.append(f"Answer too dissimilar from source (jaccard={sim:.2f})")

    # Rule 2: Answer should not be empty or too short
    if len(answer.strip()) < 3:
        distorted = True
        reasons.append("Answer too short")

    # Rule 3: Check for hallucination markers
    hallu_markers = ["i am a", "i am the", "i like to", "i want to", "i think i",
                     "this is a dream", "in my dream", "i dreamed"]
    for marker in hallu_markers:
        if marker in answer.lower():
            distorted = True
            reasons.append(f"Hallucination marker detected: '{marker}'")
            break

    # Rule 4: Keep math/logic answers consistent
    if any(x in prompt.lower() for x in ["math", "plus", "minus", "times"]):
        numbers_in_prompt = re.findall(r"\\d+", prompt)
        numbers_in_answer = re.findall(r"\\d+", answer)
        if numbers_in_prompt and not numbers_in_answer:
            distorted = True
            reasons.append("Math prompt but no numbers in answer")

    # Rule 5: Keep identity answers accurate
    if "who created" in prompt.lower() or "created you" in prompt.lower():
        if "novotron" not in answer.lower() and "creator" not in answer.lower():
            distorted = True
            reasons.append("Identity question but answer does not reference creator")

    # Decision
    if distorted:
        decision = "rejected"
        confidence = 0.3
    else:
        # Score based on similarity
        sim_score = jaccard_similarity(answer, source) if source else 0.5
        if sim_score >= 0.3:
            decision = "approved"
            confidence = min(0.95, 0.5 + sim_score)
        else:
            decision = "approved"
            confidence = 0.6

    review = {
        "version": "v063_dream_critic",
        "reviewed_at": datetime.now().isoformat(),
        "dream": dream,
        "decision": decision,
        "confidence": round(confidence, 3),
        "reasons": reasons,
        "distorted": distorted,
        "can_train": decision == "approved" and not distorted,
    }
    return review


def review_dreams(dreams: list[dict[str, Any]]) -> dict[str, Any]:
    """Review multiple dreams, store approved and rejected separately."""
    approved = []
    rejected = []

    for dream in dreams:
        review = review_dream(dream)
        if review["decision"] == "approved":
            approved.append(review)
        else:
            rejected.append(review)

    # Save to storage
    dream_dir = root() / "data" / "dream_replay"
    dream_dir.mkdir(parents=True, exist_ok=True)

    for review_list, filename in [(approved, "critic_approved_dreams.jsonl"),
                                   (rejected, "rejected_dreams.jsonl")]:
        path = dream_dir / filename
        with path.open("a", encoding="utf-8") as f:
            for r in review_list:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    return {
        "version": "v063_dream_critic",
        "created_at": datetime.now().isoformat(),
        "total_reviewed": len(dreams),
        "approved_count": len(approved),
        "rejected_count": len(rejected),
        "approved": approved,
        "rejected": rejected,
    }


def generate_dream_variants(question: str, answer: str, count: int = 12) -> list[dict[str, Any]]:
    """Generate safe dream variants from a Q&A pair."""
    variants = []
    base_prompt = normalize(question)
    base_answer = normalize(answer)

    # Safe paraphrases
    safe_variants = [
        f"What is {base_answer}?",
        f"Tell me {base_answer}",
        f"I heard the answer is {base_answer}",
        f"Can you confirm {base_answer}?",
        f"The answer to {base_prompt} is what?",
        f"Explain {base_answer} to me",
        f"What do you know about {base_answer}?",
        f"I want to learn about {base_answer}",
        f"Is {base_answer} correct?",
        f"Remind me about {base_answer}",
    ]

    # Potentially distorted variants
    distorted_variants = [
        f"I am the one who created everything",
        f"In my dream, {base_answer} was completely wrong",
        f"I dreamed that {base_answer} is the opposite of truth",
        f"The real answer is something else entirely",
    ]

    for i, var_prompt in enumerate(safe_variants):
        variants.append({
            "prompt": var_prompt,
            "answer": answer,
            "source_text": answer,
            "dream_type": "safe_paraphrase",
            "variant_index": i,
        })

    for i, var_prompt in enumerate(distorted_variants):
        variants.append({
            "prompt": var_prompt,
            "answer": var_prompt.split("that ")[-1] if "that " in var_prompt else var_prompt,
            "source_text": answer,
            "dream_type": "distorted",
            "variant_index": len(safe_variants) + i,
        })

    return variants[:count]


def main() -> int:
    import sys
    print("Nova Creature v063 — Dream Critic\n")

    # Generate test variants
    variants = generate_dream_variants("Who created you?", "Mr. Novotron", count=12)
    print(f"Generated {len(variants)} dream variants")

    # Review all
    result = review_dreams(variants)
    print(f"  Approved: {result['approved_count']}")
    print(f"  Rejected: {result['rejected_count']}")

    for r in result["approved"]:
        print(f"  ✅ [{r['dream']['variant_index']}] {r['dream']['prompt'][:50]}")

    for r in result["rejected"]:
        print(f"  ❌ [{r['dream']['variant_index']}] {r['dream']['prompt'][:50]} -> {r['reasons'][:1]}")

    # Save report
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    report_path = reports_dir / "v063_dream_critic_report.json"
    report_path.write_text(json.dumps({
        "version": "v063_dream_critic",
        "generated": len(variants),
        "approved": result["approved_count"],
        "rejected": result["rejected_count"],
        "created_at": result["created_at"],
    }, indent=2))
    print(f"\nReport: reports/v063_dream_critic_report.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
