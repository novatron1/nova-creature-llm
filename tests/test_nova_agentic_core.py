from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_agent_memory as agent_memory
import nova_agentic_core as agent
import nova_tools


def setup_function():
    agent.clear_pending_approval()


def test_agent_mode_can_be_enabled_and_disabled(monkeypatch):
    monkeypatch.setenv("NOVA_AGENT_MODE", "false")
    assert agent.get_agent_config().agent_mode is False
    assert agent.should_use_agent_mode("agent mode search project text") is False

    monkeypatch.setenv("NOVA_AGENT_MODE", "true")
    assert agent.get_agent_config().agent_mode is True
    assert agent.should_use_agent_mode("agent mode search project text") is True
    assert agent.should_use_agent_mode("agent write file note.txt with hello") is True


def test_simple_chat_does_not_trigger_tool_loop(monkeypatch):
    monkeypatch.setenv("NOVA_AGENT_MODE", "true")
    assert agent.should_use_agent_mode("hi") is False
    assert agent.should_use_agent_mode("what is your name") is False


def test_multi_step_request_triggers_planner(monkeypatch):
    monkeypatch.setenv("NOVA_AGENT_MODE", "true")
    plan = agent.create_plan("Use agent mode to search project text for brain_route", [])

    assert plan["needs_tools"] is True
    assert plan["plan"][0]["tool_needed"] == "search_project_text"


def test_planner_returns_valid_json_serializable_plan():
    plan = agent.create_plan("Use agent mode to list project files", [])
    encoded = json.dumps(plan)
    decoded = json.loads(encoded)

    assert decoded["goal"]
    assert isinstance(decoded["plan"], list)
    assert decoded["risk_level"] in {"safe", "medium", "high"}


def test_tool_registry_loads_expected_tools():
    registry = nova_tools.get_tool_registry()

    assert {
        "read_project_file",
        "list_project_files",
        "search_project_text",
        "write_project_file",
        "run_project_tests",
        "run_shell_command",
        "web_search",
    }.issubset(set(registry))
    assert registry["read_project_file"].risk_level == "safe"
    assert registry["write_project_file"].requires_approval is True


def test_safe_read_only_tools_work_inside_project_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    (tmp_path / "notes.txt").write_text("Nova agent can read safely.", encoding="utf-8")

    read = nova_tools.read_project_file({"path": "notes.txt"})
    listed = nova_tools.list_project_files({"path": "."})
    searched = nova_tools.search_project_text({"query": "agent can read"})

    assert read["content"] == "Nova agent can read safely."
    assert "notes.txt" in [item["path"] for item in listed["files"]]
    assert searched["matches"][0]["path"] == "notes.txt"


def test_path_traversal_outside_project_root_is_blocked(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)

    result = nova_tools.validate_tool_call("read_project_file", {"path": "../secret.txt"}, None)

    assert result["allowed"] is False
    assert "outside" in result["reason"].lower() or "blocked" in result["reason"].lower()


def test_file_write_requires_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    state = agent.initialize_agent_state("agent write file note.txt with hello")

    result = nova_tools.validate_tool_call(
        "write_project_file",
        {"path": "note.txt", "content": "hello"},
        state,
    )

    assert result["allowed"] is False
    assert result["approval_required"] is True


def test_shell_command_is_disabled_by_default():
    state = agent.initialize_agent_state("agent run shell command echo hi")

    result = nova_tools.validate_tool_call("run_shell_command", {"command": "echo hi"}, state)

    assert result["allowed"] is False
    assert result["approval_required"] is False
    assert "disabled" in result["reason"].lower()


def test_pending_approval_executes_only_exact_saved_action(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "AGENT_TRACE_DIR", tmp_path / "traces")
    monkeypatch.setattr(agent_memory, "MEMORY_FILE", tmp_path / "agent_memory.json")

    response, trace = agent.run_agentic_turn("agent write file note.txt with hello")

    assert "Approve this action" in response
    assert trace["requires_approval"] is True
    assert not (tmp_path / "note.txt").exists()

    approved, approved_trace = agent.run_agentic_turn("APPROVE")

    assert "ran write_project_file" in approved
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "hello"
    assert approved_trace["approved_action"]["action_name"] == "write_project_file"


def test_cancel_discards_pending_action(monkeypatch, tmp_path):
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    agent.run_agentic_turn("agent write file cancel.txt with nope")

    response, trace = agent.run_agentic_turn("CANCEL")

    assert "Canceled" in response
    assert trace["approval_canceled"] is True
    assert not (tmp_path / "cancel.txt").exists()
    assert agent.get_pending_approval() is None


def test_max_step_limit_stops_loops(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVA_AGENT_MAX_STEPS", "1")
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")

    response, trace = agent.run_agentic_turn("agent loop test search project text for alpha")

    assert trace["steps_taken_count"] <= 1
    assert trace["max_steps"] == 1
    assert response


def test_critic_can_mark_done_replan_and_fail_safe():
    done = agent.initialize_agent_state("done")
    done.final_answer = "Finished."
    assert agent.critique_progress(done)["status"] == "done"

    replan = agent.initialize_agent_state("replan")
    replan.errors.append("tool failed")
    assert agent.critique_progress(replan)["status"] == "replan"

    fail = agent.initialize_agent_state("fail")
    fail.requires_approval = True
    fail.errors.append("blocked unsafe action")
    assert agent.critique_progress(fail)["status"] == "fail_safe"


def test_agent_memory_saves_and_loads_relevant_summaries(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_memory, "MEMORY_FILE", tmp_path / "agent_memory.json")
    state = agent.initialize_agent_state("remember successful search pattern")
    state.current_goal = "search project text"
    state.final_answer = "Found brain_route in nova_enhanced_server.py"

    agent_memory.save_agent_memory(state)
    relevant = agent_memory.load_relevant_memory("where did brain_route appear")

    assert relevant
    assert "brain_route" in json.dumps(relevant)


def test_trace_files_are_created_when_tracing_enabled(monkeypatch, tmp_path):
    monkeypatch.setattr(agent, "AGENT_TRACE_DIR", tmp_path / "agent_traces")
    monkeypatch.setattr(agent_memory, "MEMORY_FILE", tmp_path / "agent_memory.json")
    monkeypatch.setattr(nova_tools, "PROJECT_ROOT", tmp_path)
    (tmp_path / "trace.txt").write_text("trace marker", encoding="utf-8")

    response, trace = agent.run_agentic_turn("agent mode search project text for trace marker")

    assert response
    trace_files = list((tmp_path / "agent_traces").glob("*.json"))
    assert trace_files
    payload = json.loads(trace_files[0].read_text(encoding="utf-8"))
    assert payload["trace_id"] == trace["trace_id"]
