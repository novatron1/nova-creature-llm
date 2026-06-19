"""v095 — Intelligence Router. Routes questions through the full intelligence stack."""
from __future__ import annotations
import sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def answer_intelligently(question: str, context: dict | None = None) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    route = "standard"
    final_answer = ""
    confidence = 0.0
    benchmark_safe = True

    # Step 1: Decompose if messy
    from v088_question_decomposer import decompose_question
    decomposed = decompose_question(question, context)

    # Step 2: Evidence check
    from v089_evidence_checker import check_evidence
    evidence = check_evidence(question, context)

    # Step 3: Strategy check for planning questions
    strategy = None
    if any(w in question.lower() for w in ["should", "best", "recommend", "next", "plan"]):
        from v093_strategy_brain import choose_strategy
        options = [
            {"name": "improve reasoning core", "risk": "low", "payoff": "high", "dependencies": [], "benchmark_value": 10},
            {"name": "build robot movement now", "risk": "high", "payoff": "low", "dependencies": ["safety"], "benchmark_value": -10},
            {"name": "build benchmark dashboard", "risk": "low", "payoff": "medium", "dependencies": [], "benchmark_value": 7},
        ]
        strategy = choose_strategy(options, {"question": question})

    # Step 4: Reason
    from v086_reasoning_core import reason_about_question
    reasoning = reason_about_question(question, context)
    final_answer = reasoning.get("final_answer")
    if final_answer:
        route = reasoning.get("route_recommendation", "standard")
        confidence = reasoning.get("confidence", 0.5)
    else:
        # Fallback: use v052 router
        from v052_role_brain_router import run as router_run
        router_result = router_run(question)
        results_list = router_result.get("results", [])
        if results_list:
            r0 = results_list[0]
            final_answer = r0.get("final_answer", "") or r0.get("reasoned_response", "")
            route = r0.get("selected_route", "unknown_fallback")
            confidence = 0.7
        else:
            final_answer = "I cannot answer that confidently."
            route = "unknown_fallback"
            confidence = 0.1

    # Step 5: Self-correct
    from v090_self_correction_loop import self_correct_answer
    correction = self_correct_answer(question, final_answer or "", context)
    if correction["correction_applied"]:
        final_answer = correction["corrected_answer"]
        confidence = correction["final_confidence"]

    # Step 6: Debate for high-stakes topics
    debate = None
    if any(w in question.lower() for w in ["should", "enable", "real robot", "move robot"]):
        from v094_debate_brain import run_debate
        debate = run_debate(question, context)
        if debate.get("final_decision"):
            final_answer = debate["final_answer"]
            route = "debate"

    return {
        "version": "v095_intelligence_router", "created_at": datetime.now().isoformat(),
        "question": question, "decomposed": decomposed, "evidence": evidence,
        "reasoning": reasoning, "planner": None, "strategy": strategy,
        "debate": debate, "self_correction": correction, "final_answer": final_answer,
        "route": route, "confidence": confidence, "benchmark_safe": benchmark_safe,
    }


def main() -> int:
    print("Nova v095 -- Intelligence Router\n")
    tests = [
        "Can Nova control a robot yet?",
        "What is the smartest next upgrade?",
        "What is 12 times 12?",
        "Who created you?",
        "Should we build robot movement or make the brain smarter first?",
    ]
    for q in tests:
        r = answer_intelligently(q)
        print(f"Q: {q}")
        print(f"  Route: {r['route']}")
        print(f"  Answer: {r['final_answer'][:80] if r['final_answer'] else '(routed)'}")
        print(f"  Confidence: {r['confidence']}")
        print()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
