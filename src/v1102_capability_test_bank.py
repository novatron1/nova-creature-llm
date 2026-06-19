"""vv1102_capability_test_bank — Intelligence Benchmark + Route Trace Lab"""
from __future__ import annotations; from datetime import datetime; from pathlib import Path
import json, uuid, re, sys, os, time, random
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def capability_test_bank():
    """Module: Create test banks for coding, math, physics, psychology, science, philosophy, logic, memory recall, people memory, sensory routing, planning, truth detection, explanation quality, rapid learning, multi-step reasoning"""

    """Create test banks for all capability domains."""
    banks = {}
    tests = {
        "coding": [
            {"q": "Fix this Python: print('hello'", "type": "syntax", "expected": "missing closing paren"},
            {"q": "What does import os do?", "type": "knowledge", "expected": "os module import"},
            {"q": "Fix: if x = 5:", "type": "syntax", "expected": "use == not ="},
        ],
        "math": [
            {"q": "What is 12 * 12?", "type": "arithmetic", "expected": "144"},
            {"q": "Solve: 2x + 3 = 11", "type": "algebra", "expected": "x = 4"},
        ],
        "physics": [
            {"q": "What is F = ma?", "type": "knowledge", "expected": "Newton's second law"},
        ],
        "science": [
            {"q": "What is photosynthesis?", "type": "biology", "expected": "plants convert light to energy"},
        ],
        "psychology": [
            {"q": "What is classical conditioning?", "type": "cognition", "expected": "Pavlovian learning"},
        ],
        "philosophy": [
            {"q": "What is the Turing Test?", "type": "philosophy_of_mind", "expected": "test of machine intelligence"},
        ],
        "logic": [
            {"q": "All men are mortal. Socrates is a man. Therefore?", "type": "deductive", "expected": "Socrates is mortal"},
        ],
        "memory_recall": [
            {"q": "What is Nova Creature?", "type": "project_knowledge", "expected": "multi-brain LLM system"},
        ],
        "people_memory": [
            {"q": "A person introduces themselves as Alice.", "type": "intro", "expected": "create profile for Alice"},
        ],
        "sensory_routing": [
            {"q": "Camera detects a face.", "type": "vision", "expected": "route to right_hemisphere"},
        ],
        "planning": [
            {"q": "How to build a feature?", "type": "task_order", "expected": "plan, implement, test"},
        ],
        "truth_detection": [
            {"q": "Is the sky made of cheese?", "type": "false_claim", "expected": "no"},
        ],
        "explanation_quality": [
            {"q": "Explain gravity.", "type": "clarity", "expected": "clear explanation"},
        ],
        "rapid_learning": [
            {"q": "Learn: Python 3.12 has new features.", "type": "new_info", "expected": "lesson created"},
        ],
        "multi_step_reasoning": [
            {"q": "If A > B and B > C, what is A vs C?", "type": "chain", "expected": "A > C"},
        ],
    }
    for domain, questions in tests.items():
        path = ROOT / "benchmark_lab" / "test_banks" / f"{domain}_test_bank.json"
        bank = {"domain": domain, "questions": questions, "count": len(questions), "created_at": datetime.now().isoformat()}
        with open(path, "w") as f:
            json.dump(bank, f, indent=2)
        banks[domain] = len(questions)
    return {"version": "v1102_capability_test_bank", "created_at": datetime.now().isoformat(),
            "domains": list(tests.keys()), "total_questions": sum(len(v) for v in tests.values()),
            "banks_created": len(banks), "status": "ok"}


def main():
    print(f"Nova v1102_capability_test_bank")
    r = capability_test_bank()
    print(json.dumps(r, indent=2))
if __name__ == "__main__":
    raise SystemExit(main())
