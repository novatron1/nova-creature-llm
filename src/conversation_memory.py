from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
from typing import Any


DEFAULT_STATE = {
    "version": "v056_conversation_memory",
    "thread_id": "default",
    "created_at": None,
    "updated_at": None,
    "current_topic": "",
    "active_goal": "",
    "last_user_message": "",
    "last_assistant_answer": "",
    "last_route": "",
    "turn_count": 0,
    "recent_turns": [],
    "known_facts": {},
    "unresolved_items": [],
}


FOLLOWUP_WORDS = {
    "that", "it", "this", "do that", "make that", "add that", "go", "ok", "okay",
    "what next", "next", "continue", "keep going", "run it", "build it"
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def project_root_from_file() -> Path:
    return Path(__file__).resolve().parents[1]


@dataclass
class ConversationMemory:
    project_root: Path
    thread_id: str = "default"

    @property
    def memory_dir(self) -> Path:
        return self.project_root / "data" / "conversation_memory"

    @property
    def state_path(self) -> Path:
        return self.memory_dir / f"{self.thread_id}_state.json"

    @property
    def log_path(self) -> Path:
        return self.memory_dir / f"{self.thread_id}_turns.jsonl"

    def ensure(self) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        if not self.state_path.exists():
            state = dict(DEFAULT_STATE)
            state["thread_id"] = self.thread_id
            state["created_at"] = now_iso()
            state["updated_at"] = now_iso()
            self.save_state(state)

    def load_state(self) -> dict[str, Any]:
        self.ensure()
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            state = dict(DEFAULT_STATE)
            state["thread_id"] = self.thread_id
            state["created_at"] = now_iso()
            state["updated_at"] = now_iso()
            self.save_state(state)
            return state

    def save_state(self, state: dict[str, Any]) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = now_iso()
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def append_log(self, item: dict[str, Any]) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def is_followup(self, message: str) -> bool:
        msg = normalize(message)
        return msg in FOLLOWUP_WORDS or msg.startswith(("do ", "add ", "make ", "run ", "continue"))

    def infer_topic_goal(self, message: str, state: dict[str, Any]) -> tuple[str, str]:
        msg = normalize(message)
        topic = state.get("current_topic", "")
        goal = state.get("active_goal", "")

        if "conversation memory" in msg or "hold a conversation" in msg:
            topic = "conversation memory loop"
            goal = "give Nova conversation memory so it remembers the thread and understands follow-ups"
        elif "fine tune" in msg or "finetune" in msg or "training" in msg:
            topic = "role-brain training"
            goal = "train separate specialized brain checkpoints"
        elif "cloud" in msg and "checkpoint" in msg:
            topic = "cloud checkpoint pipeline"
            goal = "make cloud Nova use the real v032 checkpoint"
        elif "router" in msg:
            topic = "multi-brain router"
            goal = "route questions through the correct brain organs"
        elif "what next" in msg or msg == "next":
            topic = topic or "current Nova Creature build"
            goal = goal or "choose the next safest upgrade"

        return topic, goal

    def extract_facts(self, message: str) -> dict[str, str]:
        msg = str(message or "").strip()
        facts: dict[str, str] = {}

        # Simple explicit memory patterns.
        m = re.search(r"(?i)\bremember that (.+)", msg)
        if m:
            facts[f"remembered_{now_iso()}"] = m.group(1).strip()

        m = re.search(r"(?i)\bmy ([a-zA-Z0-9_ -]{2,40}) is (.+)", msg)
        if m:
            key = m.group(1).strip().lower().replace(" ", "_")
            facts[key] = m.group(2).strip()

        return facts

    def build_context(self, message: str) -> dict[str, Any]:
        state = self.load_state()
        followup = self.is_followup(message)
        topic, goal = self.infer_topic_goal(message, state)

        resolved_message = message
        if followup and state.get("active_goal"):
            resolved_message = f"{message} [context: current_topic={state.get('current_topic')}; active_goal={state.get('active_goal')}; last_answer={state.get('last_assistant_answer')}]"

        return {
            "thread_id": self.thread_id,
            "message": message,
            "resolved_message": resolved_message,
            "is_followup": followup,
            "current_topic": topic,
            "active_goal": goal,
            "last_user_message": state.get("last_user_message", ""),
            "last_assistant_answer": state.get("last_assistant_answer", ""),
            "last_route": state.get("last_route", ""),
            "recent_turns": state.get("recent_turns", [])[-6:],
            "known_facts": state.get("known_facts", {}),
            "unresolved_items": state.get("unresolved_items", []),
        }

    def update_after_turn(self, message: str, answer: str, route: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.load_state()
        topic, goal = self.infer_topic_goal(message, state)

        facts = self.extract_facts(message)
        known = state.get("known_facts", {})
        known.update(facts)

        turn = {
            "time": now_iso(),
            "user": message,
            "assistant": answer,
            "route": route,
            "topic": topic,
            "goal": goal,
        }

        if extra:
            turn["extra"] = extra

        recent = state.get("recent_turns", [])
        recent.append(turn)
        recent = recent[-12:]

        unresolved = state.get("unresolved_items", [])
        if "I do not know" in answer and message not in unresolved:
            unresolved.append(message)
            unresolved = unresolved[-20:]

        state.update({
            "current_topic": topic,
            "active_goal": goal,
            "last_user_message": message,
            "last_assistant_answer": answer,
            "last_route": route,
            "turn_count": int(state.get("turn_count", 0)) + 1,
            "recent_turns": recent,
            "known_facts": known,
            "unresolved_items": unresolved,
        })
        self.save_state(state)
        self.append_log(turn)
        return state

    def reset(self) -> None:
        state = dict(DEFAULT_STATE)
        state["thread_id"] = self.thread_id
        state["created_at"] = now_iso()
        state["updated_at"] = now_iso()
        self.save_state(state)
        if self.log_path.exists():
            self.log_path.unlink()
