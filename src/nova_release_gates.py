"""Bounded, sanitized subprocess verification for Nova release candidates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Iterable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from nova_release_security import SECRET_PATTERNS


_ENVIRONMENT_ALLOWLIST = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "PATHEXT",
    "COMSPEC",
    "HOME",
    "USERPROFILE",
    "LOCALAPPDATA",
    "APPDATA",
)
_AUTHORIZATION_PATTERN = re.compile(
    r"(?im)(\bauthorization\s*:\s*)[^\r\n]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
_PRIVATE_RECORD_PATTERN = re.compile(
    r"(?im)([\"']?(?:prompt|response|memory(?:_contents?)?|database_rows?|db_rows?)"
    r"[\"']?\s*[:=]\s*)[^\r\n]+"
)


@dataclass(frozen=True)
class GateDefinition:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int
    required: bool = True


@dataclass
class GateResult:
    name: str
    command: list[str]
    passed: bool
    exit_code: int | None
    duration_seconds: float
    timed_out: bool
    stdout_tail: str
    stderr_tail: str


class _BoundedTail:
    def __init__(self, maximum_bytes: int) -> None:
        self._maximum_bytes = maximum_bytes
        self._content = bytearray()

    def append(self, content: bytes) -> None:
        self._content.extend(content)
        excess = len(self._content) - self._maximum_bytes
        if excess > 0:
            del self._content[:excess]

    def decode(self) -> str:
        return bytes(self._content).decode("utf-8", errors="replace").strip()


def redact_gate_output(
    output: str,
    *,
    sensitive_paths: Iterable[str | Path] = (),
) -> str:
    """Remove secrets, private records, and candidate-local absolute paths."""

    redacted = output
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    redacted = _PRIVATE_RECORD_PATTERN.sub(r"\1[REDACTED]", redacted)
    path_variants: set[str] = set()
    for path_value in sensitive_paths:
        value = str(path_value)
        if not value:
            continue
        path_variants.update({value, value.replace("\\", "/"), value.replace("/", "\\")})
    flags = re.IGNORECASE if os.name == "nt" else 0
    for value in sorted(path_variants, key=len, reverse=True):
        if len(value) > 2:
            redacted = re.sub(re.escape(value), "[REDACTED]", redacted, flags=flags)
    return redacted


def _sanitized_environment(
    candidate_root: Path,
    base_environment: Mapping[str, str] | None,
) -> dict[str, str]:
    source = dict(os.environ if base_environment is None else base_environment)
    by_upper_name = {name.upper(): value for name, value in source.items()}
    environment = {
        name: by_upper_name[name]
        for name in _ENVIRONMENT_ALLOWLIST
        if name in by_upper_name and by_upper_name[name]
    }
    environment.update(
        {
            "PYTHONPATH": str(candidate_root / "src"),
            "NOVA_MODEL_WARMUP": "false",
            "NOVA_REVIEWER_WARMUP": "false",
            "NOVA_ENABLE_REMOTE_ACCESS": "false",
            "NOVA_ALLOW_REMOTE_MODELS": "false",
            "NOVA_COMPANION_ENABLED": "true",
            "NOVA_COMPANION_DEFAULT": "false",
        }
    )
    return environment


def _drain_stream(stream: object, tail: _BoundedTail) -> None:
    try:
        while True:
            content = stream.read(8192)  # type: ignore[attr-defined]
            if not content:
                return
            tail.append(content)
    finally:
        stream.close()  # type: ignore[attr-defined]


def _popen_group_options() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
        taskkill = str(Path(system_root) / "System32" / "taskkill.exe")
        try:
            subprocess.run(
                [taskkill, "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                shell=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except ProcessLookupError:
            return
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class GateRunner:
    def __init__(
        self,
        candidate_root: str | Path,
        report_dir: str | Path,
        *,
        base_environment: Mapping[str, str] | None = None,
        max_output_bytes: int = 65_536,
    ) -> None:
        if max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        self.candidate_root = Path(candidate_root).resolve()
        self.report_dir = Path(report_dir).resolve()
        self.base_environment = base_environment
        self.max_output_bytes = max_output_bytes

    def run(self, gate: GateDefinition) -> GateResult:
        started = time.monotonic()
        command = list(gate.argv)
        stdout_tail = _BoundedTail(self.max_output_bytes)
        stderr_tail = _BoundedTail(self.max_output_bytes)
        timed_out = False
        process: subprocess.Popen[bytes] | None = None
        threads: list[threading.Thread] = []
        try:
            process = subprocess.Popen(
                command,
                cwd=self.candidate_root,
                env=_sanitized_environment(
                    self.candidate_root,
                    self.base_environment,
                ),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                **_popen_group_options(),
            )
            assert process.stdout is not None
            assert process.stderr is not None
            threads = [
                threading.Thread(
                    target=_drain_stream,
                    args=(process.stdout, stdout_tail),
                ),
                threading.Thread(
                    target=_drain_stream,
                    args=(process.stderr, stderr_tail),
                ),
            ]
            for thread in threads:
                thread.start()
            try:
                process.wait(timeout=gate.timeout_seconds)
            except subprocess.TimeoutExpired:
                timed_out = True
                _terminate_process_tree(process)
        except OSError as error:
            stderr_tail.append(str(error).encode("utf-8", errors="replace"))
        finally:
            if process is not None and process.poll() is None:
                _terminate_process_tree(process)
            for thread in threads:
                thread.join(timeout=10)

        duration = time.monotonic() - started
        exit_code = process.returncode if process is not None else None
        sensitive_paths = (self.candidate_root, self.report_dir)
        stdout = redact_gate_output(
            stdout_tail.decode(),
            sensitive_paths=sensitive_paths,
        )
        stderr = redact_gate_output(
            stderr_tail.decode(),
            sensitive_paths=sensitive_paths,
        )
        return GateResult(
            name=gate.name,
            command=command,
            passed=not timed_out and exit_code == 0,
            exit_code=exit_code,
            duration_seconds=duration,
            timed_out=timed_out,
            stdout_tail=stdout,
            stderr_tail=stderr,
        )


def default_gate_definitions(
    candidate_root: str | Path,
    run_report_dir: str | Path,
    *,
    python_executable: str = sys.executable,
) -> list[GateDefinition]:
    """Return the required, ordered release verification gates."""

    candidate = Path(candidate_root).resolve()
    reports = Path(run_report_dir).resolve()
    return [
        GateDefinition(
            name="release_focused",
            argv=(
                python_executable,
                "-m",
                "pytest",
                "tests/test_nova_release_policy.py",
                "tests/test_nova_release_security.py",
                "tests/test_nova_release_manifest.py",
                "tests/test_nova_release_worktree.py",
                "tests/test_nova_release_gates.py",
                "tests/test_nova_release_lock.py",
                "-q",
            ),
            timeout_seconds=900,
        ),
        GateDefinition(
            name="dependency_lock",
            argv=(
                python_executable,
                "-m",
                "nova_release_security",
                "verify-lock",
                "requirements-runtime.lock",
            ),
            timeout_seconds=120,
        ),
        GateDefinition(
            name="sbom",
            argv=(
                python_executable,
                "-m",
                "nova_release_security",
                "sbom",
                str(reports / "nova-sbom.json"),
            ),
            timeout_seconds=120,
        ),
        GateDefinition(
            name="javascript",
            argv=(
                python_executable,
                "-m",
                "pytest",
                "tests/test_nova_companion_javascript.py",
                "-q",
            ),
            timeout_seconds=300,
        ),
        GateDefinition(
            name="application_acceptance",
            argv=(
                python_executable,
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
            ),
            timeout_seconds=900,
        ),
        GateDefinition(
            name="python_full",
            argv=(python_executable, "-m", "pytest", "-q"),
            timeout_seconds=3_600,
        ),
        GateDefinition(
            name="conversation_560",
            argv=(
                python_executable,
                "tools/run_conversation_eval.py",
                "--pack",
                "data/evals/nova_conversation_variations_v1.json",
                "--output",
                str(reports / "conversation-560.json"),
            ),
            timeout_seconds=1_800,
        ),
        GateDefinition(
            name="clean_start_smoke",
            argv=(
                python_executable,
                "tools/nova_release_smoke.py",
                "--root",
                str(candidate),
                "--report",
                str(reports / "smoke.json"),
            ),
            timeout_seconds=120,
        ),
    ]


def _unused_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _health_is_ready(base_url: str, deadline: float) -> bool:
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            with urlopen(
                base_url + "/healthz",
                timeout=min(0.25, max(0.05, remaining)),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if response.status == 200 and payload.get("ok") is True:
                return True
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
            pass
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    return False


def _write_bounded_log(path: Path, content: str) -> None:
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def run_clean_start_smoke(
    candidate_root: str | Path,
    report_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> GateResult:
    """Start, probe, report, and terminate one isolated candidate server."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    candidate = Path(candidate_root).resolve()
    destination = Path(report_path).resolve()
    if destination == candidate or candidate in destination.parents:
        raise ValueError("smoke report must be outside the release candidate")
    destination.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    deadline = started + timeout_seconds
    port = _unused_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    server_command = [sys.executable, "nova_enhanced_server.py", str(port)]
    probe_command = [
        sys.executable,
        "tools/nova_smoke_check.py",
        "--url",
        base_url,
    ]
    server_stdout = _BoundedTail(65_536)
    server_stderr = _BoundedTail(65_536)
    server: subprocess.Popen[bytes] | None = None
    server_threads: list[threading.Thread] = []
    startup_healthy = False
    probe_result: GateResult | None = None
    timed_out = False
    launch_error = ""
    cleanup_complete = False

    try:
        server = subprocess.Popen(
            server_command,
            cwd=candidate,
            env=_sanitized_environment(candidate, None),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **_popen_group_options(),
        )
        assert server.stdout is not None
        assert server.stderr is not None
        server_threads = [
            threading.Thread(
                target=_drain_stream,
                args=(server.stdout, server_stdout),
            ),
            threading.Thread(
                target=_drain_stream,
                args=(server.stderr, server_stderr),
            ),
        ]
        for thread in server_threads:
            thread.start()

        while server.poll() is None and time.monotonic() < deadline:
            if _health_is_ready(
                base_url,
                min(deadline, time.monotonic() + 0.25),
            ):
                startup_healthy = True
                break
        if not startup_healthy and server.poll() is None:
            timed_out = time.monotonic() >= deadline
        if startup_healthy:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
            else:
                probe_result = GateRunner(
                    candidate,
                    destination.parent,
                ).run(
                    GateDefinition(
                        name="clean_start_probe",
                        argv=tuple(probe_command),
                        timeout_seconds=max(1, int(remaining)),
                    )
                )
                timed_out = probe_result.timed_out
    except OSError as error:
        launch_error = str(error)
    finally:
        if server is not None and server.poll() is None:
            _terminate_process_tree(server)
        if server is not None:
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _terminate_process_tree(server)
            cleanup_complete = server.poll() is not None
        for thread in server_threads:
            thread.join(timeout=10)

    sensitive_paths = (candidate, destination.parent)
    recorded_server_stdout = redact_gate_output(
        server_stdout.decode(),
        sensitive_paths=sensitive_paths,
    )
    recorded_server_stderr = redact_gate_output(
        server_stderr.decode(),
        sensitive_paths=sensitive_paths,
    )
    stdout = probe_result.stdout_tail if probe_result is not None else ""
    stderr_parts = [
        probe_result.stderr_tail if probe_result is not None else "",
        recorded_server_stderr,
        launch_error,
    ]
    stderr = redact_gate_output(
        "\n".join(part for part in stderr_parts if part),
        sensitive_paths=sensitive_paths,
    )
    probe_passed = probe_result is not None and probe_result.passed
    if probe_result is not None:
        exit_code = probe_result.exit_code
    elif server is not None:
        exit_code = server.returncode
    else:
        exit_code = None
    result = GateResult(
        name="clean_start_smoke",
        command=probe_command if startup_healthy else server_command,
        passed=startup_healthy and probe_passed and cleanup_complete,
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        stdout_tail=stdout,
        stderr_tail=stderr,
    )

    stdout_file = destination.with_name(
        destination.stem + ".server.stdout.log"
    )
    stderr_file = destination.with_name(
        destination.stem + ".server.stderr.log"
    )
    _write_bounded_log(stdout_file, recorded_server_stdout)
    _write_bounded_log(stderr_file, recorded_server_stderr)
    payload = asdict(result)
    payload.update(
        {
            "startup_healthy": startup_healthy,
            "probe_passed": probe_passed,
            "cleanup_complete": cleanup_complete,
            "server_pid": server.pid if server is not None else None,
            "port": port,
            "server_stdout_file": stdout_file.name,
            "server_stderr_file": stderr_file.name,
        }
    )
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result
