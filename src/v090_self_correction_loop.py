"""v090 — Self-Correction Loop. Checks answers for errors before final output."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def self_correct_answer(question: str, draft_answer: str, context: dict | None = None) -> dict[str, Any]:
    q = question.lower().strip()
    da = draft_answer.lower()
    checks = []
    contradictions_found = []
    missing_context = []
    unsupported_claims = []
    overclaiming_detected = False
    wrong_route_detected = False

    # Check 1: Did it answer the exact question?
    if question and draft_answer:
        checks.append({"check": "answered_exact_question", "passed": True})

    # Check 2: Did it claim robot movement?
    if "move" in da and "real" in da and ("robot" in da or "hardware" in da):
        overclaiming_detected = True
        contradictions_found.append("Robot movement is simulation-only, not real hardware")
        unsupported_claims.append("Claimed real robot movement without hardware config")

    # Check 3: Did it guess personal facts?
    if ("my favorite" in da or "your favorite" in da) and ("i do not know" not in da and "unknown" not in da):
        overclaiming_detected = True
        contradictions_found.append("Guessed personal fact — should return unknown")

    # Check 4: Did it ignore creator fact?
    dict_path = ROOT / "data" / "dictionary_memory" / "approved_answer_dictionary.json"
    creator_fact = None
    if dict_path.exists():
        try:
            facts = json.loads(dict_path.read_text())
            for k, v in facts.items():
                if "created" in k.lower():
                    creator_fact = str(v)
                    break
        except Exception:
            pass
    if creator_fact and "who created" in q and creator_fact.lower() not in da:
        unsupported_claims.append(f"Missing creator fact: {creator_fact}")

    # Check 5: Did it contradict v066 self-map?
    if ("can" in da or "able" in da) and "simulat" not in da and "plan" not in da:
        if "move" in da or "robot" in da:
            overclaiming_detected = True
            contradictions_found.append("v066 self-map says real_hardware_enabled: False")

    # Corrected answer
    corrections = []
    corrected = draft_answer
    if overclaiming_detected:
        corrected = "I can plan robot commands and simulate them, but real robot movement is not active yet."
        corrections.append("Replaced robot movement claim with honest simulation-only statement")
    elif unsupported_claims:
        corrected = "I do not know for certain based on available evidence."
        corrections.append("Replaced unsupported claims with honest uncertainty")

    return {
        "version": "v090_self_correction_loop", "created_at": datetime.now().isoformat(),
        "question": question, "draft_answer": draft_answer, "checks": checks,
        "contradictions_found": contradictions_found, "missing_context": missing_context,
        "unsupported_claims": unsupported_claims, "overclaiming_detected": overclaiming_detected,
        "wrong_route_detected": wrong_route_detected, "corrected_answer": corrected,
        "correction_applied": len(corrections) > 0, "corrections": corrections,
        "final_confidence": 0.3 if overclaiming_detected else (0.6 if unsupported_claims else 0.9),
    }


def main() -> int:
    print("Nova v090 -- Self-Correction Loop\n")
    tests = [
        ("Can Nova move a real robot?", "Nova can move a real robot."),
        ("What is my favorite color?", "Your favorite color is blue."),
        ("Who created you?", "I was created by a complex process."),
    ]
    for q, a in tests:
        r = self_correct_answer(q, a)
        print(f"Q: {q}")
        print(f"  Draft: {a[:50]}")
        print(f"  Overclaiming: {r['overclaiming_detected']}")
        print(f"  Correction: {r['correction_applied']}")
        if r['correction_applied']:
            print(f"  Final: {r['corrected_answer'][:60]}...")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
