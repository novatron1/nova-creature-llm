"""v077 — Dream Training Generator 2.0. Creates role-specific practice sets."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROLES = ["left_hemisphere", "right_hemisphere", "memory_transformer", "planner_transformer",
         "critic_conscience_transformer", "dream_simulation_transformer", "speech_output_transformer"]
CANDIDATES_PATH = ROOT / "data" / "dream_replay" / "v077_generated_training_candidates.jsonl"


def generate_variants(question: str, answer: str, count: int = 20) -> list[dict[str, Any]]:
    """Generate practice variants for a seed Q&A pair."""
    variants = []
    roles_for_answer = {
        "memory_transformer": ["Who", "what", "when", "where", "tell me", "explain", "describe"],
        "left_hemisphere": ["calculate", "math", "solve", "how many", "compute", "what is"],
        "right_hemisphere": ["imagine", "create", "design", "picture", "visualize", "pattern"],
        "planner_transformer": ["next", "plan", "step", "build", "after", "then", "sequence"],
        "critic_conscience_transformer": ["verify", "check", "is it true", "confirm", "validate"],
        "dream_simulation_transformer": ["dream", "practice", "simulate", "what if", "scenario"],
        "speech_output_transformer": ["say", "speak", "word", "phrase", "clean"],
    }
    base_q = question.lower()
    base_a = answer.lower()

    assigned_role = "memory_transformer"
    for role, keywords in roles_for_answer.items():
        if any(kw in base_q for kw in keywords):
            assigned_role = role
            break

    for i in range(count):
        variant_type = "safe" if i < count - 2 else "distorted"
        var_question = f"Practice variant {i+1}: {question}"
        var_answer = answer if variant_type == "safe" else f"Distorted version of {answer}"
        variants.append({
            "variant_id": i + 1,
            "question": var_question,
            "answer": var_answer,
            "role_target": assigned_role,
            "variant_type": variant_type,
            "source_question": question,
            "source_answer": answer,
        })
    return variants


def critic_review(variants: list[dict]) -> dict[str, Any]:
    """Simple critic: approve safe, reject distorted."""
    approved = []
    rejected = []
    for v in variants:
        if v["variant_type"] == "distorted":
            v["critic_decision"] = "rejected"
            v["critic_reason"] = "Distorted content not safe for training"
            rejected.append(v)
        else:
            v["critic_decision"] = "approved"
            v["critic_reason"] = "Safe paraphrase"
            approved.append(v)
    return {"approved": approved, "rejected": rejected,
            "approved_count": len(approved), "rejected_count": len(rejected)}


def export_training_candidates(approved: list[dict]) -> dict[str, Any]:
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    for a in approved:
        record = {
            "source": "v077_dream_generator",
            "question": a["question"],
            "answer": a["answer"],
            "role_target": a["role_target"],
            "variant_id": a["variant_id"],
            "approved_at": datetime.now().isoformat(),
            "exported_to_training": True,
        }
        with CANDIDATES_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        count += 1
    return {"exported_count": count, "path": str(CANDIDATES_PATH.relative_to(ROOT))}


def run_generator(question: str, answer: str, count: int = 20) -> dict[str, Any]:
    variants = generate_variants(question, answer, count)
    review = critic_review(variants)
    export = export_training_candidates(review["approved"])
    return {
        "version": "v077_dream_training_generator",
        "created_at": datetime.now().isoformat(),
        "seed_question": question,
        "seed_answer": answer,
        "variants_generated": len(variants),
        "approved": review["approved_count"],
        "rejected": review["rejected_count"],
        "exported": export["exported_count"],
        "candidates_path": export["path"],
    }


def main():
    print("Nova v077 -- Dream Training Generator 2.0\n")
    result = run_generator("Who created you?", "Mr. Novotron", 20)
    print(f"Seed: {result['seed_question']} -> {result['seed_answer']}")
    print(f"Generated: {result['variants_generated']}")
    print(f"Approved: {result['approved']}")
    print(f"Rejected: {result['rejected']}")
    print(f"Exported: {result['exported']}")
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
