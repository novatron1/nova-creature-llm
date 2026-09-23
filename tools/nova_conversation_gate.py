"""Repeatable privacy and routing smoke gate for ordinary Nova conversation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nova_gateway.config import GatewayConfig  # noqa: E402
from nova_gateway.core import NovaGatewayCore  # noqa: E402
from nova_protocol import NovaGenerationOptions, NovaMessage, NovaRequest  # noqa: E402


def load_cases(path: str | Path, *, count: int = 100) -> list[dict[str, Any]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise ValueError("Conversation regression fixture must be a non-empty array.")
    normalized = [row for row in rows if isinstance(row, dict) and str(row.get("prompt") or "").strip()]
    if not normalized:
        raise ValueError("Conversation regression fixture has no valid prompts.")
    target = max(1, int(count))
    cases: list[dict[str, Any]] = []
    for index in range(target):
        source = dict(normalized[index % len(normalized)])
        source["id"] = f"{source.get('id') or 'case'}-{index + 1:03d}"
        source["prompt"] = str(source["prompt"]).strip()
        cases.append(source)
    return cases


def run_gate(
    fixture: str | Path,
    *,
    count: int = 100,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    cases = load_cases(fixture, count=count)

    def runner(text: str, context: dict[str, Any]):
        case_id = str(context.get("nova_request", {}).get("request_id") or "case")
        return f"LLM candidate for {case_id}.", {"source": "mock_llm", "local_llm_synthesis_used": True}

    core = NovaGatewayCore(
        runner,
        config=GatewayConfig(
            rate_limit_enabled=False,
            world_model_persistence="session",
            conversation_store_path=Path(fixture).resolve().parent / ".gate-conversations.json",
        ),
        register_ollama=False,
    )
    failures: list[dict[str, str]] = []
    route_counts: dict[str, int] = {}
    for index, case in enumerate(cases, start=1):
        request_id = f"gate-{index:03d}"
        answer_marker = f"LLM candidate for {request_id}."
        try:
            response = core.generate(
                NovaRequest(
                    request_id=request_id,
                    conversation_id=f"gate-conversation-{index:03d}",
                    messages=[NovaMessage(role="user", content=case["prompt"])],
                    generation_options=NovaGenerationOptions(model="nova"),
                    metadata={
                        "client_scopes": ["chat.generate", "memory.read"],
                        "memory_read_allowed": case.get("category") == "memory",
                    },
                )
            )
            metadata_text = json.dumps(response.metadata, ensure_ascii=False, sort_keys=True)
            route = str(response.metadata.get("route_summary", {}).get("provider") or response.provider or "unknown")
            route_counts[route] = route_counts.get(route, 0) + 1
            if answer_marker in metadata_text or case["prompt"] in metadata_text:
                failures.append({"id": request_id, "reason": "content_leaked_into_metadata"})
            if not str(response.content or "").strip():
                failures.append({"id": request_id, "reason": "empty_answer"})
        except Exception as error:  # pragma: no cover - reported by the gate
            failures.append({"id": request_id, "reason": type(error).__name__})

    report = {
        "schema_version": "1.0",
        "ok": not failures,
        "total": len(cases),
        "passed": len(cases) - len(failures),
        "failed": len(failures),
        "route_counts": route_counts,
        "failures": failures[:20],
        "privacy": {
            "prompt_content_stored": False,
            "answer_content_stored": False,
            "private_reasoning_stored": False,
        },
    }
    if report_path:
        destination = Path(report_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", default=str(ROOT / "tests" / "fixtures" / "nova_conversation_regression.json"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--report", default=str(ROOT / "reports" / "nova_conversation_gate.json"))
    args = parser.parse_args()
    report = run_gate(args.fixture, count=args.count, report_path=args.report)
    print(json.dumps({key: report[key] for key in ("ok", "total", "passed", "failed", "route_counts")}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
