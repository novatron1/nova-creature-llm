from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Any


DEFAULT_DICT = {
    "who created you": "Mr. Novotron.",
    "who made you": "Mr. Novotron.",
    "who built you": "Mr. Novotron.",
    "who are you": "Nova Creature.",
    "what is your name": "Nova Creature.",
    "can you browse": "No.",
    "what is 12 times 12": "144.",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_question(text: str) -> str:
    s = str(text or "").lower().strip()
    s = re.sub(r"[^a-z0-9+\-*x ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class DictionaryMemory:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.memory_dir = self.project_root / "data" / "dictionary_memory"
        self.approved_path = self.memory_dir / "approved_answer_dictionary.json"
        self.pending_path = self.memory_dir / "pending_dictionary_lessons.jsonl"
        self.hits_path = self.memory_dir / "dictionary_hits.jsonl"

    def ensure(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        if not self.approved_path.exists():
            self.approved_path.write_text(json.dumps(DEFAULT_DICT, indent=2, ensure_ascii=False), encoding="utf-8")
        if not self.pending_path.exists():
            self.pending_path.write_text("", encoding="utf-8")
        if not self.hits_path.exists():
            self.hits_path.write_text("", encoding="utf-8")

    def load_approved(self) -> dict[str, str]:
        self.ensure()
        try:
            data = json.loads(self.approved_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {normalize_question(k): str(v) for k, v in data.items()}
        except Exception:
            pass
        return dict(DEFAULT_DICT)

    def save_approved(self, data: dict[str, str]) -> None:
        self.ensure()
        cleaned = {normalize_question(k): str(v) for k, v in data.items() if normalize_question(k)}
        self.approved_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False), encoding="utf-8")

    def lookup(self, question: str) -> dict[str, Any]:
        self.ensure()
        key = normalize_question(question)
        data = self.load_approved()
        if key in data:
            hit = {
                "time": now_iso(),
                "question": question,
                "normalized": key,
                "answer": data[key],
                "source": "approved_dictionary_exact",
            }
            self.append_jsonl(self.hits_path, hit)
            return {"found": True, **hit}
        return {"found": False, "question": question, "normalized": key}

    def add_pending(self, question: str, answer: str, tags: list[str] | None = None) -> dict[str, Any]:
        self.ensure()
        item = {
            "id": datetime.now().strftime("%Y%m%d_%H%M%S_%f"),
            "time": now_iso(),
            "question": question,
            "normalized": normalize_question(question),
            "answer": answer,
            "tags": tags or [],
            "status": "pending",
        }
        self.append_jsonl(self.pending_path, item)
        return item

    def approve_pending(self) -> int:
        self.ensure()
        approved = self.load_approved()
        items = self.read_jsonl(self.pending_path)
        count = 0
        for item in items:
            q = normalize_question(item.get("question", ""))
            a = str(item.get("answer", "")).strip()
            if q and a:
                approved[q] = a
                count += 1
        self.save_approved(approved)
        self.pending_path.write_text("", encoding="utf-8")
        return count

    def add_approved(self, question: str, answer: str) -> dict[str, Any]:
        self.ensure()
        approved = self.load_approved()
        key = normalize_question(question)
        approved[key] = str(answer)
        self.save_approved(approved)
        return {"question": question, "normalized": key, "answer": answer, "status": "approved"}

    @staticmethod
    def append_jsonl(path: Path, item: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    @staticmethod
    def read_jsonl(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        out = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
        return out
