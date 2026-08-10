from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

from nova_release_gates import (
    GateDefinition,
    GateRunner,
    default_gate_definitions,
    run_clean_start_smoke,
)


def _process_is_running(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _wait_for_process_exit(pid: int, timeout_seconds: float = 5) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not _process_is_running(pid):
            return True
        time.sleep(0.05)
    return not _process_is_running(pid)


def test_gate_runner_records_observed_result(tmp_path: Path) -> None:
    gate = GateDefinition(
        name="probe",
        argv=(sys.executable, "-c", "print('passed')"),
        timeout_seconds=5,
    )

    result = GateRunner(tmp_path, tmp_path / "reports").run(gate)

    assert result.passed is True
    assert result.exit_code == 0
    assert result.command == [sys.executable, "-c", "print('passed')"]
    assert result.stdout_tail == "passed"
    assert result.stderr_tail == ""
    assert result.timed_out is False
    assert result.duration_seconds >= 0


def test_gate_runner_times_out_and_kills_process_tree(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    gate = GateDefinition(
        name="timeout",
        argv=(sys.executable, "-c", script),
        timeout_seconds=1,
    )

    result = GateRunner(tmp_path, tmp_path / "reports").run(gate)

    assert result.passed is False
    assert result.timed_out is True
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(child_pid), f"child process {child_pid} survived"


def test_gate_runner_bounds_each_output_tail(tmp_path: Path) -> None:
    gate = GateDefinition(
        name="bounded",
        argv=(
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('x' * 100 + 'TAIL'); "
            "sys.stderr.write('y' * 100 + 'FAIL')",
        ),
        timeout_seconds=5,
    )

    result = GateRunner(
        tmp_path,
        tmp_path / "reports",
        max_output_bytes=12,
    ).run(gate)

    assert result.stdout_tail == "xxxxxxxxTAIL"
    assert result.stderr_tail == "yyyyyyyyFAIL"
    assert len(result.stdout_tail.encode("utf-8")) <= 12
    assert len(result.stderr_tail.encode("utf-8")) <= 12


def test_gate_runner_redacts_secret_and_candidate_path_output(tmp_path: Path) -> None:
    candidate = tmp_path.resolve()
    script = (
        "print('Authorization: Bearer secret-token-value-1234567890'); "
        "print('sk-abcdefghijklmnopqrstuvwxyz123456'); "
        f"print({str(candidate)!r})"
    )
    gate = GateDefinition(
        name="redaction",
        argv=(sys.executable, "-c", script),
        timeout_seconds=5,
    )

    result = GateRunner(candidate, candidate / "reports").run(gate)

    assert "secret-token" not in result.stdout_tail
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in result.stdout_tail
    assert str(candidate) not in result.stdout_tail
    assert "[REDACTED]" in result.stdout_tail


def test_gate_runner_uses_only_sanitized_environment(tmp_path: Path) -> None:
    variable = "NOVA_TEST_SECRET_DO_NOT_COPY"
    base_environment = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        variable: "private-value",
        "AUTHORIZATION": "Bearer private-value",
    }
    script = (
        "import json, os; print(json.dumps({"
        f"'secret_present': {variable!r} in os.environ, "
        "'authorization_present': 'AUTHORIZATION' in os.environ, "
        "'model_warmup': os.environ.get('NOVA_MODEL_WARMUP'), "
        "'remote_access': os.environ.get('NOVA_ENABLE_REMOTE_ACCESS')}))"
    )
    gate = GateDefinition(
        name="environment",
        argv=(sys.executable, "-c", script),
        timeout_seconds=5,
    )

    result = GateRunner(
        tmp_path,
        tmp_path / "reports",
        base_environment=base_environment,
    ).run(gate)

    assert result.passed is True
    assert json.loads(result.stdout_tail) == {
        "secret_present": False,
        "authorization_present": False,
        "model_warmup": "false",
        "remote_access": "false",
    }


def test_default_gate_definitions_cover_required_release_checks(
    tmp_path: Path,
) -> None:
    candidate = (tmp_path / "candidate").resolve()
    reports = (tmp_path / "reports").resolve()
    python = str(tmp_path / "python-3.11")

    gates = default_gate_definitions(
        candidate,
        reports,
        python_executable=python,
    )

    assert [gate.name for gate in gates] == [
        "release_focused",
        "dependency_lock",
        "sbom",
        "javascript",
        "application_acceptance",
        "python_full",
        "conversation_560",
        "clean_start_smoke",
    ]
    by_name = {gate.name: gate for gate in gates}
    assert by_name["release_focused"].argv == (
        python,
        "-m",
        "pytest",
        "tests/test_nova_release_policy.py",
        "tests/test_nova_release_security.py",
        "tests/test_nova_release_manifest.py",
        "tests/test_nova_release_worktree.py",
        "tests/test_nova_release_gates.py",
        "tests/test_nova_release_lock.py",
        "-q",
    )
    assert by_name["dependency_lock"].argv == (
        python,
        "-m",
        "nova_release_security",
        "verify-lock",
        "requirements-runtime.lock",
    )
    assert by_name["sbom"].argv == (
        python,
        "-m",
        "nova_release_security",
        "sbom",
        str(reports / "nova-sbom.json"),
    )
    assert by_name["javascript"].argv == (
        python,
        "-m",
        "pytest",
        "tests/test_nova_companion_javascript.py",
        "-q",
    )
    assert by_name["application_acceptance"].argv == (
        python,
        "-m",
        "pytest",
        "tests/test_nova_practical_support_final_fix.py",
        "tests/test_nova_companion_routes.py",
        "tests/test_nova_companion_source.py",
        "tests/test_nova_companion_pwa.py",
        "tests/test_nova_model_provider.py",
        "tests/test_nova_memory_v2.py",
        "tests/test_nova_companion_vision_service.py",
        "-q",
    )
    assert by_name["python_full"].argv == (
        python,
        "-m",
        "pytest",
        "-q",
    )
    assert by_name["conversation_560"].argv == (
        python,
        "tools/run_conversation_eval.py",
        "--pack",
        "data/evals/nova_conversation_variations_v1.json",
        "--output",
        str(reports / "conversation-560.json"),
    )
    assert by_name["clean_start_smoke"].argv == (
        python,
        "tools/nova_release_smoke.py",
        "--root",
        str(candidate),
        "--report",
        str(reports / "smoke.json"),
    )
    assert all(gate.required for gate in gates)


def _write_fake_smoke_candidate(candidate: Path, server_source: str) -> None:
    tools = candidate / "tools"
    tools.mkdir(parents=True)
    (candidate / "src").mkdir()
    (candidate / "nova_enhanced_server.py").write_text(
        textwrap.dedent(server_source),
        encoding="utf-8",
    )
    (tools / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            from urllib.request import urlopen

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            with urlopen(args.url + "/healthz", timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("ok") is not True:
                raise SystemExit(1)
            print("PROBE_OK")
            """
        ),
        encoding="utf-8",
    )


def test_clean_start_smoke_reports_startup_probe_and_process_tree_cleanup(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        """
        import json
        import os
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import subprocess
        import sys
        import time

        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"]
        )
        print(f"CHILD_PID={child.pid}", flush=True)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/healthz":
                    self.send_error(404)
                    return
                body = json.dumps({"ok": True, "version": "2026.fake"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    report_path = tmp_path / "reports" / "smoke.json"

    result = run_clean_start_smoke(
        candidate,
        report_path,
        timeout_seconds=5,
    )

    assert result.name == "clean_start_smoke"
    assert result.passed is True
    assert result.timed_out is False
    assert "PROBE_OK" in result.stdout_tail
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["startup_healthy"] is True
    assert report["probe_passed"] is True
    assert report["cleanup_complete"] is True
    assert report["server_pid"] > 0
    assert report["port"] > 0
    assert _wait_for_process_exit(report["server_pid"])
    stdout_path = report_path.parent / report["server_stdout_file"]
    stderr_path = report_path.parent / report["server_stderr_file"]
    assert stdout_path.is_file()
    assert stderr_path.is_file()
    assert candidate.resolve() not in stdout_path.resolve().parents
    server_output = stdout_path.read_text(encoding="utf-8")
    child_pid = int(server_output.split("CHILD_PID=", 1)[1].splitlines()[0])
    assert _wait_for_process_exit(child_pid), f"server child {child_pid} survived"


def test_clean_start_smoke_records_server_exit_before_health_as_failure(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        """
        import sys
        print("SERVER_EXITED_EARLY", file=sys.stderr, flush=True)
        raise SystemExit(3)
        """,
    )
    report_path = tmp_path / "reports" / "smoke.json"

    result = run_clean_start_smoke(
        candidate,
        report_path,
        timeout_seconds=3,
    )

    assert result.passed is False
    assert result.timed_out is False
    assert result.exit_code == 3
    assert "SERVER_EXITED_EARLY" in result.stderr_tail
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["startup_healthy"] is False
    assert report["probe_passed"] is False
    assert report["cleanup_complete"] is True
    assert _wait_for_process_exit(report["server_pid"])


def test_release_smoke_cli_runs_isolated_candidate_and_writes_report(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        """
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import sys

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True, "version": "2026.fake"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    report_path = tmp_path / "reports" / "cli-smoke.json"
    repository_root = Path(__file__).resolve().parents[1]
    tool = repository_root / "tools" / "nova_release_smoke.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(tool),
            "--root",
            str(candidate),
            "--report",
            str(report_path),
            "--timeout-seconds",
            "5",
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=10,
        shell=False,
    )

    assert completed.returncode == 0, completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["name"] == "clean_start_smoke"
    assert observed["passed"] is True
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["probe_passed"] is True
    assert report["cleanup_complete"] is True
    assert _wait_for_process_exit(report["server_pid"])
