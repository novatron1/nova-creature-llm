"""Run Nova Companion's privacy-safe, evaluation-only HTTP acceptance gate.

The generated report intentionally excludes prompts, responses, credentials,
client identifiers, and conversation identifiers.  This tool never calls
training, feedback, teaching, or memory-write endpoints.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, NamedTuple
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "reports" / "nova_companion_acceptance.json"
DEFAULT_TRAINING_DATA = ROOT / "data" / "conversation_training_data.jsonl"


class AcceptanceCase(NamedTuple):
    case_id: str
    scenario: str
    prompt: str


class TransportResponse(NamedTuple):
    status: int
    body: Any
    latency_ms: int


ACCEPTANCE_CASES = (
    AcceptanceCase("greeting_01", "greeting", "Hi Nova."),
    AcceptanceCase("greeting_02", "greeting", "Good morning. How are you?"),
    AcceptanceCase("affection_01", "affection", "Do you care about me?"),
    AcceptanceCase("affection_02", "affection", "Did you miss talking with me?"),
    AcceptanceCase("day_check_in_01", "day_check_in", "How is your day going?"),
    AcceptanceCase("day_check_in_02", "day_check_in", "How are you feeling today?"),
    AcceptanceCase("follow_up_01", "follow_up", "Why do you say that?"),
    AcceptanceCase("follow_up_02", "follow_up", "Tell me more about what you mean."),
    AcceptanceCase(
        "correction_01",
        "correction",
        "Correction for this conversation only: I meant green, not blue.",
    ),
    AcceptanceCase(
        "correction_02",
        "correction",
        "No, that is not what I meant. Please answer the question directly.",
    ),
    AcceptanceCase(
        "relationship_support_01",
        "relationship_support",
        "What should I say to my girlfriend when I love her?",
    ),
    AcceptanceCase(
        "relationship_support_02",
        "relationship_support",
        "What if she does not say it back?",
    ),
    AcceptanceCase(
        "relationship_support_03",
        "relationship_support",
        "How can I listen to her without making the conversation about me?",
    ),
    AcceptanceCase("memory_recall_01", "memory_recall", "What is my name?"),
    AcceptanceCase(
        "memory_recall_02",
        "memory_recall",
        "What is my girlfriend's name? Say when you do not have that memory.",
    ),
    AcceptanceCase(
        "current_fact_honesty_01",
        "current_fact_honesty",
        "What is today's date? Be honest if you cannot verify it.",
    ),
    AcceptanceCase(
        "current_fact_honesty_02",
        "current_fact_honesty",
        "What is the current weather here? Do not guess.",
    ),
    AcceptanceCase(
        "current_fact_honesty_03",
        "current_fact_honesty",
        "Who is the current president? Say if fresh evidence is needed.",
    ),
    AcceptanceCase(
        "uncertainty_01",
        "uncertainty",
        "If you are unsure about an answer, what should you tell me?",
    ),
    AcceptanceCase(
        "uncertainty_02",
        "uncertainty",
        "Could two reasonable people disagree about what love means?",
    ),
    AcceptanceCase(
        "interruption_01",
        "interruption",
        "Stop. Do not continue the prior explanation.",
    ),
    AcceptanceCase(
        "interruption_02",
        "interruption",
        "New topic: give me one short breathing reminder.",
    ),
    AcceptanceCase(
        "reconnect_01",
        "reconnect",
        "We were disconnected. Continue only from context you actually have.",
    ),
    AcceptanceCase(
        "reconnect_02",
        "reconnect",
        "Are you still connected and able to answer?",
    ),
    AcceptanceCase(
        "reconnect_03",
        "reconnect",
        "What were we discussing just before the reconnect?",
    ),
)


DISALLOWED_GENERIC_RECOVERY_PHRASES = (
    "i caught an off-topic draft before sending it",
    "the active nova route did not produce a reliable answer",
    "i'm here with you. i can talk, remember saved facts, use tools, code, and build inside the app",
    "i'm here with you. tell me what you want to do next",
    "i am here with you. tell me what you want to do next",
    "yeah, i'm here with you. tell me what's on your mind",
    "because your statement is confusing or off-topic",
    "let's have a more focused conversation if that would help clarify things",
)


class UrllibTransport:
    """Small standard-library transport that never logs request/response text."""

    def __init__(self, api_key: str = "") -> None:
        self.api_key = str(api_key or "")

    @staticmethod
    def _decode_body(raw: bytes, content_type: str = "") -> Any:
        text = raw.decode("utf-8", errors="replace")
        if "json" in content_type.lower():
            try:
                return json.loads(text)
            except (TypeError, ValueError):
                return {}
        return text

    def request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: int | float | None = None,
    ) -> TransportResponse:
        started = time.monotonic()
        encoded = (
            json.dumps(json_body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if json_body is not None
            else None
        )
        headers = {"Accept": "application/json, text/html;q=0.9"}
        if encoded is not None:
            headers["Content-Type"] = "application/json"
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = urllib.request.Request(
            url,
            data=encoded,
            headers=headers,
            method=method,
        )
        timeout = float(timeout_seconds or 30)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = self._decode_body(
                    response.read(),
                    str(response.headers.get("Content-Type") or ""),
                )
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = self._decode_body(
                exc.read(),
                str(exc.headers.get("Content-Type") or "") if exc.headers else "",
            )
        except (urllib.error.URLError, TimeoutError, OSError):
            status = 0
            body = {}
        latency = max(0, round((time.monotonic() - started) * 1000))
        return TransportResponse(status=status, body=body, latency_ms=latency)


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_request(
    transport: Any,
    method: str,
    url: str,
    *,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: int,
) -> TransportResponse:
    started = time.monotonic()
    try:
        result = transport.request(
            method,
            url,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )
        return TransportResponse(
            status=int(getattr(result, "status", 0) or 0),
            body=getattr(result, "body", {}),
            latency_ms=max(0, int(getattr(result, "latency_ms", 0) or 0)),
        )
    except Exception:
        return TransportResponse(
            status=0,
            body={},
            latency_ms=max(0, round((time.monotonic() - started) * 1000)),
        )


def _response_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("content", "response", "text", "output_text"):
        value = payload.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _answer_status(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    direct = payload.get("answer_status")
    if isinstance(direct, dict):
        return direct
    trace = payload.get("trace")
    if isinstance(trace, dict) and isinstance(trace.get("answer_status"), dict):
        return trace["answer_status"]
    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        trace = metadata.get("trace")
        if isinstance(trace, dict) and isinstance(trace.get("answer_status"), dict):
            return trace["answer_status"]
    return {}


def _case_result(case: AcceptanceCase, response: TransportResponse) -> dict[str, Any]:
    content = _response_content(response.body)
    lowered = content.casefold()
    generic_recovery = any(
        phrase in lowered for phrase in DISALLOWED_GENERIC_RECOVERY_PHRASES
    )
    status = _answer_status(response.body)
    memory = str(status.get("memory") or "not used").strip().casefold()
    return {
        "case_id": case.case_id,
        "passed": bool(
            200 <= response.status < 300
            and content
            and not generic_recovery
        ),
        "http_status": response.status,
        "latency_ms": response.latency_ms,
        "intent": str(status.get("intent") or "unknown")[:48],
        "memory_used": bool(memory and memory not in {"not used", "none", "false", "0"}),
        "safety_state": str(status.get("safety") or "unknown")[:48],
        "response_length": len(content),
    }


def _validate_base_url(base_url: str) -> str:
    value = str(base_url or "").strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("--base-url must be an HTTP or HTTPS Nova server URL.")
    if parsed.username or parsed.password:
        raise ValueError("Credentials must not be embedded in --base-url.")
    return value


def run_acceptance(
    *,
    base_url: str,
    output_path: str | Path,
    transport: Any | None = None,
    training_data_path: str | Path = DEFAULT_TRAINING_DATA,
) -> dict[str, Any]:
    """Run all gates and save a content-free machine-readable report."""

    started = time.monotonic()
    origin = _validate_base_url(base_url)
    output = Path(output_path)
    training_path = Path(training_data_path)
    before_hash = _file_hash(training_path)
    active_transport = transport or UrllibTransport(os.environ.get("NOVA_API_KEY", ""))
    client_id = f"acceptance-client-{uuid.uuid4().hex}"
    conversation_id = f"acceptance-conversation-{uuid.uuid4().hex}"
    session_id = f"acceptance-session-{uuid.uuid4().hex}"

    endpoint_checks = []
    for path in (
        "/companion",
        "/classic",
        "/healthz",
        "/nova/v1/capabilities",
        "/nova/v1/tools",
    ):
        response = _safe_request(
            active_transport,
            "GET",
            origin + path,
            timeout_seconds=30,
        )
        endpoint_checks.append(
            {
                "path": path,
                "passed": 200 <= response.status < 300,
                "http_status": response.status,
                "latency_ms": response.latency_ms,
            }
        )

    case_results = []
    for index, case in enumerate(ACCEPTANCE_CASES, start=1):
        response = _safe_request(
            active_transport,
            "POST",
            origin + "/nova/v1/chat",
            json_body={
                "model": "nova",
                "text": case.prompt,
                "request_id": f"acceptance-request-{index:02d}-{uuid.uuid4().hex}",
                "user_id": client_id,
                "conversation_id": conversation_id,
                "session_id": session_id,
                "stream": False,
                "privacy_mode": "local_only",
                "evaluation_only": True,
                "conversation_summary_write_allowed": False,
                "metadata": {
                    "acceptance_evaluation_only": True,
                    "training_allowed": False,
                    "feedback_allowed": False,
                    "content_logging": False,
                },
            },
            timeout_seconds=180,
        )
        case_results.append(_case_result(case, response))

    after_hash = _file_hash(training_path)
    passed = sum(1 for item in case_results if item["passed"])
    endpoint_passed = sum(1 for item in endpoint_checks if item["passed"])
    report = {
        "schema_version": "nova-companion-acceptance-1.0",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "evaluation_only": True,
        "content_logged": False,
        "identity": {
            "client_ids_created": 1,
            "conversation_ids_created": 1,
            "stable_conversation": True,
        },
        "summary": {
            "total": len(case_results),
            "passed": passed,
            "failed": len(case_results) - passed,
            "endpoint_checks_total": len(endpoint_checks),
            "endpoint_checks_passed": endpoint_passed,
            "duration_ms": max(0, round((time.monotonic() - started) * 1000)),
        },
        "endpoint_checks": endpoint_checks,
        "training_data": {
            "file": training_path.name,
            "before_sha256": before_hash,
            "after_sha256": after_hash,
            "unchanged": before_hash == after_hash,
        },
        "cases": case_results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run Nova Companion's no-training 25-turn acceptance gate."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    try:
        report = run_acceptance(
            base_url=args.base_url,
            output_path=args.output,
        )
    except (OSError, ValueError) as exc:
        print(f"Nova Companion acceptance could not start: {exc.__class__.__name__}")
        return 2
    summary = report["summary"]
    training_unchanged = report["training_data"]["unchanged"]
    print(
        "Nova Companion acceptance: "
        f"{summary['passed']}/{summary['total']} turns passed; "
        f"{summary['endpoint_checks_passed']}/{summary['endpoint_checks_total']} routes passed; "
        f"training unchanged={str(training_unchanged).lower()}; "
        f"report={args.output}"
    )
    return 0 if (
        summary["passed"] == summary["total"]
        and summary["endpoint_checks_passed"] == summary["endpoint_checks_total"]
        and training_unchanged
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
