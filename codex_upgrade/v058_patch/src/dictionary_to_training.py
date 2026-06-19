from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any

ROLES = [
    "left_hemisphere",
    "right_hemisphere",
    "memory_transformer",
    "planner_transformer",
    "critic_conscience_transformer",
    "dream_simulation_transformer",
    "speech_output_transformer",
]


def root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def classify_role(question: str, answer: str) -> str:
    q = normalize(question)
    a = normalize(answer)

    if re.search(r"\b\d+\b", q) and any(x in q for x in ["plus", "minus", "times", "x", "+", "-", "*", "math"]):
        return "left_hemisphere"
    if any(x in q for x in ["code", "script", "logic", "test", "calculate", "math"]):
        return "left_hemisphere"
    if any(x in q for x in ["who", "name", "created", "made", "built", "remember", "memory", "what is your"]):
        return "memory_transformer"
    if any(x in q for x in ["next", "plan", "build", "step", "upgrade", "install", "fix"]):
        return "planner_transformer"
    if any(x in q for x in ["favorite", "unknown", "guess", "safe", "true", "wrong"]) or "i do not know" in a:
        return "critic_conscience_transformer"
    if any(x in q for x in ["imagine", "creative", "pattern", "visual", "brain architecture", "map"]):
        return "right_hemisphere"
    if any(x in q for x in ["dream", "practice", "scenario", "variant", "replay"]):
        return "dream_simulation_transformer"
    if any(x in q for x in ["say", "respond", "explain", "word", "clean"]):
        return "speech_output_transformer"

    # Default: dictionary facts teach memory first.
    return "memory_transformer"


def load_dictionary(project_root: Path) -> dict[str, str]:
    candidates = [
        project_root / "data" / "dictionary_memory" / "approved_answer_dictionary.json",
        project_root / "data" / "approved_answer_dictionary.json",
    ]
    for p in candidates:
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    return {}


def load_training_set(project_root: Path, role: str) -> list[dict[str, Any]]:
    p = project_root / "exports" / "v053_training_sets" / f"{role}_training_set.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_training_set(project_root: Path, role: str, data: list[dict[str, Any]]) -> None:
    out_dir = project_root / "exports" / "v053_training_sets"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{role}_training_set.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_dictionary_to_training(project_root: Path | None = None) -> dict[str, Any]:
    project_root = project_root or root()
    dictionary = load_dictionary(project_root)

    if not dictionary:
        raise FileNotFoundError("No approved dictionary found. Expected data/dictionary_memory/approved_answer_dictionary.json")

    role_sets = {role: load_training_set(project_root, role) for role in ROLES}
    existing_keys = {
        role: {normalize(item.get("prompt", "")) for item in role_sets[role]}
        for role in ROLES
    }

    added = {role: 0 for role in ROLES}
    lessons = []

    for question, answer in dictionary.items():
        role = classify_role(question, answer)
        key = normalize(question)
        if key in existing_keys[role]:
            continue

        lesson = {
            "role": role,
            "prompt": question,
            "answer": answer,
            "source": "v058_dictionary_export",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "tags": ["dictionary_memory", "v058"],
        }
        role_sets[role].append(lesson)
        existing_keys[role].add(key)
        added[role] += 1
        lessons.append(lesson)

    for role in ROLES:
        save_training_set(project_root, role, role_sets[role])

    export_dir = project_root / "exports" / "v058_dictionary_training"
    export_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "version": "v058_dictionary_to_transformer_learning",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "dictionary_entries_seen": len(dictionary),
        "lessons_added_total": sum(added.values()),
        "lessons_added_by_role": added,
        "training_set_counts": {role: len(role_sets[role]) for role in ROLES},
        "flow": "approved dictionary -> role training sets -> v054/v055 transformer learning",
    }
    (export_dir / "v058_dictionary_export_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (export_dir / "v058_dictionary_lessons.json").write_text(json.dumps(lessons, indent=2, ensure_ascii=False), encoding="utf-8")

    return summary


if __name__ == "__main__":
    print(json.dumps(export_dictionary_to_training(), indent=2))
