"""Bounded, sanitized subprocess verification for Nova release candidates."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterable, Mapping

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
_PRIVATE_RECORD_MARKER = re.compile(
    r"(?im)(?:^|[{,])\s*[\"']?(?:prompt|response|memory(?:_contents?)?|"
    r"database_rows?|db_rows?)[\"']?\s*[:=]"
)
_WINDOWS_LAUNCHER = (
    "import json, subprocess, sys; "
    "payload = json.loads(sys.stdin.buffer.readline()); "
    "child = subprocess.Popen(payload['argv'], shell=False, "
    "stdin=subprocess.DEVNULL); "
    "raise SystemExit(child.wait())"
)
_MAX_HEALTH_HEADER_BYTES = 16_384
_MAX_HEALTH_BODY_BYTES = 65_536


class _HealthResponseRejected(Exception):
    pass


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
    def __init__(
        self,
        maximum_bytes: int,
        *,
        sensitive_paths: Iterable[str | Path] = (),
    ) -> None:
        self._maximum_bytes = maximum_bytes
        self._content = bytearray()
        self._inspection = bytearray()
        self._sensitive_paths = tuple(sensitive_paths)
        self._sensitive = False

    def append(self, content: bytes) -> None:
        if not self._sensitive:
            self._inspection.extend(content)
            inspected = self._inspection.decode("utf-8", errors="replace")
            if redact_gate_output(
                inspected,
                sensitive_paths=self._sensitive_paths,
            ) != inspected:
                self._sensitive = True
            if len(self._inspection) > 4096:
                del self._inspection[:-4096]
        self._content.extend(content)
        excess = len(self._content) - self._maximum_bytes
        if excess > 0:
            del self._content[:excess]

    def decode(self) -> str:
        if self._sensitive:
            return "[REDACTED]"
        return bytes(self._content).decode("utf-8", errors="replace").strip()


def redact_gate_output(
    output: str,
    *,
    sensitive_paths: Iterable[str | Path] = (),
) -> str:
    """Remove secrets, private records, and candidate-local absolute paths."""

    if _PRIVATE_RECORD_MARKER.search(output):
        return "[REDACTED]"
    redacted = output
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    redacted = _AUTHORIZATION_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = _BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    path_variants: set[str] = set()
    for path_value in sensitive_paths:
        value = str(path_value)
        if not value:
            continue
        slash_variants = {
            value,
            value.replace("\\", "/"),
            value.replace("/", "\\"),
        }
        path_variants.update(slash_variants)
        path_variants.update(
            json.dumps(variant, ensure_ascii=True)[1:-1]
            for variant in slash_variants
        )
    flags = re.IGNORECASE if os.name == "nt" else 0
    for value in sorted(path_variants, key=len, reverse=True):
        if len(value) > 2:
            redacted = re.sub(re.escape(value), "[REDACTED]", redacted, flags=flags)
    return redacted


def _valid_utf8_suffix(output: str, maximum_bytes: int) -> str:
    encoded = output.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return output
    suffix = encoded[-maximum_bytes:]
    while suffix:
        try:
            return suffix.decode("utf-8")
        except UnicodeDecodeError as error:
            if error.start != 0:
                return ""
            suffix = suffix[max(1, error.end) :]
    return ""


def _record_output(
    output: str,
    *,
    maximum_bytes: int,
    sensitive_paths: Iterable[str | Path],
) -> str:
    redacted = redact_gate_output(output, sensitive_paths=sensitive_paths)
    return _valid_utf8_suffix(redacted, maximum_bytes)


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


def _absolute_lexical_path(path: str | Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _is_link_or_reparse(path: Path) -> bool:
    entry_stat = os.lstat(path)
    attributes = getattr(entry_stat, "st_file_attributes", 0)
    reparse_point = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return stat.S_ISLNK(entry_stat.st_mode) or bool(attributes & reparse_point)


def _validate_existing_components(path: Path) -> None:
    current = Path(path.anchor)
    components = path.parts[1:] if path.anchor else path.parts
    if current and os.path.lexists(current) and _is_link_or_reparse(current):
        raise ValueError(f"output path contains a link or reparse point: {current}")
    for component in components:
        current /= component
        if not os.path.lexists(current):
            break
        if _is_link_or_reparse(current):
            raise ValueError(
                f"output path contains a link or reparse point: {current}"
            )


def _create_directory_without_links(path: Path) -> None:
    missing: list[Path] = []
    current = path
    while not os.path.lexists(current):
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for directory in reversed(missing):
        os.mkdir(directory)
        if _is_link_or_reparse(directory):
            raise ValueError(
                f"created report directory became a link or reparse point: {directory}"
            )


class _SafeReportDirectory:
    def __init__(self, candidate_root: Path, report_dir: str | Path) -> None:
        self.candidate_root = candidate_root.resolve()
        self.path = _absolute_lexical_path(report_dir)
        if self.path == self.candidate_root or self.candidate_root in self.path.parents:
            raise ValueError("run-report directory must be outside the candidate")
        _validate_existing_components(self.path)
        _create_directory_without_links(self.path)
        _validate_existing_components(self.path)
        if not self.path.is_dir():
            raise NotADirectoryError(self.path)
        self.physical_path = self.path.resolve(strict=True)
        if (
            self.physical_path == self.candidate_root
            or self.candidate_root in self.physical_path.parents
        ):
            raise ValueError("run-report directory must be outside the candidate")
        self._identity = self._directory_identity()

    def _directory_identity(self) -> tuple[int, int]:
        directory_stat = os.stat(self.path, follow_symlinks=False)
        return (directory_stat.st_dev, directory_stat.st_ino)

    def verify(self) -> None:
        _validate_existing_components(self.path)
        if self._directory_identity() != self._identity:
            raise ValueError("run-report directory identity changed")
        if self.path.resolve(strict=True) != self.physical_path:
            raise ValueError("run-report directory physical location changed")

    def output_path(self, filename: str) -> Path:
        if not filename or Path(filename).name != filename:
            raise ValueError("report output must be a direct filename")
        return self.path / filename

    def validate_output(self, filename: str) -> Path:
        self.verify()
        destination = self.output_path(filename)
        if os.path.lexists(destination):
            if _is_link_or_reparse(destination):
                raise ValueError(
                    f"report output is a link or reparse point: {destination}"
                )
            if not destination.is_file():
                raise ValueError(f"report output is not a regular file: {destination}")
        return destination

    def write_text(self, filename: str, content: str) -> Path:
        destination = self.validate_output(filename)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path,
            prefix=f".{filename}.",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            if _is_link_or_reparse(temporary):
                raise ValueError("exclusive report temporary became a link or reparse point")
            temporary_stat = os.fstat(descriptor)
            temporary_identity = (temporary_stat.st_dev, temporary_stat.st_ino)
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                descriptor = -1
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self.verify()
            self.validate_output(filename)
            current_temporary_stat = os.stat(temporary, follow_symlinks=False)
            if (
                current_temporary_stat.st_dev,
                current_temporary_stat.st_ino,
            ) != temporary_identity:
                raise ValueError("exclusive report temporary identity changed")
            os.replace(temporary, destination)
            self.verify()
            final_stat = os.stat(destination, follow_symlinks=False)
            if (
                _is_link_or_reparse(destination)
                or not stat.S_ISREG(final_stat.st_mode)
                or (final_stat.st_dev, final_stat.st_ino) != temporary_identity
            ):
                raise ValueError("final report output failed identity validation")
            return destination
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if os.path.lexists(temporary):
                temporary.unlink()


def _drain_stream(stream: object, tail: _BoundedTail) -> None:
    try:
        while True:
            content = stream.read(8192)  # type: ignore[attr-defined]
            if not content:
                return
            tail.append(content)
    finally:
        try:
            stream.close()  # type: ignore[attr-defined]
        except OSError:
            pass


class _WindowsJob:
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION = 1

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    class _BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _ExtendedLimitInformation(ctypes.Structure):
        pass

    class _BasicAccountingInformation(ctypes.Structure):
        _fields_ = [
            ("TotalUserTime", ctypes.c_longlong),
            ("TotalKernelTime", ctypes.c_longlong),
            ("ThisPeriodTotalUserTime", ctypes.c_longlong),
            ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
            ("TotalPageFaultCount", wintypes.DWORD),
            ("TotalProcesses", wintypes.DWORD),
            ("ActiveProcesses", wintypes.DWORD),
            ("TotalTerminatedProcesses", wintypes.DWORD),
        ]

    def __init__(self) -> None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32 = kernel32
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel32.TerminateJobObject.restype = wintypes.BOOL
        kernel32.QueryInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryInformationJobObject.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise ctypes.WinError(ctypes.get_last_error())
        information = self._ExtendedLimitInformation()
        information.BasicLimitInformation.LimitFlags = (
            self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        configured = kernel32.SetInformationJobObject(
            self._handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
        )
        if not configured:
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        assigned = self._kernel32.AssignProcessToJobObject(
            self._handle,
            wintypes.HANDLE(int(process._handle)),  # type: ignore[attr-defined]
        )
        if not assigned:
            raise ctypes.WinError(ctypes.get_last_error())

    def _active_processes(self) -> int:
        information = self._BasicAccountingInformation()
        returned = wintypes.DWORD()
        queried = self._kernel32.QueryInformationJobObject(
            self._handle,
            self._JOB_OBJECT_BASIC_ACCOUNTING_INFORMATION,
            ctypes.byref(information),
            ctypes.sizeof(information),
            ctypes.byref(returned),
        )
        if not queried:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(information.ActiveProcesses)

    def terminate_and_verify(self) -> bool:
        verified = False
        try:
            active = self._active_processes()
            if active and not self._kernel32.TerminateJobObject(self._handle, 1):
                return False
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if self._active_processes() == 0:
                    verified = True
                    break
                time.sleep(0.05)
            return verified
        except OSError:
            return False
        finally:
            self.close()

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle:
            self._kernel32.CloseHandle(handle)
            self._handle = None


_WindowsJob._ExtendedLimitInformation._fields_ = [
    ("BasicLimitInformation", _WindowsJob._BasicLimitInformation),
    ("IoInfo", _WindowsJob._IoCounters),
    ("ProcessMemoryLimit", ctypes.c_size_t),
    ("JobMemoryLimit", ctypes.c_size_t),
    ("PeakProcessMemoryUsed", ctypes.c_size_t),
    ("PeakJobMemoryUsed", ctypes.c_size_t),
]


class _ProcessContainment:
    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        process_group_id: int | None = None,
        windows_job: _WindowsJob | None = None,
    ) -> None:
        self.process = process
        self.process_group_id = process_group_id
        self.windows_job = windows_job

    @staticmethod
    def _posix_group_exists(process_group_id: int) -> bool:
        try:
            os.killpg(process_group_id, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def terminate_and_verify(self) -> bool:
        if self.windows_job is not None:
            verified = self.windows_job.terminate_and_verify()
        else:
            assert self.process_group_id is not None
            process_group_id = self.process_group_id
            try:
                os.killpg(process_group_id, signal.SIGTERM)
            except ProcessLookupError:
                pass
            grace_deadline = time.monotonic() + 0.5
            while (
                self._posix_group_exists(process_group_id)
                and time.monotonic() < grace_deadline
            ):
                time.sleep(0.05)
            if self._posix_group_exists(process_group_id):
                try:
                    os.killpg(process_group_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            verify_deadline = time.monotonic() + 5
            while (
                self._posix_group_exists(process_group_id)
                and time.monotonic() < verify_deadline
            ):
                time.sleep(0.05)
            verified = not self._posix_group_exists(process_group_id)
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            verified = False
        return verified and self.process.poll() is not None


def _launch_contained_process(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> _ProcessContainment:
    if os.name != "nt":
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            shell=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return _ProcessContainment(process, process_group_id=process.pid)

    job = _WindowsJob()
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", _WINDOWS_LAUNCHER],
            cwd=cwd,
            env=environment,
            shell=False,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        job.assign(process)
        assert process.stdin is not None
        process.stdin.write(json.dumps({"argv": command}).encode("utf-8") + b"\n")
        process.stdin.close()
        return _ProcessContainment(process, windows_job=job)
    except BaseException:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        job.close()
        raise


def _finish_capture(
    process: subprocess.Popen[bytes],
    threads: Iterable[threading.Thread],
) -> bool:
    thread_list = list(threads)
    deadline = time.monotonic() + 5
    for thread in thread_list:
        thread.join(timeout=max(0, deadline - time.monotonic()))
    complete = not any(thread.is_alive() for thread in thread_list)
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            try:
                if complete:
                    stream.close()
                else:
                    os.close(stream.fileno())
            except OSError:
                complete = False
    if not complete:
        for thread in thread_list:
            thread.join(timeout=0.25)
    return complete


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
        self._safe_report_directory = _SafeReportDirectory(
            self.candidate_root,
            report_dir,
        )
        self.report_dir = self._safe_report_directory.path
        self.base_environment = base_environment
        self.max_output_bytes = max_output_bytes

    def run(self, gate: GateDefinition) -> GateResult:
        return self._run_until(
            gate,
            time.monotonic() + gate.timeout_seconds,
        )

    def _run_until(
        self,
        gate: GateDefinition,
        deadline: float,
    ) -> GateResult:
        self._safe_report_directory.verify()
        started = time.monotonic()
        command = list(gate.argv)
        sensitive_paths = (
            self.candidate_root,
            self.report_dir,
            self._safe_report_directory.physical_path,
        )
        stdout_tail = _BoundedTail(
            self.max_output_bytes,
            sensitive_paths=sensitive_paths,
        )
        stderr_tail = _BoundedTail(
            self.max_output_bytes,
            sensitive_paths=sensitive_paths,
        )
        timed_out = False
        process: subprocess.Popen[bytes] | None = None
        containment: _ProcessContainment | None = None
        threads: list[threading.Thread] = []
        cleanup_complete = True
        capture_complete = True
        try:
            containment = _launch_contained_process(
                command,
                cwd=self.candidate_root,
                environment=_sanitized_environment(
                    self.candidate_root,
                    self.base_environment,
                ),
            )
            process = containment.process
            assert process.stdout is not None
            assert process.stderr is not None
            threads = [
                threading.Thread(
                    target=_drain_stream,
                    args=(process.stdout, stdout_tail),
                    daemon=True,
                ),
                threading.Thread(
                    target=_drain_stream,
                    args=(process.stderr, stderr_tail),
                    daemon=True,
                ),
            ]
            for thread in threads:
                thread.start()
            try:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, 0)
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
        except OSError as error:
            stderr_tail.append(str(error).encode("utf-8", errors="replace"))
        finally:
            if containment is not None:
                cleanup_complete = containment.terminate_and_verify()
            if process is not None:
                capture_complete = _finish_capture(process, threads)

        duration = time.monotonic() - started
        exit_code = process.returncode if process is not None else None
        stdout = _record_output(
            stdout_tail.decode(),
            maximum_bytes=self.max_output_bytes,
            sensitive_paths=sensitive_paths,
        )
        raw_stderr = stderr_tail.decode()
        if not cleanup_complete or not capture_complete:
            cleanup_error = "process containment cleanup could not be verified"
            raw_stderr = "\n".join(
                part for part in (raw_stderr, cleanup_error) if part
            )
        stderr = _record_output(
            raw_stderr,
            maximum_bytes=self.max_output_bytes,
            sensitive_paths=sensitive_paths,
        )
        recorded_name = redact_gate_output(
            gate.name,
            sensitive_paths=sensitive_paths,
        )
        recorded_command = [
            redact_gate_output(argument, sensitive_paths=sensitive_paths)
            for argument in command
        ]
        return GateResult(
            name=recorded_name,
            command=recorded_command,
            passed=(
                not timed_out
                and exit_code == 0
                and cleanup_complete
                and capture_complete
            ),
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


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("health deadline expired")
    return remaining


def _receive_with_deadline(connection: socket.socket, deadline: float) -> bytes:
    connection.settimeout(_remaining_seconds(deadline))
    return connection.recv(8192)


def _read_health_response(port: int, deadline: float) -> bool:
    with socket.create_connection(
        ("127.0.0.1", port),
        timeout=_remaining_seconds(deadline),
    ) as connection:
        connection.settimeout(_remaining_seconds(deadline))
        connection.sendall(
            b"GET /healthz HTTP/1.1\r\n"
            b"Host: 127.0.0.1\r\n"
            b"Accept: application/json\r\n"
            b"Connection: close\r\n\r\n"
        )
        received = bytearray()
        header_end = -1
        while header_end < 0:
            chunk = _receive_with_deadline(connection, deadline)
            if not chunk:
                raise OSError("health endpoint closed before headers")
            received.extend(chunk)
            header_end = received.find(b"\r\n\r\n")
            if header_end < 0 and len(received) > _MAX_HEALTH_HEADER_BYTES:
                raise _HealthResponseRejected("health headers exceed byte limit")

        header_bytes = bytes(received[:header_end])
        body = bytearray(received[header_end + 4 :])
        if len(header_bytes) > _MAX_HEALTH_HEADER_BYTES:
            raise _HealthResponseRejected("health headers exceed byte limit")
        header_lines = header_bytes.decode("iso-8859-1").split("\r\n")
        status_parts = header_lines[0].split()
        if len(status_parts) < 2 or not status_parts[1].isdigit():
            raise OSError("health endpoint returned an invalid status line")
        if int(status_parts[1]) != 200:
            return False
        headers: dict[str, str] = {}
        for line in header_lines[1:]:
            if ":" not in line:
                continue
            name, value = line.split(":", 1)
            headers[name.strip().lower()] = value.strip()
        content_length: int | None = None
        if "content-length" in headers:
            try:
                content_length = int(headers["content-length"])
            except ValueError as error:
                raise OSError("health content length is invalid") from error
            if content_length < 0:
                raise OSError("health content length is negative")
            if content_length > _MAX_HEALTH_BODY_BYTES:
                raise _HealthResponseRejected("health body exceeds byte limit")

        while content_length is None or len(body) < content_length:
            if len(body) > _MAX_HEALTH_BODY_BYTES:
                raise _HealthResponseRejected("health body exceeds byte limit")
            chunk = _receive_with_deadline(connection, deadline)
            if not chunk:
                break
            body.extend(chunk)
        if content_length is not None and len(body) < content_length:
            raise OSError("health endpoint closed before the complete body")
        if len(body) > _MAX_HEALTH_BODY_BYTES:
            raise _HealthResponseRejected("health body exceeds byte limit")
        payload_bytes = bytes(body[:content_length]) if content_length is not None else bytes(body)
        payload = json.loads(payload_bytes.decode("utf-8"))
        return payload.get("ok") is True


def _wait_for_health(
    port: int,
    deadline: float,
    process: subprocess.Popen[bytes],
) -> tuple[bool, bool]:
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False, False
        try:
            ready = _read_health_response(port, deadline)
        except _HealthResponseRejected:
            return False, True
        except (OSError, ValueError, json.JSONDecodeError):
            ready = False
        if ready:
            try:
                process.wait(timeout=min(0.05, _remaining_seconds(deadline)))
            except subprocess.TimeoutExpired:
                return True, False
            except TimeoutError:
                return False, False
            return False, False
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    return False, False


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
    destination = _absolute_lexical_path(report_path)
    safe_reports = _SafeReportDirectory(candidate, destination.parent)
    stdout_filename = destination.stem + ".server.stdout.log"
    stderr_filename = destination.stem + ".server.stderr.log"
    safe_reports.validate_output(destination.name)
    safe_reports.validate_output(stdout_filename)
    safe_reports.validate_output(stderr_filename)

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
    sensitive_paths = (
        candidate,
        safe_reports.path,
        safe_reports.physical_path,
    )
    server_stdout = _BoundedTail(65_536, sensitive_paths=sensitive_paths)
    server_stderr = _BoundedTail(65_536, sensitive_paths=sensitive_paths)
    server: subprocess.Popen[bytes] | None = None
    server_containment: _ProcessContainment | None = None
    server_threads: list[threading.Thread] = []
    startup_healthy = False
    probe_result: GateResult | None = None
    server_alive_after_probe = False
    timed_out = False
    launch_error = ""
    cleanup_complete = False

    try:
        server_containment = _launch_contained_process(
            server_command,
            cwd=candidate,
            environment=_sanitized_environment(candidate, None),
        )
        server = server_containment.process
        assert server.stdout is not None
        assert server.stderr is not None
        server_threads = [
            threading.Thread(
                target=_drain_stream,
                args=(server.stdout, server_stdout),
                daemon=True,
            ),
            threading.Thread(
                target=_drain_stream,
                args=(server.stderr, server_stderr),
                daemon=True,
            ),
        ]
        for thread in server_threads:
            thread.start()

        startup_healthy, health_rejected = _wait_for_health(
            port,
            deadline,
            server,
        )
        if health_rejected:
            launch_error = "health response exceeded its allowed byte boundary"
        if not startup_healthy and not health_rejected and server.poll() is None:
            timed_out = time.monotonic() >= deadline
        if startup_healthy:
            if server.poll() is not None:
                startup_healthy = False
                launch_error = "candidate server exited after readiness"
            remaining = deadline - time.monotonic()
            if startup_healthy and remaining <= 0:
                timed_out = True
            elif startup_healthy:
                probe_runner = GateRunner(
                    candidate,
                    safe_reports.path,
                )
                probe_result = probe_runner._run_until(
                    GateDefinition(
                        name="clean_start_probe",
                        argv=tuple(probe_command),
                        timeout_seconds=timeout_seconds,
                    ),
                    deadline,
                )
                timed_out = probe_result.timed_out
                server_alive_after_probe = server.poll() is None
                if not server_alive_after_probe:
                    launch_error = "candidate server exited during smoke probe"
    except OSError as error:
        launch_error = str(error)
    finally:
        containment_complete = True
        capture_complete = True
        if server_containment is not None:
            containment_complete = server_containment.terminate_and_verify()
        if server is not None:
            capture_complete = _finish_capture(server, server_threads)
        cleanup_complete = containment_complete and capture_complete

    recorded_server_stdout = _record_output(
        server_stdout.decode(),
        maximum_bytes=65_536,
        sensitive_paths=sensitive_paths,
    )
    recorded_server_stderr = _record_output(
        server_stderr.decode(),
        maximum_bytes=65_536,
        sensitive_paths=sensitive_paths,
    )
    stdout = probe_result.stdout_tail if probe_result is not None else ""
    stderr_parts = [
        probe_result.stderr_tail if probe_result is not None else "",
        recorded_server_stderr,
        launch_error,
    ]
    stderr = _record_output(
        "\n".join(part for part in stderr_parts if part),
        maximum_bytes=65_536,
        sensitive_paths=sensitive_paths,
    )
    probe_passed = (
        probe_result is not None
        and probe_result.passed
        and server_alive_after_probe
    )
    if probe_result is not None:
        exit_code = probe_result.exit_code
    elif server is not None:
        exit_code = server.returncode
    else:
        exit_code = None
    result = GateResult(
        name="clean_start_smoke",
        command=[
            redact_gate_output(argument, sensitive_paths=sensitive_paths)
            for argument in (probe_command if startup_healthy else server_command)
        ],
        passed=startup_healthy and probe_passed and cleanup_complete,
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        stdout_tail=stdout,
        stderr_tail=stderr,
    )

    stdout_file = safe_reports.write_text(
        stdout_filename,
        recorded_server_stdout + ("\n" if recorded_server_stdout else ""),
    )
    stderr_file = safe_reports.write_text(
        stderr_filename,
        recorded_server_stderr + ("\n" if recorded_server_stderr else ""),
    )
    payload = asdict(result)
    payload.update(
        {
            "startup_healthy": startup_healthy,
            "probe_passed": probe_passed,
            "cleanup_complete": cleanup_complete,
            "server_alive_after_probe": server_alive_after_probe,
            "server_pid": server.pid if server is not None else None,
            "port": port,
            "server_stdout_file": stdout_file.name,
            "server_stderr_file": stderr_file.name,
        }
    )
    safe_reports.write_text(
        destination.name,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )
    return result
