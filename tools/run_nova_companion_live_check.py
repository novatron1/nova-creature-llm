"""Run a small privacy-safe managed-chat continuity check.

The checker keeps prompts and answers in memory only. Its output contains
case IDs, latency, route labels, and the Companion safe trace projection;
conversation identifiers and model content are deliberately excluded.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "NOVA_COMPANION_LAYER_LIVE_TEST.json"
DEFAULT_TRAINING_DATA = ROOT / "data" / "conversation_training_data.jsonl"

CASES = (
    ("greeting", "Hi Nova, stay with me for this conversation."),
    ("casual_follow_up", "I am still thinking about the project we discussed."),
    ("venting", "I feel overwhelmed; I just need you to listen."),
    ("advice", "Give me one practical next step."),
    ("joking", "Give me a gentle joke about debugging this project."),
    ("technical_help", "Explain how to test the live chat route."),
    ("memory_recall", "What do you remember about the project thread?"),
    ("current_fact_protection", "What is the current weather right now?"),
)


class TransportResponse:
    def __init__(self, status: int, body: Any, latency_ms: int):
        self.status = int(status)
        self.body = body
        self.latency_ms = int(latency_ms)


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: int | float = 20,
    ) -> TransportResponse:
        encoded = json.dumps(json_body or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=encoded,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method=method,
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=float(timeout_seconds)) as response:
                raw = response.read()
                content_type = str(response.headers.get("Content-Type") or "")
                body: Any = raw.decode("utf-8", errors="replace")
                if "json" in content_type.lower():
                    try:
                        body = json.loads(body)
                    except (TypeError, ValueError):
                        body = {}
                return TransportResponse(response.status, body, round((time.monotonic() - started) * 1000))
        except urllib.error.HTTPError as exc:
            return TransportResponse(exc.code, {}, round((time.monotonic() - started) * 1000))
        except (urllib.error.URLError, TimeoutError, OSError):
            return TransportResponse(0, {}, round((time.monotonic() - started) * 1000))


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("content", "response", "text", "output_text"):
        if isinstance(body.get(key), str):
            return body[key].strip()
    return ""


def _trace(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {}
    trace = body.get("trace")
    if isinstance(trace, dict):
        return trace
    metadata = body.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("trace"), dict):
        return metadata["trace"]
    return {}


def _safe_companion(trace: dict[str, Any]) -> dict[str, Any]:
    companion = trace.get("companion")
    if not isinstance(companion, dict):
        return {"enabled": False, "memory_count": 0}
    plan = companion.get("social_plan") if isinstance(companion.get("social_plan"), dict) else {}
    return {
        "enabled": bool(companion.get("enabled")),
        "primary_mode": str(companion.get("primary_mode") or "unknown")[:48],
        "relationship_stage": str(companion.get("relationship_stage") or "unknown")[:32],
        "memory_count": max(0, min(int(companion.get("memory_count") or 0), 4)),
        "interaction_count": max(0, int(companion.get("interaction_count") or 0)),
        "state_persisted": bool(companion.get("state_persisted")),
        "social_tone": str(plan.get("tone") or "")[:48],
        "reference_memory": bool(companion.get("reference_memory")),
    }


def run_live_check(
    *,
    base_url: str,
    user_id: str,
    conversation_id: str,
    turns: int = 8,
    transport: Any | None = None,
    output_path: str | Path = DEFAULT_OUTPUT,
    training_data_path: str | Path = DEFAULT_TRAINING_DATA,
) -> dict[str, Any]:
    origin = str(base_url or "").strip().rstrip("/")
    if not origin.startswith(("http://", "https://")):
        raise ValueError("base_url must be an HTTP or HTTPS URL")
    count = max(1, min(int(turns or 8), len(CASES)))
    active_transport = transport or UrllibTransport()
    training_path = Path(training_data_path)
    before_hash = _file_hash(training_path)
    history: list[dict[str, str]] = []
    results: list[dict[str, Any]] = []
    started = time.monotonic()
    for index, (case_id, prompt) in enumerate(CASES[:count], start=1):
        request_body = {
            "model": "nova",
            "text": prompt,
            "request_id": f"live-check-{uuid.uuid4().hex}",
            "user_id": str(user_id or "live-check-user"),
            "conversation_id": str(conversation_id or "live-check-conversation"),
            "stream": False,
            "privacy_mode": "local_preferred",
            "live_companion_check": True,
            "conversation_history": list(history[-8:]),
            "metadata": {"live_companion_check": True, "content_logging": False},
        }
        try:
            response = active_transport.request(
                "POST",
                origin + "/api/chat",
                json_body=request_body,
                timeout_seconds=20,
            )
            status = int(getattr(response, "status", 0) or 0)
            body = getattr(response, "body", {})
            latency_ms = max(0, int(getattr(response, "latency_ms", 0) or 0))
        except Exception:
            status, body, latency_ms = 0, {}, 0
        content = _content(body)
        trace = _trace(body)
        results.append(
            {
                "case_id": case_id,
                "passed": bool(200 <= status < 300 and content),
                "http_status": status,
                "latency_ms": latency_ms,
                "route": str(trace.get("source") or trace.get("final_answer_source") or "unknown")[:64],
                "companion": _safe_companion(trace),
            }
        )
        if content:
            history.extend(({"role": "user", "content": prompt}, {"role": "assistant", "content": content}))
            history = history[-8:]
    after_hash = _file_hash(training_path)
    report = {
        "schema_version": "nova-companion-live-check-1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content_logged": False,
        "summary": {
            "turns": count,
            "passed": sum(1 for item in results if item["passed"]),
            "failed": sum(1 for item in results if not item["passed"]),
            "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
            "training_unchanged": before_hash == after_hash,
        },
        "training_data": {
            "file": training_path.name,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "unchanged": before_hash == after_hash,
        },
        "cases": results,
    }
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Nova Companion's privacy-safe managed-chat live check.")
    parser.add_argument("--base-url", default="http://127.0.0.1:3000")
    parser.add_argument("--user-id", default="live-check-user")
    parser.add_argument("--conversation-id", default="live-check-conversation")
    parser.add_argument("--turns", type=int, default=8)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = run_live_check(
            base_url=args.base_url,
            user_id=args.user_id,
            conversation_id=args.conversation_id,
            turns=args.turns,
            output_path=args.output,
        )
    except (OSError, ValueError) as exc:
        print(f"Nova Companion live check could not start: {exc.__class__.__name__}")
        return 2
    summary = report["summary"]
    print(
        "Nova Companion live check: "
        f"{summary['passed']}/{summary['turns']} turns passed; "
        f"training unchanged={str(summary['training_unchanged']).lower()}; "
        f"report={args.output}"
    )
    return 0 if summary["passed"] == summary["turns"] and summary["training_unchanged"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
