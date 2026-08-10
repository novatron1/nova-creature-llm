from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from nova_release_gates import (
    GateDefinition,
    GateRunner,
    default_gate_definitions,
    redact_gate_output,
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


def _force_kill_test_process(pid: int) -> None:
    if not _process_is_running(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM if os.name == "nt" else signal.SIGKILL)
    except ProcessLookupError:
        return


def _gate_paths(tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    return candidate, tmp_path / "reports"


def _make_directory_link(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        link.symlink_to(target, target_is_directory=True)
        return
    command_processor = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    completed = subprocess.run(
        [command_processor, "/d", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
        timeout=5,
        shell=False,
    )
    if completed.returncode != 0:
        pytest.skip(f"could not create test junction: {completed.stderr}")


def test_gate_runner_records_observed_result(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    gate = GateDefinition(
        name="probe",
        argv=(sys.executable, "-c", "print('passed')"),
        timeout_seconds=5,
    )

    result = GateRunner(candidate, reports).run(gate)

    assert result.passed is True
    assert result.exit_code == 0
    assert result.command == [sys.executable, "-c", "print('passed')"]
    assert result.stdout_tail == "passed"
    assert result.stderr_tail == ""
    assert result.timed_out is False
    assert result.duration_seconds >= 0


def test_gate_runner_times_out_and_kills_process_tree(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    child_pid_path = candidate / "child.pid"
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

    result = GateRunner(candidate, reports).run(gate)

    assert result.passed is False
    assert result.timed_out is True
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(child_pid), f"child process {child_pid} survived"


def test_gate_runner_bounds_each_output_tail(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
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
        candidate,
        reports,
        max_output_bytes=12,
    ).run(gate)

    assert result.stdout_tail == "xxxxxxxxTAIL"
    assert result.stderr_tail == "yyyyyyyyFAIL"
    assert len(result.stdout_tail.encode("utf-8")) <= 12
    assert len(result.stderr_tail.encode("utf-8")) <= 12


def test_gate_runner_redacts_secret_and_candidate_path_output(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    candidate = candidate.resolve()
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

    result = GateRunner(candidate, reports).run(gate)

    assert "secret-token" not in result.stdout_tail
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in result.stdout_tail
    assert str(candidate) not in result.stdout_tail
    assert "[REDACTED]" in result.stdout_tail


def test_gate_runner_redacts_name_and_every_command_argument(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    candidate = candidate.resolve()
    reports = reports.resolve()
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    gate = GateDefinition(
        name="Authorization: Bearer gate-name-secret-1234567890",
        argv=(
            sys.executable,
            "-c",
            "print('safe')",
            secret,
            f"--candidate={candidate}",
            json.dumps(str(reports)),
        ),
        timeout_seconds=5,
    )

    result = GateRunner(candidate, reports).run(gate)

    public_strings = [result.name, *result.command, result.stdout_tail, result.stderr_tail]
    recorded = "\n".join(public_strings)
    assert "gate-name-secret" not in recorded
    assert secret not in recorded
    assert str(candidate) not in recorded
    assert json.dumps(str(reports))[1:-1] not in recorded
    assert "[REDACTED]" in recorded


def test_redact_gate_output_handles_json_escaped_and_slash_path_variants() -> None:
    windows_path = r"C:\Sensitive\Candidate Root"
    escaped_windows_path = json.dumps(windows_path)[1:-1]
    output = "\n".join(
        [
            windows_path,
            windows_path.replace("\\", "/"),
            escaped_windows_path,
        ]
    )

    redacted = redact_gate_output(output, sensitive_paths=[windows_path])

    assert "Sensitive" not in redacted
    assert redacted.splitlines() == ["[REDACTED]"] * 3


@pytest.mark.parametrize(
    "marker",
    ["prompt", "response", "memory", "database_row"],
)
def test_redact_gate_output_suppresses_entire_multiline_private_record(
    marker: str,
) -> None:
    output = f"safe prefix\n{marker}: private first line\nprivate continuation\nsafe suffix"

    assert redact_gate_output(output) == "[REDACTED]"


def test_redact_gate_output_suppresses_multiline_structured_json_record() -> None:
    output = (
        'safe prefix\n{"prompt": "private first line",\n'
        '"continuation": "private second line"}\nsafe suffix'
    )

    assert redact_gate_output(output) == "[REDACTED]"


def test_gate_runner_reapplies_byte_cap_after_invalid_utf8_decode(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    script = (
        "import sys; sys.stdout.buffer.write("
        "b'x' * 20 + b'\\xff' + '💥END'.encode('utf-8'))"
    )

    result = GateRunner(candidate, reports, max_output_bytes=8).run(
        GateDefinition(
            name="invalid-utf8",
            argv=(sys.executable, "-c", script),
            timeout_seconds=5,
        )
    )

    assert result.stdout_tail == "💥END"
    assert len(result.stdout_tail.encode("utf-8")) <= 8


def test_gate_runner_reapplies_byte_cap_after_redaction(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)

    result = GateRunner(candidate, reports, max_output_bytes=8).run(
        GateDefinition(
            name="redaction-cap",
            argv=(
                sys.executable,
                "-c",
                "print('prompt:x')",
            ),
            timeout_seconds=5,
        )
    )

    assert "prompt" not in result.stdout_tail
    assert len(result.stdout_tail.encode("utf-8")) <= 8


def test_gate_runner_remembers_secret_marker_that_scrolls_out_of_tail(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)

    result = GateRunner(candidate, reports, max_output_bytes=8).run(
        GateDefinition(
            name="scrolled-secret",
            argv=(
                sys.executable,
                "-c",
                "print('Authorization: Bearer never-store-this-secret-value')",
            ),
            timeout_seconds=5,
        )
    )

    assert "secret" not in result.stdout_tail
    assert "value" not in result.stdout_tail
    assert len(result.stdout_tail.encode("utf-8")) <= 8


def test_gate_runner_preserves_valid_split_multibyte_suffix(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    script = (
        "import sys; sys.stdout.buffer.write(b'x' * 8191); "
        "sys.stdout.buffer.flush(); "
        "sys.stdout.buffer.write('💥END'.encode('utf-8'))"
    )

    result = GateRunner(candidate, reports, max_output_bytes=7).run(
        GateDefinition(
            name="split-utf8",
            argv=(sys.executable, "-c", script),
            timeout_seconds=5,
        )
    )

    assert result.stdout_tail == "💥END"
    assert len(result.stdout_tail.encode("utf-8")) == 7


def test_gate_runner_uses_only_sanitized_environment(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
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
        candidate,
        reports,
        base_environment=base_environment,
    ).run(gate)

    assert result.passed is True
    assert json.loads(result.stdout_tail) == {
        "secret_present": False,
        "authorization_present": False,
        "model_warmup": "false",
        "remote_access": "false",
    }


def test_gate_runner_cleans_child_after_successful_leader_exit(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    child_pid_path = candidate / "early-child.pid"
    script = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'], stdin=subprocess.DEVNULL, "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
    )
    gate = GateDefinition(
        name="early-exit",
        argv=(sys.executable, "-c", script),
        timeout_seconds=5,
    )

    result = GateRunner(candidate, reports).run(gate)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    try:
        assert result.passed is True
        assert _wait_for_process_exit(child_pid), f"child {child_pid} survived"
    finally:
        _force_kill_test_process(child_pid)


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal behavior")
def test_gate_runner_kills_sigterm_ignoring_descendant_after_leader_exit(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    child_pid_path = candidate / "ignoring-child.pid"
    child_code = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
    )
    script = (
        "import pathlib, subprocess, sys; "
        f"child = subprocess.Popen([sys.executable, '-c', {child_code!r}], "
        "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, "
        "stderr=subprocess.DEVNULL); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
    )

    result = GateRunner(candidate, reports).run(
        GateDefinition(
            name="ignore-term",
            argv=(sys.executable, "-c", script),
            timeout_seconds=5,
        )
    )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    try:
        assert result.passed is True
        assert _wait_for_process_exit(child_pid), f"child {child_pid} survived"
    finally:
        _force_kill_test_process(child_pid)


def test_gate_runner_requires_pipe_drains_to_finish_after_tree_cleanup(
    tmp_path: Path,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    child_pid_path = candidate / "pipe-child.pid"
    script = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
    )

    started = time.monotonic()
    result = GateRunner(candidate, reports).run(
        GateDefinition(
            name="pipe-cleanup",
            argv=(sys.executable, "-c", script),
            timeout_seconds=5,
        )
    )
    elapsed = time.monotonic() - started
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    try:
        assert result.passed is True
        assert elapsed < 4
        assert _wait_for_process_exit(child_pid), f"child {child_pid} survived"
    finally:
        _force_kill_test_process(child_pid)


def test_gate_runner_rejects_report_directory_inside_candidate(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()

    with pytest.raises(ValueError, match="outside"):
        GateRunner(candidate, candidate / "reports")


def test_gate_runner_rejects_linked_report_directory(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    outside = tmp_path / "redirected"
    report_link = tmp_path / "report-link"
    _make_directory_link(report_link, outside)

    with pytest.raises(ValueError, match="link|reparse"):
        GateRunner(candidate, report_link)


@pytest.mark.parametrize(
    "redirected_name",
    ["smoke.json", "smoke.server.stdout.log", "smoke.server.stderr.log"],
)
def test_clean_start_smoke_rejects_redirected_output_before_launch(
    tmp_path: Path,
    redirected_name: str,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        """
        from pathlib import Path
        Path("server-started").write_text("started")
        raise SystemExit(3)
        """,
    )
    reports = tmp_path / "reports"
    reports.mkdir()
    _make_directory_link(
        reports / redirected_name,
        tmp_path / f"redirect-target-{redirected_name.replace('.', '-')}",
    )

    with pytest.raises(ValueError, match="link|reparse"):
        run_clean_start_smoke(
            candidate,
            reports / "smoke.json",
            timeout_seconds=2,
        )

    assert not (candidate / "server-started").exists()


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


def test_clean_start_smoke_rejects_oversized_health_body_before_probe(
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
                body = json.dumps({"ok": True, "padding": "x" * 70000}).encode()
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
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        "from pathlib import Path\nPath('probe-ran').write_text('yes')\n",
        encoding="utf-8",
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=2,
    )

    assert result.passed is False
    assert not (candidate / "probe-ran").exists()


def test_clean_start_smoke_trickled_health_body_obeys_global_deadline(
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
        import time

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True, "padding": "slow"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.12)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )

    started = time.monotonic()
    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - started

    assert result.passed is False
    assert result.timed_out is True
    assert elapsed < 1.6


def test_clean_start_smoke_probe_cannot_round_past_global_deadline(
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
        import time

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                for byte in body:
                    self.wfile.write(bytes([byte]))
                    self.wfile.flush()
                    time.sleep(0.06)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        "import time\ntime.sleep(30)\n",
        encoding="utf-8",
    )

    started = time.monotonic()
    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=1,
    )
    elapsed = time.monotonic() - started

    assert result.passed is False
    assert result.timed_out is True
    assert elapsed < 1.5


def test_clean_start_smoke_requires_leader_alive_after_readiness(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        """
        import json
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import sys

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        server = HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler)
        server.handle_request()
        """,
    )
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        "from pathlib import Path\nPath('probe-ran').write_text('yes')\n",
        encoding="utf-8",
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=2,
    )

    assert result.passed is False
    assert not (candidate / "probe-ran").exists()


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
