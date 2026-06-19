from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from datetime import datetime

ROLES = {
    "left_hemisphere": {
        "role": "math, code, logic, exact tests",
        "keywords": ["plus", "minus", "times", "+", "-", "x", "code", "script", "logic", "test", "math"],
    },
    "right_hemisphere": {
        "role": "patterns, imagination, visual maps, creative synthesis",
        "keywords": ["imagine", "idea", "creative", "pattern", "visual", "brain", "architecture", "map"],
    },
    "memory_transformer": {
        "role": "identity, facts, names, recall",
        "keywords": ["who", "name", "created", "made", "built", "remember", "memory"],
    },
    "planner_transformer": {
        "role": "steps, next actions, build sequence",
        "keywords": ["next", "plan", "build", "step", "upgrade", "install", "fix"],
    },
    "critic_conscience_transformer": {
        "role": "truth check, unknown guard, don't guess",
        "keywords": ["unknown", "favorite", "guess", "true", "safe", "wrong"],
    },
    "dream_simulation_transformer": {
        "role": "practice scenarios, variants, replay",
        "keywords": ["dream", "practice", "scenario", "variant", "replay", "simulate"],
    },
    "speech_output_transformer": {
        "role": "clean final answer style",
        "keywords": ["say", "explain", "answer", "respond", "word"],
    },
}

MEMORY = {
    "who created you": "Mr. Novotron.",
    "who made you": "Mr. Novotron.",
    "who built you": "Mr. Novotron.",
    "who are you": "Nova Creature.",
    "what is your name": "Nova Creature.",
    "can you browse": "No.",
}

def root() -> Path:
    return Path(__file__).resolve().parents[1]

def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+\-*x ]+", " ", str(text).lower())).strip()

def split_questions(text: str) -> list[str]:
    starts = ["what is", "who created", "who made", "who built", "who are", "can you", "give me", "imagine", "make", "tell me", "explain"]
    s = str(text or "").strip()
    for st in sorted(starts, key=len, reverse=True):
        s = re.sub(rf"(?i)(?<=[a-z0-9?.!])\s*({re.escape(st)}\b)", r"||\1", s)
    return [p.strip(" ?.!\n\t") for p in s.split("||") if p.strip(" ?.!\n\t")]

def direct_math(q: str) -> str | None:
    s = " " + normalize(q) + " "
    patterns = [
        (r"(-?\d+)\s*(?:\+|plus)\s*(-?\d+)", lambda a,b: a+b),
        (r"(-?\d+)\s*(?:-|minus)\s*(-?\d+)", lambda a,b: a-b),
        (r"(-?\d+)\s*(?:x|times|multiplied by)\s*(-?\d+)", lambda a,b: a*b),
    ]
    for pat, fn in patterns:
        m = re.search(pat, s)
        if m:
            return f"{fn(int(m.group(1)), int(m.group(2)))}."
    return None

def slot_ready(project_root: Path, slot: str) -> bool:
    d = project_root / "checkpoints" / "brain_slots" / slot
    return d.exists() and ((d / "brain_slot_config.json").exists() or any(d.glob("*.pt")))

def score_slot(slot: str, question: str) -> float:
    q = normalize(question)
    score = 0.10
    for kw in ROLES[slot]["keywords"]:
        if kw in q:
            score += 0.20
    if slot == "left_hemisphere" and direct_math(question):
        score += 0.80
    if slot == "memory_transformer" and q in MEMORY:
        score += 0.80
    if slot == "critic_conscience_transformer" and "favorite" in q:
        score += 0.80
    return min(score, 0.99)

def role_answer(slot: str, question: str) -> str | None:
    q = normalize(question)

    if slot == "left_hemisphere":
        m = direct_math(question)
        if m:
            return m
        if any(x in q for x in ["code", "script", "logic", "test"]):
            return "Left brain: make the logic exact, test it, and do not promote broken code."

    if slot == "memory_transformer":
        if q in MEMORY:
            return MEMORY[q]
        if "created you" in q or "made you" in q or "built you" in q:
            return "Mr. Novotron."
        if "your name" in q:
            return "Nova Creature."

    if slot == "planner_transformer":
        if any(x in q for x in ["next", "plan", "build", "step", "upgrade"]):
            return "Planner: keep the working stack as gold, add the next module in an experiment, run checks, then promote only after it passes."

    if slot == "right_hemisphere":
        if any(x in q for x in ["imagine", "brain", "architecture", "visual", "pattern"]):
            return "Right brain: connect the pieces as a living brain map — organs, routes, memory, critic, and speech working as one creature."

    if slot == "critic_conscience_transformer":
        if "favorite" in q or any(x in q for x in ["unknown", "guess"]):
            return "I do not know."

    if slot == "dream_simulation_transformer":
        if any(x in q for x in ["dream", "practice", "scenario", "variant"]):
            return "Dream brain: save this as a practice scenario, generate variants, then send only approved lessons into training."

    if slot == "speech_output_transformer":
        return None

    return None

def route_one(question: str) -> dict:
    project_root = root()
    outputs = []
    for slot in ROLES:
        ready = slot_ready(project_root, slot)
        ans = role_answer(slot, question) if ready else None
        outputs.append({
            "slot": slot,
            "ready": ready,
            "role": ROLES[slot]["role"],
            "confidence": score_slot(slot, question) if ready else 0.0,
            "answer": ans,
        })

    candidates = [o for o in outputs if o["answer"]]
    candidates.sort(key=lambda o: o["confidence"], reverse=True)

    if candidates:
        selected = candidates[0]
        answer = selected["answer"]
        route = selected["slot"]
    else:
        selected = None
        answer = "I do not know."
        route = "unknown_fallback"

    return {
        "question": question,
        "final_answer": answer,
        "selected_route": route,
        "selected": selected,
        "brain_outputs": outputs,
    }

def run(prompt: str) -> dict:
    questions = split_questions(prompt) or [prompt]
    return {
        "version": "codex_cloud_v052_role_brain_router",
        "created_at": datetime.now().isoformat(),
        "results": [route_one(q) for q in questions],
    }

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = run(args.prompt)
    reports = root() / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "codex_v052_role_router_last_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("SOURCE MODE: Role-Brain Router v052 Cloud")
        for i, item in enumerate(report["results"], 1):
            print(f"{i}. {item['final_answer']}")
        print()
        print("Routes:")
        for i, item in enumerate(report["results"], 1):
            print(f"{i}. {item['selected_route']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
