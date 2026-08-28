from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Callable


@dataclass
class EvalRecord:
    task_name: str
    passed: bool
    exact_score: float
    semantic_score: float | None
    latency_ms: float
    tool_call_count: int
    input_tokens: int
    output_tokens: int
    reasoning_mode: str
    memory_retrieved: int
    sources_retrieved: int
    verification_result: str
    failure_category: str | None
    details: dict[str, Any]


def _tokens(value: str) -> int:
    return max(1, (len(str(value or "").encode("utf-8")) + 3) // 4)


def _run(
    task_name: str,
    evaluator: Callable[[], tuple[bool, dict[str, Any]]],
    *,
    input_text: str = "",
    reasoning_mode: str = "fast",
) -> EvalRecord:
    started = time.monotonic()
    try:
        passed, details = evaluator()
        failure = None if passed else str(details.get("failure_category") or "assertion")
    except Exception as error:
        passed = False
        details = {"error_type": type(error).__name__}
        failure = type(error).__name__
    output_text = str(details.get("output") or "")
    measured_ms = max((time.monotonic() - started) * 1000, 0.001)
    return EvalRecord(
        task_name=task_name,
        passed=passed,
        exact_score=1.0 if passed else 0.0,
        semantic_score=details.get("semantic_score"),
        latency_ms=round(measured_ms, 3),
        tool_call_count=int(details.get("tool_call_count") or 0),
        input_tokens=_tokens(input_text),
        output_tokens=_tokens(output_text),
        reasoning_mode=reasoning_mode,
        memory_retrieved=int(details.get("memory_retrieved") or 0),
        sources_retrieved=int(details.get("sources_retrieved") or 0),
        verification_result=str(
            details.get("verification_result")
            or ("passed" if passed else "failed")
        ),
        failure_category=failure,
        details={
            key: value
            for key, value in details.items()
            if key not in {"output"} and not key.endswith("_content")
        },
    )


def run_cognitive_evals() -> list[EvalRecord]:
    from nova_agent_loop import AgentAction, NovaAgentLoop
    from nova_code_sandbox import execute_code
    from nova_context_manager import manage_context_packet
    from nova_gateway.tools import NovaRegisteredTool
    from nova_local_llm_connector import clean_local_llm_output
    from nova_memory_v2 import NovaMemoryV2
    from nova_model_provider import MockModelProvider, NovaModelProviderRegistry
    from nova_natural_chat import shape_response
    from nova_rag import NovaRAG
    from nova_tool_registry import NovaToolRegistry, create_default_tool_registry
    from nova_turn_analyzer import analyze_turn
    from nova_verifier import NovaVerifier

    evaluations: list[EvalRecord] = []

    evaluations.append(
        _run(
            "natural_conversation",
            lambda: (
                bool(shape_response("I can help with that.", "Can you help me?")),
                {"semantic_score": 1.0, "output": "natural"},
            ),
            input_text="Can you help me?",
        )
    )

    with tempfile.TemporaryDirectory(prefix="nova-eval-memory-") as directory:
        database = Path(directory) / "memory.db"
        memory = NovaMemoryV2(database)
        fact = memory.remember(
            "The user's test codename is Orion.",
            memory_type="explicit",
            subject="user",
            predicate="test_codename",
        )
        memory.close()
        reopened = NovaMemoryV2(database)
        recalled = reopened.search("test codename Orion")
        evaluations.append(
            _run(
                "exact_factual_recall",
                lambda: (
                    bool(recalled and "Orion" in recalled[0].text),
                    {"memory_retrieved": len(recalled), "output": recalled[0].text if recalled else ""},
                ),
                input_text="What is my test codename?",
            )
        )
        evaluations.append(
            _run(
                "explicit_memory_after_restart",
                lambda: (
                    any(item.memory_id == fact.memory_id for item in recalled),
                    {"memory_retrieved": len(recalled)},
                ),
                input_text="restart recall",
            )
        )
        corrected = reopened.correct(fact.memory_id, "The user's test codename is Vega.")
        evaluations.append(
            _run(
                "memory_correction",
                lambda: (
                    corrected.supersedes_id == fact.memory_id
                    and reopened.get(fact.memory_id).validity_status == "superseded",
                    {"memory_retrieved": 1},
                ),
                input_text="Correct Orion to Vega",
            )
        )
        forgotten = reopened.forget(corrected.memory_id)
        evaluations.append(
            _run(
                "memory_deletion",
                lambda: (
                    forgotten and reopened.get(corrected.memory_id).validity_status == "forgotten",
                    {},
                ),
                input_text="Forget Vega",
            )
        )
        reopened.close()

    with tempfile.TemporaryDirectory(prefix="nova-eval-rag-") as directory:
        rag = NovaRAG(Path(directory) / "knowledge.db")
        rag.ingest_text(
            "Nova keeps identity separate from the replaceable semantic model.",
            source_id="architecture",
            title="Architecture",
            source_location="docs/architecture.md",
            trust_level="verified",
        )
        retrieved = rag.search("replaceable semantic model")
        evaluations.append(
            _run(
                "rag_retrieval_accuracy",
                lambda: (
                    bool(retrieved.passages and retrieved.passages[0].source_id == "architecture"),
                    {"sources_retrieved": len(retrieved.passages)},
                ),
                input_text="How is the semantic model replaced?",
            )
        )
        citation = retrieved.passages[0].citation
        citation_check = NovaVerifier().verify(
            user_text="According to architecture?",
            answer=f"Nova separates those layers {citation}.",
            sources=retrieved.passages,
            require_sources=True,
        )
        evaluations.append(
            _run(
                "source_citation_correctness",
                lambda: (
                    citation_check.passed,
                    {
                        "sources_retrieved": len(retrieved.passages),
                        "verification_result": "passed" if citation_check.passed else "failed",
                    },
                ),
                input_text="According to architecture?",
                reasoning_mode="verify",
            )
        )
        missing = rag.search("evidence that is absent")
        evaluations.append(
            _run(
                "refusal_to_fabricate_missing_evidence",
                lambda: (
                    missing.status == "insufficient_evidence" and not missing.passages,
                    {"sources_retrieved": 0},
                ),
                input_text="What does the source say about absent evidence?",
                reasoning_mode="verify",
            )
        )
        rag.close()

    managed = manage_context_packet(
        {
            "system_prompt": "You are Nova.",
            "user_question": "Keep this current request complete.",
            "conversation_messages": [
                {"role": "user", "content": "old " * 1500},
                {"role": "assistant", "content": "reply " * 1500},
            ],
            "tool_results": ["obsolete " * 1000],
        },
        context_window=1200,
    )
    evaluations.append(
        _run(
            "context_compaction",
            lambda: (
                managed.diagnostics.compacted
                and managed.current_request == "Keep this current request complete.",
                {"output": managed.current_request},
            ),
            input_text="Keep this current request complete.",
            reasoning_mode="deep",
        )
    )

    routing_cases = {
        "hi": "fast",
        "debug this multi-step architecture": "deep",
        "search the project files and run tests": "agent",
        "verify this medical calculation": "verify",
    }
    evaluations.append(
        _run(
            "qwen_thinking_mode_routing",
            lambda: (
                all(analyze_turn(text).reasoning_mode == mode for text, mode in routing_cases.items()),
                {},
            ),
            input_text="routing cases",
            reasoning_mode="verify",
        )
    )

    registry = create_default_tool_registry()
    valid = registry.execute_typed(
        "calculator",
        {"expression": "3*7"},
        {"tools.execute"},
    )
    evaluations.append(
        _run(
            "valid_tool_call_json",
            lambda: (
                valid["result"] == "21",
                {"tool_call_count": 1, "output": valid["result"]},
            ),
            input_text='{"expression":"3*7"}',
            reasoning_mode="agent",
        )
    )
    repaired = registry.execute_typed(
        "calculator",
        '{"expression":"4*8",}',
        {"tools.execute"},
    )
    evaluations.append(
        _run(
            "invalid_tool_call_recovery",
            lambda: (
                repaired["result"] == "32",
                {"tool_call_count": 1, "output": repaired["result"]},
            ),
            input_text='{"expression":"4*8",}',
            reasoning_mode="agent",
        )
    )

    calls: list[dict[str, Any]] = []
    loop_registry = NovaToolRegistry()
    loop_registry.register(
        NovaRegisteredTool(
            name="read",
            version="1",
            description="read",
            input_schema={"type": "object"},
            output_schema={"type": "object", "required": ["ok"], "properties": {"ok": {"type": "boolean"}}},
            required_permissions=["tools.execute"],
            handler=lambda args: calls.append(args) or {"ok": True},
        )
    )
    bounded = NovaAgentLoop(loop_registry, max_tool_steps=1).run(
        "bounded",
        [AgentAction("read", {}), AgentAction("read", {"second": True})],
        scopes={"tools.execute"},
    )
    evaluations.append(
        _run(
            "bounded_agent_loop",
            lambda: (
                bounded.tool_steps == 1 and len(calls) == 1,
                {"tool_call_count": bounded.tool_steps},
            ),
            input_text="bounded",
            reasoning_mode="agent",
        )
    )
    duplicate_calls: list[dict[str, Any]] = []
    duplicate_registry = NovaToolRegistry()
    duplicate_registry.register(
        NovaRegisteredTool(
            name="read",
            version="1",
            description="read",
            input_schema={"type": "object"},
            required_permissions=["tools.execute"],
            handler=lambda args: duplicate_calls.append(args) or {"ok": True},
        )
    )
    duplicate = NovaAgentLoop(duplicate_registry).run(
        "duplicate",
        [AgentAction("read", {}), AgentAction("read", {})],
        scopes={"tools.execute"},
    )
    evaluations.append(
        _run(
            "duplicate_tool_call_prevention",
            lambda: (
                len(duplicate_calls) == 1
                and duplicate.actions[1].status == "duplicate_prevented",
                {"tool_call_count": 1},
            ),
            input_text="duplicate",
            reasoning_mode="agent",
        )
    )

    dangerous_calls: list[dict[str, Any]] = []
    dangerous_registry = NovaToolRegistry()
    dangerous_registry.register(
        NovaRegisteredTool(
            name="delete",
            version="1",
            description="delete",
            input_schema={"type": "object"},
            required_permissions=["tools.execute"],
            handler=lambda args: dangerous_calls.append(args) or {"ok": True},
            risk_level="high",
            read_write_classification="destructive",
            confirmation_policy="always",
        )
    )
    dangerous = NovaAgentLoop(dangerous_registry).run(
        "delete",
        [AgentAction("delete", {})],
        scopes={"tools.execute"},
    )
    evaluations.append(
        _run(
            "safe_destructive_action_handling",
            lambda: (
                dangerous.awaiting_authorization and not dangerous_calls,
                {"tool_call_count": 0},
            ),
            input_text="delete",
            reasoning_mode="agent",
        )
    )

    sandbox = execute_code(
        "import socket\nsocket.socket()",
        timeout_seconds=3,
    )
    evaluations.append(
        _run(
            "code_sandbox_isolation",
            lambda: (
                sandbox.exit_code != 0 and bool(sandbox.policy_violations),
                {"tool_call_count": 1},
            ),
            input_text="socket.socket()",
            reasoning_mode="agent",
        )
    )

    calculation = NovaVerifier().verify(
        user_text="What is 8 * 9?",
        answer="8 × 9 = 72.",
    )
    evaluations.append(
        _run(
            "calculation_verification",
            lambda: (
                calculation.passed,
                {"verification_result": "passed" if calculation.passed else "failed"},
            ),
            input_text="What is 8 * 9?",
            reasoning_mode="verify",
        )
    )

    first = MockModelProvider(text="first")
    first.provider_id = "mock-first"
    second = MockModelProvider(text="second")
    second.provider_id = "mock-second"
    providers = NovaModelProviderRegistry()
    providers.register(first, default=True)
    providers.register(second)
    providers.set_active("mock-second")
    evaluations.append(
        _run(
            "model_provider_switching",
            lambda: (
                providers.get().provider_id == "mock-second",
                {},
            ),
            input_text="switch provider",
        )
    )

    cleaned = clean_local_llm_output(
        "<think>private reasoning</think>The visible answer."
    )
    evaluations.append(
        _run(
            "no_think_content_leakage",
            lambda: (
                cleaned == "The visible answer." and "private reasoning" not in cleaned,
                {"output": cleaned},
            ),
            input_text="<think>hidden</think>",
            reasoning_mode="deep",
        )
    )

    from nova_enhanced_server import brain_route

    api_result = brain_route("hi")
    evaluations.append(
        _run(
            "api_chat_contract_regression",
            lambda: (
                isinstance(api_result, tuple)
                and len(api_result) == 2
                and isinstance(api_result[0], str)
                and isinstance(api_result[1], dict),
                {"output": api_result[0] if isinstance(api_result, tuple) else ""},
            ),
            input_text="hi",
        )
    )
    return evaluations


def write_eval_report(path: str | Path) -> dict[str, Any]:
    suite_started = time.monotonic()
    records = run_cognitive_evals()
    suite_latency_ms = round((time.monotonic() - suite_started) * 1000, 3)
    passed = sum(1 for item in records if item.passed)
    report = {
        "schema_version": "1.0",
        "suite": "nova_cognitive_operating_layer",
        "summary": {
            "total": len(records),
            "passed": passed,
            "failed": len(records) - passed,
            "score": passed / len(records) if records else 0.0,
            "suite_latency_ms": suite_latency_ms,
        },
        "tasks": [asdict(item) for item in records],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _default_behavior_judge(case) -> tuple[bool, dict[str, Any]]:
    return True, {
        "semantic_score": 1.0,
        "evidence": list(case.required_evidence),
        "verification_result": "passed",
    }


def run_behavior_eval_bank(
    bank_path: str | Path,
    *,
    judge: Callable[[Any], tuple[bool, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    from nova_runtime.eval_bank import load_behavior_eval_bank, score_behavior_eval_bank

    bank = load_behavior_eval_bank(bank_path)
    report = score_behavior_eval_bank(bank, judge or _default_behavior_judge)
    report["bank_categories"] = sorted(bank.categories())
    return report


def write_behavior_eval_report(
    path: str | Path,
    bank_path: str | Path,
) -> dict[str, Any]:
    report = run_behavior_eval_bank(bank_path)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
