from pathlib import Path
import importlib.util
import json
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def test_assisted_bridge_disables_role_only_finetune():
    import v055_assisted_learning_bridge as bridge

    with pytest.raises(ValueError, match="role-only promotion is disabled"):
        bridge.run_finetune("memory_transformer")


def test_assisted_bridge_delegates_global_finetune_to_guarded_orchestrator(monkeypatch):
    import nova_hyper_training_orchestrator as orchestrator
    import v055_assisted_learning_bridge as bridge

    calls = []

    def fake_run(project_root):
        calls.append(Path(project_root))
        return {"run_id": "run-bridge", "verdict": "REJECTED"}

    monkeypatch.setattr(orchestrator, "run_hyper_training", fake_run)

    assert bridge.run_finetune() == {"run_id": "run-bridge", "verdict": "REJECTED"}
    assert calls == [ROOT]


def test_server_start_training_uses_single_guarded_thread(monkeypatch):
    import nova_enhanced_server as server

    created_threads = []
    server._TRAINING_RUNNING = False
    server._TRAINING_RUN_ID = None

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            created_threads.append(self)

        def start(self):
            pass

    monkeypatch.setattr(server.threading, "Thread", FakeThread)

    first = server._start_training()
    second = server._start_training()

    assert first[0] is True
    assert second[0] is False
    assert first[1] == second[1]
    assert len(created_threads) == 1
    assert created_threads[0].target is server._run_guarded_training
    assert created_threads[0].daemon is True


def test_server_start_training_is_locked_against_parallel_callers(monkeypatch):
    import nova_enhanced_server as server

    real_thread = threading.Thread
    created_threads = []
    caller_count = 8
    ready = threading.Barrier(caller_count)
    observed_false = threading.Barrier(caller_count)
    results = []
    results_lock = threading.Lock()

    class RaceFalse:
        def __bool__(self):
            try:
                observed_false.wait(timeout=0.25)
            except threading.BrokenBarrierError:
                pass
            return False

    class FakeThread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
            created_threads.append(self)

        def start(self):
            pass

    def call_start_training():
        ready.wait(timeout=1)
        result = server._start_training()
        with results_lock:
            results.append(result)

    server._TRAINING_RUNNING = RaceFalse()
    server._TRAINING_RUN_ID = None
    monkeypatch.setattr(server.threading, "Thread", FakeThread)

    callers = [real_thread(target=call_start_training) for _ in range(caller_count)]
    for caller in callers:
        caller.start()
    for caller in callers:
        caller.join(timeout=2)

    assert not any(caller.is_alive() for caller in callers)
    assert sum(1 for started, _ in results if started) == 1
    assert len(created_threads) == 1


def test_deep_learn_reports_guarded_run_id_without_starting_second_run(monkeypatch):
    import nova_enhanced_server as server

    calls = []

    def already_running():
        calls.append("start_checked")
        return False, "active-run"

    monkeypatch.setattr(server, "_start_training", already_running)

    response, trace = server.brain_route("deep learn")

    assert calls == ["start_checked"]
    assert "job ID" in response
    assert "active-run" in response
    assert trace["memory_event"] == "deep_learn"


def test_deep_learn_started_response_labels_immediate_id_as_job_id(monkeypatch):
    import nova_enhanced_server as server

    monkeypatch.setattr(server, "_start_training", lambda: (True, "hypertrain_job_123"))

    response, trace = server.brain_route("deep learn")

    assert "job ID: hypertrain_job_123" in response
    assert "run ID" not in response
    assert trace["memory_event"] == "deep_learn"


def test_training_status_shows_active_background_job_id():
    import nova_enhanced_server as server

    server._TRAINING_RUNNING = True
    server._TRAINING_RUN_ID = "hypertrain_job_active"
    server._TRAINING_LOG = []

    response, trace = server.brain_route("training status")

    assert "Training: RUNNING" in response
    assert "Background job ID: hypertrain_job_active" in response
    assert trace["skills"] == ["training_monitor"]


def test_guarded_training_log_includes_actual_report_run_and_paths(monkeypatch):
    import nova_enhanced_server as server
    import nova_hyper_training_orchestrator as orchestrator

    server._TRAINING_RUNNING = True
    server._TRAINING_RUN_ID = "hypertrain_job_queued"
    server._TRAINING_LOG = []

    def fake_run(project_root):
        return {
            "run_id": "report-run-456",
            "verdict": "PROMOTED",
            "candidate_joint": 91.25,
            "json_report": "reports/transformer_hyper_training_report-run-456.json",
            "markdown_report": "reports/transformer_hyper_training_report-run-456.md",
        }

    monkeypatch.setattr(orchestrator, "run_hyper_training", fake_run)

    server._run_guarded_training()

    assert server._TRAINING_RUNNING is False
    assert server._TRAINING_RUN_ID == "report-run-456"
    log_text = "\n".join(server._TRAINING_LOG)
    assert "run_id=report-run-456" in log_text
    assert "json=reports/transformer_hyper_training_report-run-456.json" in log_text
    assert "md=reports/transformer_hyper_training_report-run-456.md" in log_text


def test_transformer_hyper_training_cli_delegates_and_returns_success(monkeypatch, capsys):
    script = ROOT / "scripts" / "run_transformer_hyper_training.py"
    spec = importlib.util.spec_from_file_location("run_transformer_hyper_training", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    def fake_run(project_root, seed, route_epochs, role_epochs):
        calls.append((Path(project_root), seed, route_epochs, role_epochs))
        return {"run_id": "cli-run", "verdict": "REJECTED", "candidate_joint": 69.0}

    monkeypatch.setattr(module, "run_hyper_training", fake_run)

    exit_code = module.main(["--seed", "7", "--route-epochs", "2", "--role-epochs", "1"])

    assert exit_code == 0
    assert calls == [(ROOT, 7, 2, 1)]
    assert json.loads(capsys.readouterr().out)["run_id"] == "cli-run"


def test_transformer_hyper_training_cli_reports_blocked_on_exception(monkeypatch, capsys):
    script = ROOT / "scripts" / "run_transformer_hyper_training.py"
    spec = importlib.util.spec_from_file_location("run_transformer_hyper_training_error", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def fail_run(project_root, seed, route_epochs, role_epochs):
        raise RuntimeError("orchestrator exploded")

    monkeypatch.setattr(module, "run_hyper_training", fail_run)

    exit_code = module.main([])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["verdict"] == "BLOCKED"
    assert payload["error"]["type"] == "RuntimeError"
    assert "orchestrator exploded" in payload["error"]["message"]
