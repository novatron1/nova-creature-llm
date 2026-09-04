"""Privacy-bounded operational world model for Nova conversations.

The world model is a cognitive blackboard, not an LLM and not chain-of-thought.
It keeps concise operational state that Nova's clients can inspect safely:
active goal, topic, referenced relationship roles, unresolved questions,
device capability availability, and the last provider route.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

from nova_protocol import NovaRequest, NovaResponse


WORLD_MODEL_SCHEMA_VERSION = "1.2"
WORLD_MODEL_INTERFACE_VERSION = "1.0"
WORLD_MODEL_PERSISTENCE_MODES = frozenset({"session", "checkpoint"})
_SUPPORTED_CHECKPOINT_VERSIONS = frozenset(
    {"1.0", "1.1", WORLD_MODEL_SCHEMA_VERSION}
)
_SAFE_TOPICS = frozenset(
    {
        "relationship",
        "nova_identity",
        "app_building",
        "coding",
        "model_training",
        "model_routing",
        "science",
        "memory",
        "device_awareness",
        "general_conversation",
    }
)
_SAFE_GOALS = frozenset(
    {
        "Repair or improve the requested system",
        "Build or create the requested result",
        "Verify the requested behavior",
        "Improve Nova through guarded learning",
        "Give concrete, respectful relationship guidance",
        "Discuss Nova's identity and capabilities honestly",
        "Answer the user's current question",
        "Continue the current conversation coherently",
    }
)
_SAFE_PEOPLE = frozenset(
    {"girlfriend", "boyfriend", "wife", "husband", "friend", "family", "nova", "user"}
)
_SAFE_CONTINUITY_ENTITIES = frozenset(
    set(_SAFE_PEOPLE)
    | {"earth", "qwen", "dolphin", "ollama", "app", "model"}
)
_SAFE_EMOTIONAL_CONTEXT = frozenset(
    {"anxious", "hurt", "sad", "frustrated", "strained", "positive", "affectionate"}
)
_PERSISTED_ROUTE_FIELDS = frozenset(
    {
        "requested_alias",
        "selected_provider",
        "selected_model",
        "remains_local",
        "fallback_path",
        "answer_source",
        "provider",
        "model",
        "finish_reason",
        "latency_ms",
        "planning_strategy",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _compact(text: str, limit: int = 240) -> str:
    return " ".join(str(text or "").split()).strip()[:limit]


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _safe_route_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, Any] = {}
    for key in _PERSISTED_ROUTE_FIELDS:
        item = value.get(key)
        if item is None:
            continue
        if key == "remains_local":
            output[key] = bool(item)
        elif key == "latency_ms":
            try:
                output[key] = max(0.0, min(float(item), 3_600_000.0))
            except (TypeError, ValueError):
                continue
        elif key == "fallback_path":
            output[key] = [_compact(entry, 120) for entry in list(item or [])[:8]]
        else:
            output[key] = _compact(item, 160)
    return output


def _safe_choice(value: Any, allowed: frozenset[str], default: str) -> str:
    compact = _compact(value, 240)
    return compact if compact in allowed else default


def _safe_count(value: Any, maximum: int = 8) -> int:
    try:
        return max(0, min(int(value or 0), maximum))
    except (TypeError, ValueError):
        return 0


def _safe_continuity(value: Any) -> dict[str, Any]:
    """Keep only bounded operational continuity metadata.

    Raw conversation, prompt, response, names, and free-form notes are
    intentionally ignored. Detailed context remains in the client-owned rolling
    summary rather than Nova's restart checkpoint.
    """

    source = value if isinstance(value, dict) else {}
    active_topic = _safe_choice(
        str(source.get("active_topic") or "").strip().lower(),
        _SAFE_TOPICS,
        "general_conversation",
    )
    entities = [
        compact
        for compact in (
            _compact(item, 40).lower()
            for item in list(source.get("active_entities") or [])[:16]
        )
        if compact in _SAFE_CONTINUITY_ENTITIES
    ]
    emotions = [
        compact
        for compact in (
            _compact(item, 40).lower()
            for item in list(source.get("emotional_context") or [])[:8]
        )
        if compact in _SAFE_EMOTIONAL_CONTEXT
    ]
    return {
        "active_topic": active_topic,
        "unresolved_count": _safe_count(source.get("unresolved_count")),
        "commitment_count": _safe_count(source.get("commitment_count")),
        "correction_count": _safe_count(source.get("correction_count")),
        "active_entities": list(dict.fromkeys(entities))[:8],
        "emotional_context": list(dict.fromkeys(emotions))[:4],
    }


def _topic(text: str) -> str:
    value = _compact(text, 800).lower()
    rules = (
        ("relationship", ("girlfriend", "boyfriend", "wife", "husband", "love her", "love him", "relationship")),
        ("nova_identity", ("are you human", "self aware", "conscious", "feel powerful", "nova identity")),
        ("app_building", ("build app", "build a", "website", "app builder", "game builder")),
        ("coding", ("code", "python", "javascript", "debug", "bug", "api", "server")),
        ("model_training", ("train", "adapter", "lora", "checkpoint", "evaluation")),
        ("model_routing", ("qwen", "dolphin", "deepseek", "provider", "model route")),
        ("science", ("science", "earth", "physics", "biology", "chemistry", "space")),
        ("memory", ("remember", "memory", "recall", "forget")),
        ("device_awareness", ("camera", "sensor", "microphone", "battery", "location", "distance")),
    )
    for topic, markers in rules:
        if any(marker in value for marker in markers):
            return topic
    return "general_conversation"


def _goal(text: str, topic: str) -> str:
    value = _compact(text, 800).lower()
    if any(marker in value for marker in ("fix ", "repair", "improve", "upgrade", "make it better")):
        return "Repair or improve the requested system"
    if any(marker in value for marker in ("build ", "create ", "make an app", "make a website", "generate ")):
        return "Build or create the requested result"
    if any(marker in value for marker in ("test ", "check ", "verify", "live test")):
        return "Verify the requested behavior"
    if any(marker in value for marker in ("train ", "teach ", "learn from")):
        return "Improve Nova through guarded learning"
    if topic == "relationship":
        return "Give concrete, respectful relationship guidance"
    if topic == "nova_identity":
        return "Discuss Nova's identity and capabilities honestly"
    if "?" in str(text or "") or re.match(r"^(what|why|how|when|where|who|can|do|is|are|should)\b", value):
        return "Answer the user's current question"
    return "Continue the current conversation coherently"


def _people(text: str) -> list[str]:
    value = _compact(text, 800).lower()
    roles: list[str] = []
    role_markers = (
        ("girlfriend", ("girlfriend", "girl friend")),
        ("boyfriend", ("boyfriend", "boy friend")),
        ("wife", ("wife",)),
        ("husband", ("husband",)),
        ("friend", ("friend", "buddy")),
        ("family", ("mother", "mom", "father", "dad", "sister", "brother", "family")),
        ("nova", ("nova", "you")),
        ("user", (" i ", " me ", " my ")),
    )
    padded = f" {value} "
    for role, markers in role_markers:
        if any(marker in padded for marker in markers):
            roles.append(role)
    return roles[:8]


def _sensor_summary(request: NovaRequest) -> dict[str, Any]:
    desktop = request.metadata.get("desktop_context")
    snapshot = desktop.get("sensor_snapshot") if isinstance(desktop, dict) else None
    if not isinstance(snapshot, dict):
        return {"available": False, "channels": []}
    channels = [
        key
        for key in ("screen", "network", "battery", "location", "motion", "orientation", "touch", "distance")
        if snapshot.get(key) is not None
    ]
    permissions = snapshot.get("permissions") if isinstance(snapshot.get("permissions"), dict) else {}
    return {
        "available": True,
        "enabled": bool(snapshot.get("enabled", False)),
        "source": _compact(snapshot.get("source") or "client_sensor_snapshot", 80),
        "channels": channels,
        "permissions": {
            str(key)[:40]: bool(value)
            for key, value in permissions.items()
            if isinstance(value, bool)
        },
    }


@dataclass
class CognitiveBlackboard:
    """One provider-independent operational state board."""

    client_id: str
    user_id: str
    conversation_id: str
    session_id: str
    schema_version: str = WORLD_MODEL_SCHEMA_VERSION
    status: str = "idle"
    current_topic: str = "general_conversation"
    active_goal: str = "Continue the current conversation coherently"
    goal_status: str = "ready"
    active_people: list[str] = field(default_factory=list)
    unresolved_questions: list[dict[str, str]] = field(default_factory=list)
    continuity: dict[str, Any] = field(
        default_factory=lambda: _safe_continuity({})
    )
    device_context: dict[str, Any] = field(default_factory=lambda: {"available": False, "channels": []})
    route_state: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    last_request_id: str = ""
    last_error_category: str = ""
    privacy_mode: str = "local_preferred"
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "current_topic": self.current_topic,
            "active_goal": self.active_goal,
            "goal_status": self.goal_status,
            "active_people": list(self.active_people),
            "unresolved_count": len(self.unresolved_questions),
            "continuity": dict(self.continuity),
            "turn_count": self.turn_count,
            "route_state": dict(self.route_state),
            "device_channels": list(self.device_context.get("channels") or []),
            "updated_at": self.updated_at,
        }


class NovaWorldModel:
    """Thread-safe bounded registry of per-client cognitive blackboards."""

    def __init__(
        self,
        maximum_conversations: int = 128,
        *,
        persistence: str = "session",
        checkpoint_path: str | Path | None = None,
        max_age_days: int = 30,
    ):
        self.maximum_conversations = max(8, min(int(maximum_conversations), 1024))
        self.persistence = str(persistence or "session").strip().lower()
        if self.persistence not in WORLD_MODEL_PERSISTENCE_MODES:
            raise ValueError(f"Unsupported world-model persistence mode {persistence!r}.")
        self.checkpoint_path = Path(checkpoint_path).resolve() if checkpoint_path else None
        if self.persistence == "checkpoint" and self.checkpoint_path is None:
            raise ValueError("Checkpoint persistence requires a world-model checkpoint path.")
        self.max_age_days = max(1, min(int(max_age_days), 3650))
        self._boards: OrderedDict[tuple[str, str], CognitiveBlackboard] = OrderedDict()
        self._lock = RLock()
        self._checkpoint_lock = RLock()
        self._loaded_count = 0
        self._expired_count = 0
        self._invalid_record_count = 0
        self._checkpoint_error = ""
        self._checkpoint_quarantined = False
        self._last_saved_at = ""
        if self.persistence == "checkpoint":
            self._load_checkpoint()

    @staticmethod
    def _key(client_id: str, conversation_id: str) -> tuple[str, str]:
        return (_compact(client_id or "anonymous", 160), _compact(conversation_id or "default", 160))

    @staticmethod
    def _persistent_record(board: CognitiveBlackboard) -> dict[str, Any]:
        unresolved_count = min(len(board.unresolved_questions), 8)
        return {
            "schema_version": WORLD_MODEL_SCHEMA_VERSION,
            "client_id": _compact(board.client_id, 160),
            "conversation_id": _compact(board.conversation_id, 160),
            "status": "idle" if board.status == "working" else _compact(board.status, 40),
            "current_topic": _safe_choice(
                board.current_topic,
                _SAFE_TOPICS,
                "general_conversation",
            ),
            "active_goal": _safe_choice(
                board.active_goal,
                _SAFE_GOALS,
                "Continue the current conversation coherently",
            ),
            "goal_status": "ready" if board.goal_status == "in_progress" else _compact(board.goal_status, 40),
            "active_people": [
                item
                for item in (_compact(value, 80) for value in board.active_people[:8])
                if item in _SAFE_PEOPLE
            ],
            "unresolved_count": unresolved_count,
            "continuity": _safe_continuity(board.continuity),
            "device_context": {
                "available": bool(board.device_context.get("available", False)),
                "enabled": bool(board.device_context.get("enabled", False)),
                "channels": [
                    _compact(item, 40)
                    for item in list(board.device_context.get("channels") or [])[:16]
                ],
            },
            "route_state": _safe_route_state(board.route_state),
            "turn_count": max(0, min(int(board.turn_count), 10_000_000)),
            "last_error_category": _compact(board.last_error_category, 120),
            "privacy_mode": _compact(board.privacy_mode, 80),
            "created_at": board.created_at,
            "updated_at": board.updated_at,
        }

    def export_checkpoint_payload(self) -> dict[str, Any]:
        """Return the privacy-filtered portable checkpoint representation."""
        with self._lock:
            boards = [self._persistent_record(board) for board in self._boards.values()]
        return {
            "schema_version": WORLD_MODEL_SCHEMA_VERSION,
            "interface_version": WORLD_MODEL_INTERFACE_VERSION,
            "saved_at": _now(),
            "privacy": {
                "prompt_content_stored": False,
                "response_content_stored": False,
                "private_chain_of_thought_stored": False,
                "sensor_values_stored": False,
                "user_id_stored": False,
                "session_id_stored": False,
            },
            "boards": boards,
        }

    @staticmethod
    def _restored_board(record: dict[str, Any]) -> CognitiveBlackboard | None:
        client_id = _compact(record.get("client_id"), 160)
        conversation_id = _compact(record.get("conversation_id"), 160)
        if not client_id or not conversation_id:
            return None
        unresolved_count = max(0, min(int(record.get("unresolved_count") or 0), 8))
        updated_at = _parse_time(record.get("updated_at"))
        created_at = _parse_time(record.get("created_at")) or updated_at or datetime.now(timezone.utc)
        channels = [
            _compact(item, 40)
            for item in list((record.get("device_context") or {}).get("channels") or [])[:16]
        ]
        return CognitiveBlackboard(
            client_id=client_id,
            user_id="restored-without-user-content",
            conversation_id=conversation_id,
            session_id="",
            status=_compact(record.get("status") or "idle", 40),
            current_topic=_safe_choice(
                record.get("current_topic"),
                _SAFE_TOPICS,
                "general_conversation",
            ),
            active_goal=_safe_choice(
                record.get("active_goal"),
                _SAFE_GOALS,
                "Continue the current conversation coherently",
            ),
            goal_status=_compact(record.get("goal_status") or "ready", 40),
            active_people=[
                item
                for item in (
                    _compact(value, 80)
                    for value in list(record.get("active_people") or [])[:8]
                )
                if item in _SAFE_PEOPLE
            ],
            unresolved_questions=[
                {
                    "text": "Follow-up needed from a previous session",
                    "added_at": str(record.get("updated_at") or _now()),
                    "persisted_without_content": "true",
                }
                for _ in range(unresolved_count)
            ],
            continuity=_safe_continuity(record.get("continuity")),
            device_context={
                "available": bool((record.get("device_context") or {}).get("available", False)),
                "enabled": bool((record.get("device_context") or {}).get("enabled", False)),
                "channels": channels,
            },
            route_state=_safe_route_state(record.get("route_state")),
            turn_count=max(0, min(int(record.get("turn_count") or 0), 10_000_000)),
            last_request_id="",
            last_error_category=_compact(record.get("last_error_category"), 120),
            privacy_mode=_compact(record.get("privacy_mode") or "local_preferred", 80),
            created_at=created_at.isoformat(),
            updated_at=(updated_at or created_at).isoformat(),
        )

    def _quarantine_bad_checkpoint(self) -> None:
        path = self.checkpoint_path
        if path is None or not path.exists():
            return
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = path.with_name(path.name + f".corrupt-{suffix}")
        try:
            os.replace(path, target)
            self._checkpoint_quarantined = True
        except OSError:
            self._checkpoint_quarantined = False

    def _load_checkpoint(self) -> None:
        path = self.checkpoint_path
        if path is None or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("checkpoint root must be an object")
            if str(payload.get("schema_version") or "") not in _SUPPORTED_CHECKPOINT_VERSIONS:
                raise ValueError("unsupported checkpoint schema")
            records = payload.get("boards")
            if not isinstance(records, list):
                raise ValueError("checkpoint boards must be an array")
            cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
            loaded: list[CognitiveBlackboard] = []
            expired = 0
            invalid = 0
            for raw in records[-self.maximum_conversations :]:
                if not isinstance(raw, dict):
                    invalid += 1
                    continue
                updated = _parse_time(raw.get("updated_at"))
                if updated is not None and updated < cutoff:
                    expired += 1
                    continue
                try:
                    board = self._restored_board(raw)
                except (AttributeError, TypeError, ValueError):
                    invalid += 1
                    continue
                if board is not None:
                    loaded.append(board)
                else:
                    invalid += 1
            with self._lock:
                for board in loaded:
                    self._boards[self._key(board.client_id, board.conversation_id)] = board
                self._loaded_count = len(loaded)
                self._expired_count = expired
                self._invalid_record_count = invalid
                self._checkpoint_error = ""
        except Exception as exc:
            self._checkpoint_error = f"invalid_checkpoint:{exc.__class__.__name__}"
            self._quarantine_bad_checkpoint()

    def checkpoint_now(self) -> dict[str, Any]:
        """Atomically persist the current privacy-filtered blackboards."""
        if self.persistence != "checkpoint" or self.checkpoint_path is None:
            return {"ok": True, "saved": False, "reason": "session_only"}
        with self._checkpoint_lock:
            payload = self.export_checkpoint_payload()
            path = self.checkpoint_path
            temporary = path.with_suffix(path.suffix + ".tmp")
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(
                    json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, path)
                with self._lock:
                    self._last_saved_at = str(payload["saved_at"])
                    self._checkpoint_error = ""
                return {"ok": True, "saved": True, "boards": len(payload["boards"])}
            except Exception as exc:
                with self._lock:
                    self._checkpoint_error = f"checkpoint_write_failed:{exc.__class__.__name__}"
                    error = self._checkpoint_error
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass
                return {"ok": False, "saved": False, "error": error}

    def import_checkpoint_payload(
        self,
        payload: dict[str, Any],
        *,
        merge: bool = True,
    ) -> dict[str, Any]:
        """Explicitly restore privacy-filtered boards into a checkpoint-backed model."""
        if self.persistence != "checkpoint" or self.checkpoint_path is None:
            raise ValueError("World-model import requires checkpoint persistence.")
        if not isinstance(payload, dict):
            raise ValueError("World-model checkpoint root must be an object.")
        if str(payload.get("schema_version") or "") not in _SUPPORTED_CHECKPOINT_VERSIONS:
            raise ValueError("Unsupported world-model checkpoint schema.")
        records = payload.get("boards")
        if not isinstance(records, list):
            raise ValueError("World-model checkpoint boards must be an array.")

        restored: list[CognitiveBlackboard] = []
        rejected = 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.max_age_days)
        for raw in records[-self.maximum_conversations :]:
            if not isinstance(raw, dict):
                rejected += 1
                continue
            updated = _parse_time(raw.get("updated_at"))
            if updated is not None and updated < cutoff:
                rejected += 1
                continue
            try:
                board = self._restored_board(raw)
            except (AttributeError, TypeError, ValueError):
                board = None
            if board is None:
                rejected += 1
                continue
            restored.append(board)

        with self._lock:
            if not merge:
                self._boards.clear()
            for board in restored:
                key = self._key(board.client_id, board.conversation_id)
                self._boards[key] = board
                self._boards.move_to_end(key)
            while len(self._boards) > self.maximum_conversations:
                self._boards.popitem(last=False)
        saved = self.checkpoint_now()
        if not saved.get("ok"):
            raise OSError("World-model checkpoint could not be written.")
        return {
            "ok": True,
            "imported": len(restored),
            "rejected": rejected,
            "merge": bool(merge),
        }

    def begin_turn(self, request: NovaRequest, routing: dict[str, Any]) -> dict[str, Any]:
        key = self._key(request.client_id, request.conversation_id)
        text = request.last_user_text()
        with self._lock:
            board = self._boards.get(key)
            if board is None:
                board = CognitiveBlackboard(
                    client_id=key[0],
                    user_id=_compact(request.user_id or "anonymous", 160),
                    conversation_id=key[1],
                    session_id=_compact(request.session_id or "", 160),
                )
                self._boards[key] = board
            board.user_id = _compact(request.user_id or "anonymous", 160)
            board.session_id = _compact(request.session_id or "", 160)
            self._boards.move_to_end(key)
            while len(self._boards) > self.maximum_conversations:
                self._boards.popitem(last=False)

            board.status = "working"
            board.current_topic = _topic(text)
            board.active_goal = _goal(text, board.current_topic)
            board.goal_status = "in_progress"
            detected_people = _people(text)
            board.active_people = list(dict.fromkeys(board.active_people + detected_people))[-8:]
            board.device_context = _sensor_summary(request)
            board.route_state = {
                "requested_alias": routing.get("requested_alias"),
                "selected_provider": routing.get("selected_provider"),
                "selected_model": routing.get("selected_model"),
                "remains_local": bool(routing.get("remains_local", False)),
                "fallback_path": list(routing.get("fallback_path") or []),
            }
            board.turn_count += 1
            board.last_request_id = _compact(request.request_id, 160)
            board.last_error_category = ""
            board.privacy_mode = _compact(request.privacy_mode or "local_preferred", 80)
            board.updated_at = _now()
            return board.summary()

    def complete_turn(self, request: NovaRequest, response: NovaResponse) -> dict[str, Any]:
        key = self._key(request.client_id, request.conversation_id)
        with self._lock:
            board = self._boards.get(key)
            if board is None:
                board = CognitiveBlackboard(
                    client_id=key[0],
                    user_id=_compact(request.user_id or "anonymous", 160),
                    conversation_id=key[1],
                    session_id=_compact(request.session_id or "", 160),
                )
                self._boards[key] = board
            trace = response.metadata.get("trace") if isinstance(response.metadata.get("trace"), dict) else {}
            routing = response.metadata.get("routing") if isinstance(response.metadata.get("routing"), dict) else {}
            answer = _compact(response.content, 800).lower()
            failed = bool(response.errors) or not answer or any(
                marker in answer
                for marker in (
                    "did not return a usable answer",
                    "did not produce a reliable answer",
                    "provider unavailable",
                    "i don't know yet",
                )
            )
            board.status = "needs_attention" if failed else "idle"
            board.goal_status = "needs_followup" if failed else "completed"
            board.route_state.update(
                {
                    "selected_provider": routing.get("selected_provider") or response.provider,
                    "selected_model": routing.get("selected_model") or response.model,
                    "remains_local": bool(routing.get("remains_local", board.route_state.get("remains_local", False))),
                    "fallback_path": list(routing.get("fallback_path") or board.route_state.get("fallback_path") or []),
                    "answer_source": (
                        trace.get("final_answer_source")
                        or trace.get("source")
                        or trace.get("route")
                        or response.provider
                    ),
                    "provider": response.provider,
                    "model": response.model,
                    "finish_reason": response.finish_reason,
                    "latency_ms": response.metadata.get("latency_ms"),
                }
            )
            dream = response.metadata.get("dream_lab")
            if isinstance(dream, dict) and dream.get("selected_strategy"):
                board.route_state["planning_strategy"] = _compact(
                    dream.get("selected_strategy"),
                    120,
                )
            if failed:
                question = _compact(request.last_user_text(), 240)
                if question and all(item.get("text") != question for item in board.unresolved_questions):
                    board.unresolved_questions.append({"text": question, "added_at": _now()})
                    board.unresolved_questions = board.unresolved_questions[-8:]
            board.updated_at = _now()
            result = board.summary()
        self.checkpoint_now()
        return result

    def fail_turn(self, request: NovaRequest, error_category: str) -> dict[str, Any]:
        key = self._key(request.client_id, request.conversation_id)
        with self._lock:
            board = self._boards.get(key)
            if board is None:
                board = CognitiveBlackboard(
                    client_id=key[0],
                    user_id=_compact(request.user_id or "anonymous", 160),
                    conversation_id=key[1],
                    session_id=_compact(request.session_id or "", 160),
                )
                self._boards[key] = board
            board.status = "error"
            board.goal_status = "needs_followup"
            board.last_error_category = _compact(error_category or "internal_error", 120)
            question = _compact(request.last_user_text(), 240)
            if question and all(item.get("text") != question for item in board.unresolved_questions):
                board.unresolved_questions.append({"text": question, "added_at": _now()})
                board.unresolved_questions = board.unresolved_questions[-8:]
            board.updated_at = _now()
            result = board.summary()
        self.checkpoint_now()
        return result

    def record_continuity(
        self,
        client_id: str,
        conversation_id: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        """Record allowlisted continuity labels and counts for one client.

        This method never stores free-form prompts, responses, private names, or
        memory contents. Its purpose is to keep a tiny restart-safe navigation
        hint while the richer rolling summary remains client-owned.
        """

        key = self._key(client_id, conversation_id)
        continuity = _safe_continuity(value)
        with self._lock:
            board = self._boards.get(key)
            if board is None:
                board = CognitiveBlackboard(
                    client_id=key[0],
                    user_id="continuity-without-user-content",
                    conversation_id=key[1],
                    session_id="",
                )
                self._boards[key] = board
            board.continuity = continuity
            board.current_topic = continuity["active_topic"]
            board.updated_at = _now()
            self._boards.move_to_end(key)
            while len(self._boards) > self.maximum_conversations:
                self._boards.popitem(last=False)
            result = board.summary()
        self.checkpoint_now()
        return result

    def view(self, client_id: str, conversation_id: str | None = None) -> dict[str, Any]:
        client = _compact(client_id or "anonymous", 160)
        persistence = {
            "mode": self.persistence,
            "restart_safe": self.persistence == "checkpoint",
            "max_age_days": self.max_age_days,
            "prompt_content_stored": False,
            "response_content_stored": False,
        }
        with self._lock:
            if conversation_id:
                board = self._boards.get(self._key(client, conversation_id))
                return {
                    "object": "nova.world_model",
                    "schema_version": WORLD_MODEL_SCHEMA_VERSION,
                    "persistence": persistence,
                    "data": board.to_dict() if board else None,
                }
            boards = [
                board.summary()
                for (board_client, _), board in reversed(self._boards.items())
                if board_client == client
            ]
            return {
                "object": "list",
                "schema_version": WORLD_MODEL_SCHEMA_VERSION,
                "persistence": persistence,
                "data": boards,
            }

    def health_check(self) -> dict[str, Any]:
        with self._lock:
            return {
                "ok": True,
                "schema_version": WORLD_MODEL_SCHEMA_VERSION,
                "interface_version": WORLD_MODEL_INTERFACE_VERSION,
                "active_conversations": len(self._boards),
                "maximum_conversations": self.maximum_conversations,
                "persistence": (
                    "versioned_local_checkpoint"
                    if self.persistence == "checkpoint"
                    else "session_memory_only"
                ),
                "checkpoint_enabled": self.persistence == "checkpoint",
                "checkpoint_exists": bool(self.checkpoint_path and self.checkpoint_path.exists()),
                "checkpoint_loaded_conversations": self._loaded_count,
                "checkpoint_expired_conversations": self._expired_count,
                "checkpoint_invalid_records": self._invalid_record_count,
                "checkpoint_error": self._checkpoint_error or None,
                "checkpoint_quarantined": self._checkpoint_quarantined,
                "last_saved_at": self._last_saved_at or None,
                "max_age_days": self.max_age_days,
                "prompt_content_stored": False,
                "response_content_stored": False,
                "sensor_values_stored": False,
                "private_chain_of_thought_stored": False,
            }
