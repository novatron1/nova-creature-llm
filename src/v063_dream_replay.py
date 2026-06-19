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


def root() -> Path:
    return ROOT


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify_role_for_qa(question: str) -> str:
    q = normalize(question)
    if re.search(r"\b\d+\b", q) and any(x in q for x in ["plus","minus","times","x","+","-","math"]):
        return "left_hemisphere"
    if any(x in q for x in ["who","name","created","made","built","remember","memory"]):
        return "memory_transformer"
    if any(x in q for x in ["next","plan","build","step","upgrade","install"]):
        return "planner_transformer"
    if any(x in q for x in ["favorite","unknown","guess","safe"]):
        return "critic_conscience_transformer"
    if any(x in q for x in ["imagine","creative","pattern","visual","architecture"]):
        return "right_hemisphere"
    if any(x in q for x in ["dream","practice","scenario","variant"]):
        return "dream_simulation_transformer"
    if any(x in q for x in ["say","respond","explain","word"]):
        return "speech_output_transformer"
    return "memory_transformer"


def collect_conversation_turns() -> list[dict[str, Any]]:
    """Collect all conversation turns from conversation memory logs."""
    mem_dir = root() / "data" / "conversation_memory"
    turns = []
    if not mem_dir.exists():
        return turns
    for f in mem_dir.glob("*_turns.jsonl"):
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line:
                try:
                    item = json.loads(line)
                    turns.append(item)
                except json.JSONDecodeError:
                    pass
    return turns


def generate_dream_lessons() -> list[dict[str, Any]]:
    """Generate dream replay lessons from conversation turns."""
    turns = collect_conversation_turns()
    lessons = []
    seen_pairs = set()

    for turn in turns:
        msg = str(turn.get("user", turn.get("user_message", turn.get("message", "")))).strip()
        ans = str(turn.get("assistant", turn.get("assistant_answer", turn.get("answer", turn.get("final_answer", ""))))).strip()
        route = str(turn.get("route", turn.get("last_route", ""))).strip()

        if not msg or not ans or ans == "I do not know.":
            continue

        pair_key = normalize(msg + ans)
        if pair_key in seen_pairs:
            continue
        seen_pairs.add(pair_key)

        role = route if route in ROLES else classify_role_for_qa(msg)

        lessons.append({
            "role": role,
            "prompt": msg,
            "answer": ans,
            "source": "v063_dream_replay",
            "dream_type": "conversation_replay",
            "created_at": datetime.now().isoformat(),
        })

    return lessons


def export_dream_lessons() -> dict[str, Any]:
    """Export dream replay lessons into v053 training sets."""
    lessons = generate_dream_lessons()
    if not lessons:
        return {"lessons_generated": 0, "roles_updated": [], "message": "No conversation turns to replay"}

    role_lessons: dict[str, list[dict]] = {}
    for lesson in lessons:
        role = lesson["role"]
        if role not in role_lessons:
            role_lessons[role] = []
        role_lessons[role].append(lesson)

    added_total = 0
    roles_updated = []
    for role in ROLES:
        ts_path = root() / "exports" / "v053_training_sets" / f"{role}_training_set.json"
        existing = json.loads(ts_path.read_text(encoding="utf-8")) if ts_path.exists() and ts_path.stat().st_size > 0 else []
        existing_norm = {normalize(item.get("prompt", "") + item.get("answer", "")) for item in existing}

        new_count = 0
        for lesson in role_lessons.get(role, []):
            key = normalize(lesson["prompt"] + lesson["answer"])
            if key not in existing_norm:
                existing.append(lesson)
                existing_norm.add(key)
                new_count += 1

        if new_count > 0:
            ts_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
            added_total += new_count
            roles_updated.append(role)

    return {
        "version": "v063_dream_replay",
        "created_at": datetime.now().isoformat(),
        "conversation_turns_analyzed": len(collect_conversation_turns()),
        "dream_lessons_generated": len(lessons),
        "dream_lessons_added": added_total,
        "roles_updated": roles_updated,
        "duplicates_skipped": len(lessons) - added_total,
    }


def main() -> int:
    print("Nova Creature v063 — Dream Replay Learning\n")
    result = export_dream_lessons()
    print(f"Turns analyzed: {result['conversation_turns_analyzed']}")
    print(f"Dream lessons generated: {result['dream_lessons_generated']}")
    print(f"New lessons added: {result['dream_lessons_added']}")
    print(f"Roles updated: {result['roles_updated']}")
    reports_dir = root() / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v063_dream_replay_report.json").write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
