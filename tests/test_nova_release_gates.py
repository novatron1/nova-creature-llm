from __future__ import annotations

import ctypes
from dataclasses import replace
import errno
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest
import nova_release_gates

from nova_release_gates import (
    GateDefinition,
    GateRunner,
    _SafeReportDirectory,
    _connection_owned_by_containment,
    _launch_contained_process,
    _linux_connection_owner_pids,
    _listener_owned_by_containment,
    _sanitized_environment,
    _unused_loopback_port,
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


def _wait_for_listener(port: int, timeout_seconds: float = 5) -> bool:
    import socket

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(0.05)
    return False


def _wait_for_path(path: Path, timeout_seconds: float = 5) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if path.exists():
            return True
        time.sleep(0.05)
    return path.exists()


def _gate_paths(tmp_path: Path) -> tuple[Path, Path]:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    return candidate, tmp_path / "reports"


def test_unsupported_posix_is_rejected_before_report_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    reports = tmp_path / "reports"
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_OS_NAME", "posix")
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_SYSTEM", "darwin")

    with pytest.raises(RuntimeError, match="unsupported release-gate platform"):
        GateRunner(candidate, reports)

    assert not reports.exists()


@pytest.mark.parametrize("missing_api", ["pidfd_open", "pidfd_send_signal"])
def test_linux_preflight_rejects_missing_pidfd_api_before_report_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_api: str,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    reports = tmp_path / "reports"
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_OS_NAME", "posix")
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_SYSTEM", "linux")
    owner = os if missing_api == "pidfd_open" else signal
    monkeypatch.delattr(owner, missing_api, raising=False)

    with pytest.raises(RuntimeError, match="unsupported release-gate platform"):
        GateRunner(candidate, reports)

    assert not reports.exists()


def test_linux_preflight_rejects_kernel_pidfd_failure_and_closes_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    reports = tmp_path / "reports"
    descriptor = os.open(os.devnull, os.O_RDONLY)
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_OS_NAME", "posix")
    monkeypatch.setattr(nova_release_gates, "_PLATFORM_SYSTEM", "linux")
    monkeypatch.setattr(os, "pidfd_open", lambda pid: descriptor, raising=False)

    def reject_kernel_pidfd(descriptor: int, signum: int) -> None:
        raise OSError(errno.ENOSYS, "kernel pidfd signaling unavailable")

    monkeypatch.setattr(
        signal,
        "pidfd_send_signal",
        reject_kernel_pidfd,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="unsupported release-gate platform"):
        GateRunner(candidate, reports)

    with pytest.raises(OSError) as closed_descriptor:
        os.fstat(descriptor)
    assert closed_descriptor.value.errno == errno.EBADF
    assert not reports.exists()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux PIDFD proof")
def test_linux_preflight_probes_real_pidfd_without_descriptor_leak() -> None:
    before = len(list(Path("/proc/self/fd").iterdir()))

    nova_release_gates._ensure_supported_platform()

    after = len(list(Path("/proc/self/fd").iterdir()))
    assert after <= before


def test_linux_session_scan_fails_closed_at_entry_and_process_caps(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    for pid in (101, 102, 103):
        process = proc_root / str(pid)
        process.mkdir(parents=True)
        (process / "stat").write_text(
            f"{pid} (python) S 1 2 4242 0\n",
            encoding="ascii",
        )
    containment = nova_release_gates._ProcessContainment(
        SimpleNamespace(pid=999),  # type: ignore[arg-type]
        process_group_id=4242,
    )

    entry_capped = containment._linux_session_members(
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_entries=2,
        maximum_processes=10,
    )
    process_capped = containment._linux_session_members(
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_entries=10,
        maximum_processes=2,
    )

    assert entry_capped.complete is False
    assert process_capped.complete is False
    assert len(entry_capped.members) == 2
    assert len(process_capped.members) == 2
    assert set(entry_capped.members).issubset({101, 102, 103})
    assert set(process_capped.members).issubset({101, 102, 103})


def test_linux_session_scan_fails_closed_when_absolute_deadline_is_exhausted(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    process = proc_root / "101"
    process.mkdir(parents=True)
    (process / "stat").write_text(
        "101 (python) S 1 2 4242 0\n",
        encoding="ascii",
    )
    containment = nova_release_gates._ProcessContainment(
        SimpleNamespace(pid=999),  # type: ignore[arg-type]
        process_group_id=4242,
    )
    started = time.monotonic()

    scan = containment._linux_session_members(
        time.monotonic() - 1,
        proc_root=proc_root,
        maximum_entries=10,
        maximum_processes=10,
    )

    assert scan.members == ()
    assert scan.complete is False
    assert time.monotonic() - started < 0.1


@pytest.mark.parametrize(
    "stat_content",
    [b"malformed\n", b"x" * 4_097],
    ids=("malformed", "oversized"),
)
def test_linux_session_scan_treats_uncertain_stat_as_incomplete(
    tmp_path: Path,
    stat_content: bytes,
) -> None:
    proc_root = tmp_path / "proc"
    process = proc_root / "101"
    process.mkdir(parents=True)
    (process / "stat").write_bytes(stat_content)
    containment = nova_release_gates._ProcessContainment(
        SimpleNamespace(pid=999),  # type: ignore[arg-type]
        process_group_id=4242,
    )

    scan = containment._linux_session_members(
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_entries=10,
        maximum_processes=10,
    )

    assert scan.members == ()
    assert scan.complete is False


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


def test_gate_runner_redacts_sensitive_option_value_sequences(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    secrets = {
        "prompt": "private prompt words",
        "response": "private response words",
        "memory": "private memory contents",
        "password": "password-value-should-not-escape",
        "token": "token-value-should-not-escape",
    }
    gate = GateDefinition(
        name="contextual-redaction",
        argv=(
            sys.executable,
            "-c",
            "print('safe')",
            "--prompt",
            secrets["prompt"],
            "--response",
            secrets["response"],
            "--memory",
            secrets["memory"],
            "--password",
            secrets["password"],
            f"--api-token={secrets['token']}",
        ),
        timeout_seconds=5,
    )

    result = GateRunner(candidate, reports).run(gate)

    recorded = "\n".join(result.command)
    assert all(secret not in recorded for secret in secrets.values())
    assert recorded.count("[REDACTED]") >= len(secrets)


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
    ["prompt", "response", "memory", "database_row", "private"],
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


def test_posix_cleanup_rechecks_session_after_supervisor_is_reaped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSupervisor:
        pid = 4242
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def wait(self, timeout: float) -> int:
            self.returncode = 0
            return 0

    supervisor = FakeSupervisor()
    control_read, control_write = os.pipe()
    containment = nova_release_gates._ProcessContainment(
        supervisor,  # type: ignore[arg-type]
        process_group_id=supervisor.pid,
        control_fd=control_write,
    )

    def session_cleanup(
        active_containment: object,
        deadline: float,
    ) -> bool:
        return supervisor.poll() is None

    monkeypatch.setattr(
        nova_release_gates._ProcessContainment,
        "_terminate_linux_session_members",
        session_cleanup,
    )
    try:
        cleanup_complete = containment.terminate_and_verify()
    finally:
        os.close(control_read)

    assert cleanup_complete is False


def test_posix_cleanup_kills_and_reaps_stalled_supervisor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSupervisor:
        pid = 4242
        returncode: int | None = None
        killed = False

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            self.killed = True

        def wait(self, timeout: float) -> int:
            if not self.killed:
                raise subprocess.TimeoutExpired("supervisor", timeout)
            self.returncode = 1
            return 1

    supervisor = FakeSupervisor()
    control_read, control_write = os.pipe()
    containment = nova_release_gates._ProcessContainment(
        supervisor,  # type: ignore[arg-type]
        process_group_id=supervisor.pid,
        control_fd=control_write,
    )
    monkeypatch.setattr(
        nova_release_gates._ProcessContainment,
        "_terminate_linux_session_members",
        lambda containment, deadline: True,
    )
    try:
        cleanup_complete = containment.terminate_and_verify()
    finally:
        os.close(control_read)

    assert cleanup_complete is True
    assert supervisor.killed is True
    assert supervisor.returncode == 1


def test_windows_blocked_payload_preserves_timeout_and_cleanup_uncertainty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    release_writer = threading.Event()

    class FakeStream:
        closed = False

        def fileno(self) -> int:
            return 123

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        stdin = FakeStream()
        returncode: int | None = None

        def poll(self) -> int | None:
            return self.returncode

        def kill(self) -> None:
            self.returncode = 1

        def wait(self, timeout: float) -> int:
            self.returncode = 1
            return 1

    process = FakeProcess()

    def blocked_write(descriptor: int, payload: bytes) -> int:
        release_writer.wait(5)
        return len(payload)

    monkeypatch.setattr(os, "write", blocked_write)
    try:
        with pytest.raises(
            nova_release_gates._ContainedLaunchTimeout,
            match="payload exceeded launch deadline",
        ) as raised:
            nova_release_gates._write_windows_payload_with_deadline(
                process,  # type: ignore[arg-type]
                b"payload",
                time.monotonic() + 0.05,
            )
    finally:
        release_writer.set()

    assert raised.value.cleanup_complete is False
    assert process.returncode == 1
    assert process.stdin.closed is True


@pytest.mark.skipif(os.name != "nt", reason="Windows Job/payload proof")
def test_windows_launch_propagates_known_writer_cleanup_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, reports = _gate_paths(tmp_path)

    def fail_payload_write(
        process: object,
        payload: bytes,
        deadline: float,
    ) -> None:
        raise nova_release_gates._ContainedLaunchTimeout(
            "trusted supervisor payload exceeded launch deadline",
            cleanup_complete=False,
        )

    monkeypatch.setattr(
        nova_release_gates,
        "_write_windows_payload_with_deadline",
        fail_payload_write,
    )

    result = GateRunner(candidate, reports).run(
        GateDefinition(
            name="writer-cleanup-uncertain",
            argv=(sys.executable, "-c", "pass"),
            timeout_seconds=2,
        )
    )

    assert result.passed is False
    assert result.timed_out is True
    assert "process containment cleanup could not be verified" in result.stderr_tail


@pytest.mark.skipif(os.name == "nt", reason="POSIX supervisor behavior")
def test_posix_supervisor_pins_session_after_candidate_exit(
    tmp_path: Path,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    containment = _launch_contained_process(
        [sys.executable, "-c", "raise SystemExit(0)"],
        cwd=candidate,
        environment=_sanitized_environment(candidate, None),
        deadline=time.monotonic() + 5,
    )
    unrelated = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    try:
        assert containment.wait_candidate(5) == 0
        assert containment.process.poll() is None
        assert containment.owns_pid(unrelated.pid) is False
        assert containment.terminate_and_verify() is True
        assert _process_is_running(unrelated.pid) is True
    finally:
        if containment.process.poll() is None:
            containment.terminate_and_verify()
        _force_kill_test_process(unrelated.pid)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux FD/process proof")
def test_posix_supervisor_reports_spawn_failure_without_fd_leak(tmp_path: Path) -> None:
    candidate, _ = _gate_paths(tmp_path)
    before = len(list(Path("/proc/self/fd").iterdir()))

    with pytest.raises(OSError, match="candidate spawn failed"):
        _launch_contained_process(
            [str(candidate / "does-not-exist")],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 5,
        )

    after = len(list(Path("/proc/self/fd").iterdir()))
    assert after <= before


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux FD/process proof")
def test_posix_payload_encoding_failure_closes_all_descriptors(tmp_path: Path) -> None:
    candidate, _ = _gate_paths(tmp_path)
    before = len(list(Path("/proc/self/fd").iterdir()))

    with pytest.raises(TypeError):
        _launch_contained_process(
            [object()],  # type: ignore[list-item]
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 5,
        )

    after = len(list(Path("/proc/self/fd").iterdir()))
    assert after <= before


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux handshake proof")
def test_posix_handshake_timeout_reaps_supervisor_before_late_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    late_marker = candidate / "late-spawn"
    delayed_supervisor = (
        "import pathlib, time; time.sleep(1); "
        f"pathlib.Path({str(late_marker)!r}).write_text('late'); time.sleep(30)"
    )
    monkeypatch.setattr(nova_release_gates, "_POSIX_SUPERVISOR", delayed_supervisor)
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="handshake"):
        _launch_contained_process(
            [sys.executable, "-c", "print('must not launch')"],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 0.1,
        )

    assert time.monotonic() - started < 2
    time.sleep(0.2)
    assert not late_marker.exists()


def test_launch_rejects_expired_deadline_before_spawning_process(
    tmp_path: Path,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    marker = candidate / "must-not-launch"

    with pytest.raises(TimeoutError, match="launch deadline"):
        _launch_contained_process(
            [
                sys.executable,
                "-c",
                f"from pathlib import Path; Path({str(marker)!r}).write_text('bad')",
            ],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() - 1,
        )

    assert not marker.exists()


@pytest.mark.parametrize(
    "command",
    [
        ["x"] * 4_097,
        ["x" * 262_145],
    ],
    ids=("argument-count", "argument-size"),
)
def test_supervisor_payload_is_bounded_before_serialization(
    command: list[str],
) -> None:
    started = time.monotonic()

    with pytest.raises(ValueError, match="supervisor payload bound"):
        nova_release_gates._supervisor_payload(
            command,
            deadline=time.monotonic() + 1,
        )

    assert time.monotonic() - started < 0.1


def test_launch_bootstrap_cap_is_shorter_than_long_caller_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    stalled_supervisor = "import time; time.sleep(2)"
    if os.name == "nt":
        monkeypatch.setattr(
            nova_release_gates,
            "_WINDOWS_LAUNCHER",
            stalled_supervisor,
        )
    else:
        monkeypatch.setattr(
            nova_release_gates,
            "_POSIX_SUPERVISOR",
            stalled_supervisor,
        )
    monkeypatch.setattr(
        nova_release_gates,
        "_SUPERVISOR_BOOTSTRAP_SECONDS",
        0.2,
        raising=False,
    )
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="payload|handshake"):
        _launch_contained_process(
            [sys.executable, "-c", "pass", "x" * 200_000],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 5,
        )

    assert time.monotonic() - started < 1


def test_gate_launch_setup_obeys_one_second_absolute_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    stalled_supervisor = "import time; time.sleep(2)"
    if os.name == "nt":
        monkeypatch.setattr(
            nova_release_gates,
            "_WINDOWS_LAUNCHER",
            stalled_supervisor,
        )
    else:
        monkeypatch.setattr(
            nova_release_gates,
            "_POSIX_SUPERVISOR",
            stalled_supervisor,
        )
    gate = GateDefinition(
        name="bounded-launch",
        argv=(sys.executable, "-c", "pass", "x" * 200_000),
        timeout_seconds=1,
    )
    started = time.monotonic()

    result = GateRunner(candidate, reports).run(gate)

    assert result.passed is False
    assert result.timed_out is True
    assert time.monotonic() - started < 1.6


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux cleanup proof")
def test_failed_posix_launch_reports_indeterminate_cleanup_and_reaps_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    supervisor_pid_path = candidate / "uncertain-supervisor.pid"
    delayed_supervisor = (
        "import os, pathlib, sys, time; sys.stdin.buffer.readline(); "
        f"pathlib.Path({str(supervisor_pid_path)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(nova_release_gates, "_POSIX_SUPERVISOR", delayed_supervisor)
    monkeypatch.setattr(
        nova_release_gates,
        "_SUPERVISOR_BOOTSTRAP_SECONDS",
        0.2,
        raising=False,
    )

    def indeterminate_scan(
        containment: object,
        deadline: float,
        **kwargs: object,
    ) -> object:
        return nova_release_gates._LinuxSessionScan((), False)

    monkeypatch.setattr(
        nova_release_gates._ProcessContainment,
        "_linux_session_members",
        indeterminate_scan,
    )

    result = GateRunner(candidate, reports).run(
        GateDefinition(
            name="uncertain-launch-cleanup",
            argv=(sys.executable, "-c", "pass"),
            timeout_seconds=2,
        )
    )

    assert result.passed is False
    assert result.timed_out is True
    assert "process containment cleanup could not be verified" in result.stderr_tail
    assert _wait_for_path(supervisor_pid_path)
    supervisor_pid = int(supervisor_pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(supervisor_pid)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux pipe proof")
def test_posix_blocked_payload_honors_deadline_and_reaps_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    supervisor_pid_path = candidate / "blocked-supervisor.pid"
    stalled_supervisor = (
        "import os, pathlib, time; "
        f"pathlib.Path({str(supervisor_pid_path)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(nova_release_gates, "_POSIX_SUPERVISOR", stalled_supervisor)
    before = len(list(Path("/proc/self/fd").iterdir()))
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="payload"):
        _launch_contained_process(
            [sys.executable, "-c", "pass", "x" * 200_000],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 0.2,
        )

    assert time.monotonic() - started < 1
    assert _wait_for_path(supervisor_pid_path)
    supervisor_pid = int(supervisor_pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(supervisor_pid)
    after = len(list(Path("/proc/self/fd").iterdir()))
    assert after <= before


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux handshake proof")
def test_posix_delayed_handshake_uses_only_remaining_caller_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, _ = _gate_paths(tmp_path)
    supervisor_pid_path = candidate / "delayed-supervisor.pid"
    delayed_supervisor = (
        "import os, pathlib, sys, time; sys.stdin.buffer.readline(); "
        f"pathlib.Path({str(supervisor_pid_path)!r}).write_text(str(os.getpid())); "
        "time.sleep(30)"
    )
    monkeypatch.setattr(nova_release_gates, "_POSIX_SUPERVISOR", delayed_supervisor)
    started = time.monotonic()

    with pytest.raises(TimeoutError, match="handshake"):
        _launch_contained_process(
            [sys.executable, "-c", "pass"],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 0.2,
        )

    assert time.monotonic() - started < 1
    assert _wait_for_path(supervisor_pid_path)
    supervisor_pid = int(supervisor_pid_path.read_text(encoding="utf-8"))
    assert _wait_for_process_exit(supervisor_pid)


@pytest.mark.skipif(
    os.name != "nt" and not sys.platform.startswith("linux"),
    reason="listener PID proof is implemented for Windows and Linux",
)
def test_listener_ownership_accepts_only_contained_listener(tmp_path: Path) -> None:
    candidate, _ = _gate_paths(tmp_path)
    port = _unused_loopback_port()
    listener_script = (
        "from http.server import HTTPServer, BaseHTTPRequestHandler; import sys; "
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), BaseHTTPRequestHandler).serve_forever()"
    )
    containment = _launch_contained_process(
        [sys.executable, "-c", listener_script, str(port)],
        cwd=candidate,
        environment=_sanitized_environment(candidate, os.environ),
        deadline=time.monotonic() + 5,
    )
    try:
        assert _wait_for_listener(port)
        owned, reason = _listener_owned_by_containment(port, containment)
        assert owned is True, reason
    finally:
        assert containment.terminate_and_verify()


@pytest.mark.skipif(
    os.name != "nt" and not sys.platform.startswith("linux"),
    reason="listener PID proof is implemented for Windows and Linux",
)
def test_listener_ownership_rejects_live_contained_competitor(tmp_path: Path) -> None:
    candidate, _ = _gate_paths(tmp_path)
    port = _unused_loopback_port()
    listener_script = (
        "from http.server import HTTPServer, BaseHTTPRequestHandler; import sys; "
        "HTTPServer(('127.0.0.1', int(sys.argv[1])), BaseHTTPRequestHandler).serve_forever()"
    )
    competitor = subprocess.Popen(
        [sys.executable, "-c", listener_script, str(port)],
        cwd=candidate,
        env=_sanitized_environment(candidate, os.environ),
        shell=False,
    )
    containment = None
    try:
        assert _wait_for_listener(port)
        containment = _launch_contained_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=candidate,
            environment=_sanitized_environment(candidate, os.environ),
            deadline=time.monotonic() + 5,
        )
        owned, reason = _listener_owned_by_containment(port, containment)
        assert owned is False
        assert "ownership" in reason
    finally:
        if containment is not None:
            assert containment.terminate_and_verify()
        competitor.terminate()
        try:
            competitor.wait(timeout=5)
        except subprocess.TimeoutExpired:
            competitor.kill()
            competitor.wait(timeout=5)


@pytest.mark.skipif(
    os.name != "nt" and not sys.platform.startswith("linux"),
    reason="connection PID proof is implemented for Windows and Linux",
)
def test_connection_ownership_rejects_handoff_after_valid_listener_sample(
    tmp_path: Path,
) -> None:
    import socket

    candidate, _ = _gate_paths(tmp_path)
    ready = candidate / "ready"
    released = candidate / "released"
    port = _unused_loopback_port()
    candidate_script = textwrap.dedent(
        f"""
        import pathlib, socket, time
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", {port}))
        listener.listen()
        pathlib.Path({str(ready)!r}).write_text("ready")
        connection, _ = listener.accept()
        connection.close()
        listener.close()
        pathlib.Path({str(released)!r}).write_text("released")
        time.sleep(30)
        """
    )
    containment = _launch_contained_process(
        [sys.executable, "-c", candidate_script],
        cwd=candidate,
        environment=_sanitized_environment(candidate, os.environ),
        deadline=time.monotonic() + 5,
    )
    competitor = None
    try:
        assert _wait_for_path(ready)
        sampled, reason = _listener_owned_by_containment(port, containment)
        assert sampled is True, reason
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
        assert _wait_for_path(released)
        competitor_script = (
            "from http.server import HTTPServer, BaseHTTPRequestHandler; import sys; "
            "HTTPServer(('127.0.0.1', int(sys.argv[1])), BaseHTTPRequestHandler).serve_forever()"
        )
        competitor = subprocess.Popen(
            [sys.executable, "-c", competitor_script, str(port)],
            cwd=candidate,
            shell=False,
        )
        assert _wait_for_listener(port)
        with socket.create_connection(("127.0.0.1", port), timeout=1) as connection:
            owned, reason = _connection_owned_by_containment(
                connection,
                containment,
                time.monotonic() + 2,
            )
        assert owned is False
        assert "connection ownership" in reason
    finally:
        assert containment.terminate_and_verify()
        if competitor is not None:
            competitor.terminate()
            try:
                competitor.wait(timeout=5)
            except subprocess.TimeoutExpired:
                competitor.kill()
                competitor.wait(timeout=5)


def test_linux_connection_resolver_rejects_oversized_tcp_table(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    tcp_table = proc_root / "net" / "tcp"
    tcp_table.parent.mkdir(parents=True)
    tcp_table.write_bytes(b"header\n" + b"x" * 1024)
    started = time.monotonic()

    owners = _linux_connection_owner_pids(
        ("127.0.0.1", 12345),
        ("127.0.0.1", 54321),
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_tcp_bytes=128,
    )

    assert owners is None
    assert time.monotonic() - started < 0.5


def test_linux_connection_resolver_caps_process_and_fd_enumeration(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    tcp_table = proc_root / "net" / "tcp"
    tcp_table.parent.mkdir(parents=True)
    tcp_table.write_text(
        "header\n"
        "0: 0100007F:3039 0100007F:D431 01 0 0 0 0 0 999\n",
        encoding="ascii",
    )
    for pid in ("1", "2", "3"):
        (proc_root / pid / "fd").mkdir(parents=True)

    process_capped = _linux_connection_owner_pids(
        ("127.0.0.1", 12345),
        ("127.0.0.1", 54321),
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_processes=2,
    )

    assert process_capped is None

    for index in range(3):
        (proc_root / "1" / "fd" / str(index)).write_text("fd", encoding="ascii")
    fd_capped = _linux_connection_owner_pids(
        ("127.0.0.1", 12345),
        ("127.0.0.1", 54321),
        time.monotonic() + 1,
        proc_root=proc_root,
        maximum_processes=4,
        maximum_fds_per_process=2,
    )

    assert fd_capped is None


def test_linux_connection_resolver_rejects_oversized_proc_component(
    tmp_path: Path,
) -> None:
    proc_root = tmp_path / "proc"
    tcp_table = proc_root / "net" / "tcp"
    tcp_table.parent.mkdir(parents=True)
    tcp_table.write_text(
        "header\n"
        "0: 0100007F:3039 0100007F:D431 01 0 0 0 0 0 999\n",
        encoding="ascii",
    )
    (proc_root / ("1" * 100) / "fd").mkdir(parents=True)

    owners = _linux_connection_owner_pids(
        ("127.0.0.1", 12345),
        ("127.0.0.1", 54321),
        time.monotonic() + 1,
        proc_root=proc_root,
    )

    assert owners is None


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


def test_safe_report_write_never_follows_directory_substitution(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    reports.mkdir()
    moved = tmp_path / "moved-reports"
    external = tmp_path / "external"
    external.mkdir()
    safe = _SafeReportDirectory(candidate, reports)

    def substitute_directory() -> None:
        os.replace(reports, moved)
        _make_directory_link(reports, external)

    safe._before_create_hook = substitute_directory
    try:
        with pytest.raises((OSError, ValueError)):
            safe.write_text("result.json", "must-not-escape")
        assert not (external / "result.json").exists()
        assert not any(external.iterdir())
    finally:
        safe.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows ancestor handle semantics")
def test_windows_report_write_pins_every_existing_ancestor(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    ancestor = tmp_path / "trusted-tree"
    reports = ancestor / "reports"
    reports.mkdir(parents=True)
    moved = tmp_path / "moved-tree"
    external = tmp_path / "external-tree"
    (external / "reports").mkdir(parents=True)
    safe = _SafeReportDirectory(candidate, reports)

    def substitute_ancestor() -> None:
        os.replace(ancestor, moved)
        _make_directory_link(ancestor, external)

    safe._before_create_hook = substitute_ancestor
    try:
        with pytest.raises((OSError, ValueError)):
            safe.write_text("result.json", "must-not-escape")
        assert not (external / "reports" / "result.json").exists()
    finally:
        safe.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows retained-handle identity")
def test_windows_pinned_identity_is_queried_from_retained_handle(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    reports.mkdir()
    safe = _SafeReportDirectory(candidate, reports)
    try:
        observed = safe._pinned_identity()
        safe._identity = (-1, -1)
        assert safe._pinned_identity() == observed
    finally:
        safe.close()


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
    assert by_name["sbom"].artifact_paths == (
        str(reports / "nova-sbom.json"),
    )
    assert by_name["conversation_560"].artifact_paths == (
        str(reports / "conversation-560.json"),
    )


@pytest.mark.parametrize(
    ("gate_name", "artifact_name"),
    [("sbom", "nova-sbom.json"), ("conversation_560", "conversation-560.json")],
)
def test_default_artifact_gate_rejects_redirect_before_launch(
    tmp_path: Path,
    gate_name: str,
    artifact_name: str,
) -> None:
    candidate, reports = _gate_paths(tmp_path)
    reports.mkdir()
    _make_directory_link(
        reports / artifact_name,
        tmp_path / f"redirect-{artifact_name}",
    )
    marker = candidate / "gate-started"
    gate = next(
        item
        for item in default_gate_definitions(candidate, reports)
        if item.name == gate_name
    )
    gate = replace(
        gate,
        argv=(
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(marker)!r}).write_text('yes')",
        ),
    )

    with pytest.raises(ValueError, match="artifact|link|reparse"):
        GateRunner(candidate, reports).run(gate)

    assert not marker.exists()


def test_gate_artifact_must_retain_reserved_identity_and_content(tmp_path: Path) -> None:
    candidate, reports = _gate_paths(tmp_path)
    reports.mkdir()
    artifact = reports / "result.json"
    success = GateDefinition(
        name="artifact-success",
        argv=(
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(artifact)!r}).write_text('{{}}')",
        ),
        timeout_seconds=5,
        artifact_paths=(str(artifact),),
    )

    result = GateRunner(candidate, reports).run(success)

    assert result.passed is True
    assert artifact.read_text(encoding="utf-8") == "{}"

    artifact.unlink()
    replacement = GateDefinition(
        name="artifact-replacement",
        argv=(
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                f"p=Path({str(artifact)!r}); p.unlink(); p.write_text('replacement')"
            ),
        ),
        timeout_seconds=5,
        artifact_paths=(str(artifact),),
    )

    replaced = GateRunner(candidate, reports).run(replacement)

    assert replaced.passed is False
    assert "artifact output could not be verified" in replaced.stderr_tail


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
            paths = (
                "/healthz",
                "/status",
                "/api/reliability/status",
                "/api/desktop/status",
                "/assets/nova_foundation_ui.js",
                "/assets/nova_foundation_ui.css",
                "/manifest.webmanifest",
                "/service-worker.js",
                "/recovery",
            )
            payload = None
            for index, path in enumerate(paths):
                with urlopen(args.url + path, timeout=2) as response:
                    content = response.read()
                if index == 0:
                    payload = json.loads(content.decode("utf-8"))
            if payload.get("ok") is not True:
                raise SystemExit(1)
            print("PROBE_OK")
            """
        ),
        encoding="utf-8",
    )


def _write_raw_socket_smoke_probe(candidate: Path, request_template: str) -> None:
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            f"""
            import argparse
            import socket
            from urllib.parse import urlsplit

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            parsed = urlsplit(args.url)
            request = {request_template!r}.format(port=parsed.port).encode("ascii")
            with socket.create_connection((parsed.hostname, parsed.port), timeout=2) as connection:
                connection.sendall(request)
                connection.settimeout(2)
                while connection.recv(65536):
                    pass
            print("RAW_PROBE_DONE")
            """
        ),
        encoding="utf-8",
    )


def _write_proxy_policy_server(candidate: Path, marker: Path) -> None:
    _write_fake_smoke_candidate(
        candidate,
        f"""
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import pathlib
        import sys

        marker = pathlib.Path({str(marker)!r})

        class Handler(BaseHTTPRequestHandler):
            def _respond(self):
                body = json.dumps({{"ok": True}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.headers.get("User-Agent"):
                    marker.write_text("proxied")
                self._respond()

            def do_POST(self):
                marker.write_text("proxied")
                length = int(self.headers.get("Content-Length", "0"))
                if length:
                    self.rfile.read(length)
                self._respond()

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux handshake proof")
def test_clean_start_smoke_launch_setup_obeys_one_second_absolute_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(candidate, "raise SystemExit(99)")
    delayed_supervisor = (
        "import sys, time; sys.stdin.buffer.readline(); time.sleep(30)"
    )
    monkeypatch.setattr(nova_release_gates, "_POSIX_SUPERVISOR", delayed_supervisor)
    started = time.monotonic()

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=1,
    )

    assert result.passed is False
    assert result.timed_out is True
    assert time.monotonic() - started < 1.6


def test_clean_start_proxy_rejects_unrelated_local_client_before_upstream(
    tmp_path: Path,
) -> None:
    import socket
    import threading

    candidate = tmp_path / "candidate"
    candidate.mkdir()
    upstream_marker = candidate / "proxied-request"
    _write_proxy_policy_server(candidate, upstream_marker)
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            """
            import argparse
            import pathlib
            import time
            from urllib.parse import urlsplit

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            parsed = urlsplit(args.url)
            pathlib.Path("proxy-port").write_text(str(parsed.port))
            deadline = time.monotonic() + 5
            while not pathlib.Path("release-probe").exists():
                if time.monotonic() >= deadline:
                    raise SystemExit(3)
                time.sleep(0.01)
            """
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "reports" / "smoke.json"
    observed: dict[str, object] = {}

    def run_smoke() -> None:
        try:
            observed["result"] = run_clean_start_smoke(
                candidate,
                report_path,
                timeout_seconds=8,
            )
        except BaseException as error:
            observed["error"] = error

    worker = threading.Thread(target=run_smoke)
    worker.start()
    proxy_port_path = candidate / "proxy-port"
    try:
        assert _wait_for_path(proxy_port_path)
        proxy_port = int(proxy_port_path.read_text(encoding="utf-8"))
        request = (
            f"GET /healthz HTTP/1.1\r\n"
            f"Accept-Encoding: identity\r\n"
            f"Host: 127.0.0.1:{proxy_port}\r\n"
            f"User-Agent: Python-urllib/3.11\r\n"
            f"Connection: close\r\n\r\n"
        ).encode("ascii")
        with socket.create_connection(("127.0.0.1", proxy_port), timeout=2) as client:
            client.sendall(request)
            client.settimeout(2)
            try:
                while client.recv(65_536):
                    pass
            except (ConnectionAbortedError, ConnectionResetError):
                pass
    finally:
        (candidate / "release-probe").write_text("release", encoding="ascii")
        worker.join(timeout=10)

    assert worker.is_alive() is False
    if "error" in observed:
        raise observed["error"]  # type: ignore[misc]
    result = observed["result"]
    assert isinstance(result, nova_release_gates.GateResult)
    assert result.passed is False
    assert not upstream_marker.exists()


@pytest.mark.parametrize(
    "request_template",
    [
        (
            "POST /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n"
            "Content-Length: 4\r\n\r\nPWN!"
        ),
        (
            "GET /not-a-smoke-path HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n\r\n"
        ),
        (
            "GET /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n"
            "X-Not-Used-By-Smoke: value\r\n\r\n"
        ),
        (
            "GET /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n\r\n"
        ),
        (
            "GET /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n"
            "Transfer-Encoding: chunked\r\n\r\n4\r\nPWN!\r\n0\r\n\r\n"
        ),
        (
            "GET /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n\r\n"
            "GET /status HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n\r\n"
        ),
        "GET /healthz HTTP/1.1\r\nMalformed-Header\r\n\r\n",
        (
            "GET /healthz HTTP/1.1\r\n"
            "Accept-Encoding: identity\r\n"
            "Host: 127.0.0.1:{port}\r\n"
            "User-Agent: Python-urllib/3.11\r\n"
            "Connection: close\r\n"
            "X-Padding: " + "x" * 17_000 + "\r\n\r\n"
        ),
    ],
    ids=(
        "post-body",
        "unknown-path",
        "unknown-header",
        "duplicate-host",
        "chunked-body",
        "pipelined-request",
        "malformed-request",
        "oversized-request",
    ),
)
def test_clean_start_proxy_rejects_unapproved_http_before_upstream(
    tmp_path: Path,
    request_template: str,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    upstream_marker = candidate / "proxied-request"
    _write_proxy_policy_server(candidate, upstream_marker)
    _write_raw_socket_smoke_probe(candidate, request_template)

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=5,
    )

    assert result.passed is False
    assert not upstream_marker.exists()


@pytest.mark.parametrize(
    "paths",
    [
        ("/healthz",),
        ("/healthz", "/healthz"),
    ],
    ids=("incomplete", "duplicate"),
)
def test_clean_start_proxy_requires_exact_nine_path_probe_sequence(
    tmp_path: Path,
    paths: tuple[str, ...],
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_proxy_policy_server(candidate, candidate / "proxied-request")
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            f"""
            import argparse
            from urllib.request import Request, urlopen

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            for path in {paths!r}:
                request = Request(args.url + path, method="GET")
                with urlopen(request, timeout=2) as response:
                    response.read()
            """
        ),
        encoding="utf-8",
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=5,
    )

    assert result.passed is False
    assert "exact smoke request sequence" in result.stderr_tail


def test_clean_start_proxy_caps_total_accepted_connections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_proxy_policy_server(candidate, candidate / "proxied-request")
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            """
            import argparse
            from urllib.request import urlopen

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            paths = ("/healthz", "/status", "/api/reliability/status")
            for path in paths:
                with urlopen(args.url + path, timeout=2) as response:
                    response.read()
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        nova_release_gates,
        "_MAX_PROXY_CONNECTIONS",
        2,
        raising=False,
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=5,
    )

    assert result.passed is False
    assert "probe proxy exceeded connection limit" in result.stderr_tail


def test_clean_start_proxy_caps_aggregate_relayed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
                body = json.dumps({"ok": True, "padding": "x" * 256}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            """
            import argparse
            from urllib.request import urlopen

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            paths = ("/healthz", "/status")
            for path in paths:
                with urlopen(args.url + path, timeout=2) as response:
                    response.read()
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        nova_release_gates,
        "_MAX_PROXY_TOTAL_BYTES",
        750,
        raising=False,
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=5,
    )

    assert result.passed is False
    assert "probe proxy exceeded aggregate transfer byte limit" in result.stderr_tail


def test_clean_start_proxy_allows_exact_contained_read_only_probe_paths(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    request_log = candidate / "request-paths.log"
    allowed_paths = (
        "/healthz",
        "/status",
        "/api/reliability/status",
        "/api/desktop/status",
        "/assets/nova_foundation_ui.js",
        "/assets/nova_foundation_ui.css",
        "/manifest.webmanifest",
        "/service-worker.js",
        "/recovery",
    )
    _write_fake_smoke_candidate(
        candidate,
        f"""
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import pathlib
        import sys

        request_log = pathlib.Path({str(request_log)!r})

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                with request_log.open("a", encoding="utf-8") as stream:
                    stream.write(self.path + "\\n")
                body = json.dumps({{"ok": True}}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    (candidate / "tools" / "nova_smoke_check.py").write_text(
        textwrap.dedent(
            f"""
            import argparse
            from urllib.request import Request, urlopen

            parser = argparse.ArgumentParser()
            parser.add_argument("--url", required=True)
            args = parser.parse_args()
            for path in {allowed_paths!r}:
                request = Request(args.url + path, method="GET")
                with urlopen(request, timeout=2) as response:
                    response.read()
            print("FULL_PROBE_OK")
            """
        ),
        encoding="utf-8",
    )

    result = run_clean_start_smoke(
        candidate,
        tmp_path / "reports" / "smoke.json",
        timeout_seconds=10,
    )

    assert result.passed is True
    assert "FULL_PROBE_OK" in result.stdout_tail
    assert request_log.read_text(encoding="utf-8").splitlines() == [
        "/healthz",
        "/healthz",
        "/status",
        "/api/reliability/status",
        "/api/desktop/status",
        "/assets/nova_foundation_ui.js",
        "/assets/nova_foundation_ui.css",
        "/manifest.webmanifest",
        "/service-worker.js",
        "/recovery",
    ]


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


def test_clean_start_smoke_persisted_log_honors_exact_byte_cap(tmp_path: Path) -> None:
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    _write_fake_smoke_candidate(
        candidate,
        r"""
        import json
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        import sys

        sys.stdout.buffer.write(b"x" * 65530 + b"\xff" + b"\xf0\x9f\x92\xa5END")
        sys.stdout.buffer.flush()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"ok": True}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
        """,
    )
    report_path = tmp_path / "reports" / "smoke.json"

    result = run_clean_start_smoke(candidate, report_path, timeout_seconds=5)

    assert result.passed is True
    report = json.loads(report_path.read_text(encoding="utf-8"))
    persisted = report_path.parent / report["server_stdout_file"]
    raw = persisted.read_bytes()
    assert len(raw) <= 65_536
    assert raw.decode("utf-8").endswith("💥END")


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


def test_release_smoke_cli_sanitizes_unsafe_report_path_error(tmp_path: Path) -> None:
    candidate = tmp_path / "private candidate"
    candidate.mkdir()
    report_path = candidate / "private reports" / "smoke.json"
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
        ],
        cwd=repository_root,
        capture_output=True,
        text=True,
        timeout=5,
        shell=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "Traceback" not in completed.stderr
    assert str(candidate) not in completed.stderr
    assert str(report_path) not in completed.stderr
    assert len(completed.stderr.encode("utf-8")) <= 4096
    error = json.loads(completed.stderr)
    assert error == {"error": "release smoke setup failed"}
