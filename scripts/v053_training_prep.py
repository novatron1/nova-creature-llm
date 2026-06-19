from __future__ import annotations

import argparse
import json
from pathlib import Path
from datetime import datetime

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

def role_dir(role: str) -> Path:
    d = root() / "training_data" / "role_brains" / role
    d.mkdir(parents=True, exist_ok=True)
    return d

def append_jsonl(path: Path, obj: dict):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def read_jsonl(path: Path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

def init():
    for role in ROLES:
        d = role_dir(role)
        for name in ["pending_lessons.jsonl", "approved_lessons.jsonl"]:
            p = d / name
            if not p.exists():
                p.write_text("", encoding="utf-8")
    print("PASS: training prep folders ready.")

def add(role: str, prompt: str, answer: str):
    if role not in ROLES:
        raise SystemExit(f"Bad role: {role}")
    lesson = {
        "id": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
        "created_at": datetime.now().isoformat(),
        "role": role,
        "prompt": prompt,
        "answer": answer,
        "status": "pending",
    }
    append_jsonl(role_dir(role) / "pending_lessons.jsonl", lesson)
    print("PASS: lesson added pending:", lesson["id"])

def approve_all():
    count = 0
    for role in ROLES:
        d = role_dir(role)
        pending = read_jsonl(d / "pending_lessons.jsonl")
        for item in pending:
            item["status"] = "approved"
            item["approved_at"] = datetime.now().isoformat()
            append_jsonl(d / "approved_lessons.jsonl", item)
            count += 1
        (d / "pending_lessons.jsonl").write_text("", encoding="utf-8")
    print("PASS: approved pending lessons:", count)

def gold():
    init()
    samples = [
        ("left_hemisphere", "What is 12 times 12?", "144."),
        ("right_hemisphere", "Imagine the brain architecture.", "Right brain: connect the pieces as a living brain map."),
        ("memory_transformer", "Who created you?", "Mr. Novotron."),
        ("planner_transformer", "What is the next build step?", "Prepare separate approved training sets for each brain role."),
        ("critic_conscience_transformer", "What is my favorite color?", "I do not know."),
        ("dream_simulation_transformer", "Make a practice scenario.", "Dream brain: generate variants and replay the lesson."),
        ("speech_output_transformer", "Clean this answer.", "Speech brain: give the final answer clearly and simply."),
    ]
    for role, prompt, answer in samples:
        lesson = {"id": "gold_" + role, "created_at": datetime.now().isoformat(), "role": role, "prompt": prompt, "answer": answer, "status": "approved"}
        append_jsonl(role_dir(role) / "approved_lessons.jsonl", lesson)
    export()

def export():
    out_root = root() / "exports" / "v053_training_sets"
    out_root.mkdir(parents=True, exist_ok=True)
    summary = {}
    for role in ROLES:
        items = read_jsonl(role_dir(role) / "approved_lessons.jsonl")
        data = [{"role": role, "prompt": x["prompt"], "answer": x["answer"]} for x in items]
        (out_root / f"{role}_training_set.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        summary[role] = len(data)
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("PASS: exported training sets:", out_root)
    for k, v in summary.items():
        print(k, v)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    addp = sub.add_parser("add")
    addp.add_argument("--role", required=True)
    addp.add_argument("--prompt", required=True)
    addp.add_argument("--answer", required=True)
    sub.add_parser("approve-all")
    sub.add_parser("export")
    sub.add_parser("gold")
    args = ap.parse_args()
    if args.cmd == "init":
        init()
    elif args.cmd == "add":
        add(args.role, args.prompt, args.answer)
    elif args.cmd == "approve-all":
        approve_all()
    elif args.cmd == "export":
        export()
    elif args.cmd == "gold":
        gold()

if __name__ == "__main__":
    main()
