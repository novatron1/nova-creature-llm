from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_nova_companion_acceptance.py"
sys.path.insert(0, str(ROOT / "src"))

from nova_answer_firewall import GENERIC_FALLBACK_MARKERS as FIREWALL_GENERIC_MARKERS


def _load_runner():
    assert SCRIPT.exists(), "Task 11 acceptance runner has not been implemented."
    spec = importlib.util.spec_from_file_location("run_nova_companion_acceptance", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _RecordingTransport:
    def __init__(self, response_type, *, generic_case: int | None = None, on_last_chat=None):
        self.response_type = response_type
        self.generic_case = generic_case
        self.on_last_chat = on_last_chat
        self.calls: list[dict[str, object]] = []
        self.chat_calls = 0

    def request(self, method, url, *, json_body=None, timeout_seconds=None):
        path = urlsplit(url).path
        self.calls.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "timeout_seconds": timeout_seconds,
            }
        )
        if method == "GET":
            body = "<!doctype html><title>Nova</title>" if path in {"/companion", "/classic"} else {"ok": True}
            return self.response_type(status=200, body=body, latency_ms=3)

        self.chat_calls += 1
        if self.chat_calls == 25 and self.on_last_chat:
            self.on_last_chat()
        content = (
            "I caught an off-topic draft before sending it."
            if self.chat_calls == self.generic_case
            else f"Focused evaluation response {self.chat_calls}."
        )
        body = {
            "content": content,
            "metadata": {
                "trace": {
                    "answer_status": {
                        "intent": "social",
                        "memory": "not used",
                        "safety": "passed",
                    }
                }
            },
        }
        return self.response_type(status=200, body=body, latency_ms=7)


def test_acceptance_runner_uses_one_identity_and_exactly_25_evaluation_only_turns(tmp_path):
    runner = _load_runner()
    training = tmp_path / "conversation_training_data.jsonl"
    training.write_text('{"existing":true}\n', encoding="utf-8")
    output = tmp_path / "acceptance.json"
    transport = _RecordingTransport(runner.TransportResponse)

    report = runner.run_acceptance(
        base_url="http://nova.test",
        output_path=output,
        transport=transport,
        training_data_path=training,
    )

    chat_calls = [call for call in transport.calls if call["method"] == "POST"]
    assert len(chat_calls) == 25
    bodies = [call["json_body"] for call in chat_calls]
    assert len({body["user_id"] for body in bodies}) == 1
    assert len({body["conversation_id"] for body in bodies}) == 1
    assert len({body["session_id"] for body in bodies}) == 1
    assert all(body["evaluation_only"] is True for body in bodies)
    assert all(body["conversation_summary_write_allowed"] is False for body in bodies)
    assert all(body["metadata"]["training_allowed"] is False for body in bodies)
    assert report["summary"]["passed"] == 25
    assert report["training_data"]["unchanged"] is True

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert len(saved["cases"]) == 25
    assert set(saved["cases"][0]) == {
        "case_id",
        "passed",
        "http_status",
        "latency_ms",
        "intent",
        "memory_used",
        "safety_state",
        "response_length",
    }
    first_prompt = bodies[0]["text"]
    assert first_prompt not in output.read_text(encoding="utf-8")
    assert "Focused evaluation response" not in output.read_text(encoding="utf-8")


def test_acceptance_runner_checks_required_routes_and_all_required_scenarios(tmp_path):
    runner = _load_runner()
    output = tmp_path / "acceptance.json"
    transport = _RecordingTransport(runner.TransportResponse)

    report = runner.run_acceptance(
        base_url="http://nova.test/",
        output_path=output,
        transport=transport,
        training_data_path=tmp_path / "missing-training-data.jsonl",
    )

    get_paths = [call["path"] for call in transport.calls if call["method"] == "GET"]
    assert get_paths == [
        "/companion",
        "/classic",
        "/healthz",
        "/nova/v1/capabilities",
        "/nova/v1/tools",
    ]
    assert {case.scenario for case in runner.ACCEPTANCE_CASES} >= {
        "greeting",
        "affection",
        "day_check_in",
        "follow_up",
        "correction",
        "relationship_support",
        "memory_recall",
        "current_fact_honesty",
        "uncertainty",
        "interruption",
        "reconnect",
    }
    assert report["summary"]["endpoint_checks_passed"] == 5


def test_acceptance_runner_sends_bounded_ephemeral_history_without_reporting_content(tmp_path):
    runner = _load_runner()
    output = tmp_path / "acceptance.json"
    transport = _RecordingTransport(runner.TransportResponse)

    runner.run_acceptance(
        base_url="http://nova.test",
        output_path=output,
        transport=transport,
        training_data_path=tmp_path / "missing-training-data.jsonl",
    )

    bodies = [
        call["json_body"]
        for call in transport.calls
        if call["method"] == "POST"
    ]
    assert bodies[0].get("conversation_history") in (None, [])
    assert bodies[1]["conversation_history"] == [
        {"role": "user", "content": runner.ACCEPTANCE_CASES[0].prompt},
        {"role": "assistant", "content": "Focused evaluation response 1."},
    ]
    assert len(bodies[5]["conversation_history"]) == 8
    assert bodies[5]["conversation_history"][0] == {
        "role": "user",
        "content": runner.ACCEPTANCE_CASES[1].prompt,
    }
    reconnect_index = next(
        index
        for index, case in enumerate(runner.ACCEPTANCE_CASES)
        if case.case_id == "reconnect_01"
    )
    assert len(bodies[reconnect_index]["conversation_history"]) == 8
    assert bodies[reconnect_index]["conversation_history"][-2:] == [
        {
            "role": "user",
            "content": runner.ACCEPTANCE_CASES[reconnect_index - 1].prompt,
        },
        {
            "role": "assistant",
            "content": f"Focused evaluation response {reconnect_index}.",
        },
    ]

    serialized = output.read_text(encoding="utf-8")
    assert "conversation_history" not in serialized
    assert "Focused evaluation response" not in serialized
    assert all(case.prompt not in serialized for case in runner.ACCEPTANCE_CASES)


def test_acceptance_runner_fails_generic_recovery_and_training_mutation_without_leaking_content(tmp_path):
    runner = _load_runner()
    training = tmp_path / "conversation_training_data.jsonl"
    training.write_text("stable\n", encoding="utf-8")
    output = tmp_path / "acceptance.json"

    def mutate_training():
        training.write_text("changed\n", encoding="utf-8")

    transport = _RecordingTransport(
        runner.TransportResponse,
        generic_case=4,
        on_last_chat=mutate_training,
    )
    report = runner.run_acceptance(
        base_url="http://nova.test",
        output_path=output,
        transport=transport,
        training_data_path=training,
    )

    assert report["summary"]["passed"] == 24
    assert report["summary"]["failed"] == 1
    assert report["cases"][3]["passed"] is False
    assert report["training_data"]["unchanged"] is False
    serialized = output.read_text(encoding="utf-8")
    assert "off-topic draft" not in serialized
    assert '"changed\\n"' not in serialized


@pytest.mark.parametrize("marker", FIREWALL_GENERIC_MARKERS)
def test_acceptance_runner_rejects_every_canonical_firewall_generic_marker(marker):
    runner = _load_runner()
    result = runner._case_result(
        runner.ACCEPTANCE_CASES[0],
        runner.TransportResponse(
            status=200,
            body={
                "content": marker,
                "metadata": {
                    "trace": {
                        "answer_status": {
                            "intent": "social",
                            "memory": "not used",
                            "safety": "blocked",
                        }
                    }
                },
            },
            latency_ms=1,
        ),
    )

    assert marker in runner.GENERIC_FALLBACK_MARKERS
    assert result["passed"] is False
