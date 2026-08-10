"""Bounded, sanitized subprocess verification for Nova release candidates."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import secrets
import select
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
    r"database_rows?|db_rows?|private)[\"']?\s*[:=]"
)
_SENSITIVE_OPTION = re.compile(
    r"^--?(?:[^=]*(?:prompt|response|memory|database|db|private|authorization|"
    r"token|key|secret|password)[^=]*)(?:=(.*))?$",
    re.IGNORECASE,
)
_WINDOWS_LAUNCHER = (
    "import json, subprocess, sys; "
    "payload = json.loads(sys.stdin.buffer.readline()); "
    "child = subprocess.Popen(payload['argv'], shell=False, "
    "stdin=subprocess.DEVNULL); "
    "raise SystemExit(child.wait())"
)
_POSIX_SUPERVISOR = """
import json
import os
import select
import signal
import subprocess
import sys
import time

status_fd = int(sys.argv[1])
control_fd = int(sys.argv[2])
ready_fd = int(sys.argv[3])
child = None
try:
    payload_bytes = sys.stdin.buffer.readline(262145)
    if len(payload_bytes) > 262144 or not payload_bytes.endswith(b"\\n"):
        raise ValueError("invalid payload")
    payload = json.loads(payload_bytes)
    argv = payload.get("argv")
    if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
        raise ValueError("invalid argv")
    readable, _, _ = select.select([control_fd], [], [], 0)
    if readable:
        raise RuntimeError("controller cancelled launch")
    child = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL)
except BaseException:
    os.write(ready_fd, b'{"started":false,"error":"candidate spawn failed"}\\n')
    raise SystemExit(72)
else:
    os.write(ready_fd, b'{"started":true}\\n')
finally:
    os.close(ready_fd)

while child.poll() is None:
    readable, _, _ = select.select([control_fd], [], [], 0.05)
    if readable:
        os.read(control_fd, 1)
        child.terminate()
        try:
            child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()
        break
exit_code = child.wait()
os.write(status_fd, (str(exit_code) + "\\n").encode("ascii"))
os.close(status_fd)
signal.signal(signal.SIGTERM, signal.SIG_IGN)
os.read(control_fd, 1)
os.close(control_fd)
raise SystemExit(0)
"""
_MAX_HEALTH_HEADER_BYTES = 16_384
_MAX_HEALTH_BODY_BYTES = 65_536
_MAX_TCP_TABLE_BYTES = 4 * 1024 * 1024
_MAX_TCP_ROWS = 65_536
_MAX_PROC_PIDS = 32_768
_MAX_PROC_FDS_PER_PID = 4_096
_MAX_PROC_LINK_BYTES = 512
_MAX_PROC_COMPONENT_BYTES = 32
_PLATFORM_OS_NAME = os.name
_PLATFORM_SYSTEM = sys.platform
_SUPERVISOR_HANDSHAKE_SECONDS = 5.0


class _HealthResponseRejected(Exception):
    pass


class _ConnectionOwnershipRejected(Exception):
    pass


def _ensure_supported_platform() -> None:
    if _PLATFORM_OS_NAME == "nt":
        return
    if _PLATFORM_OS_NAME == "posix" and _PLATFORM_SYSTEM.startswith("linux"):
        return
    raise RuntimeError("unsupported release-gate platform")


@dataclass(frozen=True)
class GateDefinition:
    name: str
    argv: tuple[str, ...]
    timeout_seconds: int
    required: bool = True
    artifact_paths: tuple[str, ...] = ()


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


def _persisted_log_content(output: str, maximum_bytes: int) -> str:
    bounded = _valid_utf8_suffix(output, maximum_bytes)
    if bounded and len(bounded.encode("utf-8")) < maximum_bytes:
        return bounded + "\n"
    return bounded


def _redact_command(
    command: Iterable[str],
    *,
    sensitive_paths: Iterable[str | Path],
) -> list[str]:
    recorded: list[str] = []
    redact_next = False
    for argument in command:
        if redact_next:
            recorded.append("[REDACTED]")
            redact_next = False
            continue
        option = _SENSITIVE_OPTION.match(argument)
        if option is not None:
            if "=" in argument:
                recorded.append(argument.split("=", 1)[0] + "=[REDACTED]")
            else:
                recorded.append(
                    redact_gate_output(argument, sensitive_paths=sensitive_paths)
                )
                redact_next = True
            continue
        recorded.append(
            redact_gate_output(argument, sensitive_paths=sensitive_paths)
        )
    return recorded


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
        self._directory_fd: int | None = None
        self._directory_handle: int | None = None
        self._directory_handles: list[int] = []
        self._before_create_hook = None
        self._pin_directory()

    def _pin_directory(self) -> None:
        if os.name != "nt":
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            self._directory_fd = os.open(self.path, flags)
            if self._pinned_identity() != self._identity:
                self.close()
                raise ValueError("run-report directory changed while pinning")
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        current = Path(self.path.anchor)
        chain = [current]
        for component in self.path.parts[1:]:
            current /= component
            chain.append(current)
        try:
            for directory in chain:
                handle = kernel32.CreateFileW(
                    str(directory),
                    0x0001 | 0x0080,
                    0x00000001 | 0x00000002,
                    None,
                    3,
                    0x02000000 | 0x00200000,
                    None,
                )
                if handle == wintypes.HANDLE(-1).value:
                    raise ctypes.WinError(ctypes.get_last_error())
                numeric_handle = int(handle)
                self._directory_handles.append(numeric_handle)
                path_stat = os.stat(directory, follow_symlinks=False)
                path_identity = (path_stat.st_dev, path_stat.st_ino)
                if self._windows_handle_identity(numeric_handle) != path_identity:
                    raise ValueError("report ancestor changed while pinning")
        except BaseException:
            self.close()
            raise
        self._directory_handle = self._directory_handles[-1]
        if self._pinned_identity() != self._identity:
            self.close()
            raise ValueError("run-report directory changed while pinning")

    @staticmethod
    def _windows_handle_identity(handle: int) -> tuple[int, int]:
        class _FileInformation(ctypes.Structure):
            _fields_ = [
                ("FileAttributes", wintypes.DWORD),
                ("CreationTime", wintypes.FILETIME),
                ("LastAccessTime", wintypes.FILETIME),
                ("LastWriteTime", wintypes.FILETIME),
                ("VolumeSerialNumber", wintypes.DWORD),
                ("FileSizeHigh", wintypes.DWORD),
                ("FileSizeLow", wintypes.DWORD),
                ("NumberOfLinks", wintypes.DWORD),
                ("FileIndexHigh", wintypes.DWORD),
                ("FileIndexLow", wintypes.DWORD),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetFileInformationByHandle.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_FileInformation),
        ]
        kernel32.GetFileInformationByHandle.restype = wintypes.BOOL
        information = _FileInformation()
        if not kernel32.GetFileInformationByHandle(
            wintypes.HANDLE(handle),
            ctypes.byref(information),
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        file_index = (int(information.FileIndexHigh) << 32) | int(
            information.FileIndexLow
        )
        return int(information.VolumeSerialNumber), file_index

    def _pinned_identity(self) -> tuple[int, int]:
        if self._directory_fd is not None:
            directory_stat = os.fstat(self._directory_fd)
            return (directory_stat.st_dev, directory_stat.st_ino)
        if self._directory_handle is not None:
            return self._windows_handle_identity(self._directory_handle)
        raise ValueError("run-report directory pin is closed")

    def close(self) -> None:
        if self._directory_fd is not None:
            os.close(self._directory_fd)
            self._directory_fd = None
        if self._directory_handles:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel32.CloseHandle.restype = wintypes.BOOL
            for handle in reversed(self._directory_handles):
                kernel32.CloseHandle(wintypes.HANDLE(handle))
            self._directory_handles.clear()
        self._directory_handle = None

    def __del__(self) -> None:
        try:
            self.close()
        except (OSError, AttributeError):
            pass

    def _directory_identity(self) -> tuple[int, int]:
        directory_stat = os.stat(self.path, follow_symlinks=False)
        return (directory_stat.st_dev, directory_stat.st_ino)

    def verify(self) -> None:
        if self._directory_fd is None and self._directory_handle is None:
            raise ValueError("run-report directory pin is closed")
        if self._pinned_identity() != self._identity:
            raise ValueError("pinned run-report directory identity changed")
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

    def _artifact_filename(self, artifact_path: str | Path) -> str:
        artifact = _absolute_lexical_path(artifact_path)
        if artifact.parent != self.path:
            raise ValueError("gate artifact must be within the verified report directory")
        return artifact.name

    def reserve_artifact(self, artifact_path: str | Path) -> tuple[str, tuple[int, int]]:
        filename = self._artifact_filename(artifact_path)
        destination = self.output_path(filename)
        self.verify()
        if os.path.lexists(destination):
            if _is_link_or_reparse(destination):
                raise ValueError("gate artifact is a link or reparse point")
            raise ValueError("gate artifact already exists")
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        if self._directory_fd is not None:
            descriptor = os.open(filename, flags, 0o600, dir_fd=self._directory_fd)
        else:
            descriptor = os.open(destination, flags, 0o600)
        try:
            artifact_stat = os.fstat(descriptor)
            identity = (artifact_stat.st_dev, artifact_stat.st_ino)
        finally:
            os.close(descriptor)
        self.verify()
        return filename, identity

    def verify_artifact(
        self,
        reservation: tuple[str, tuple[int, int]],
    ) -> bool:
        filename, identity = reservation
        try:
            self.verify()
            destination = self.output_path(filename)
            if _is_link_or_reparse(destination):
                return False
            if self._directory_fd is not None:
                artifact_stat = os.stat(
                    filename,
                    dir_fd=self._directory_fd,
                    follow_symlinks=False,
                )
            else:
                artifact_stat = os.stat(destination, follow_symlinks=False)
            return (
                stat.S_ISREG(artifact_stat.st_mode)
                and (artifact_stat.st_dev, artifact_stat.st_ino) == identity
                and artifact_stat.st_size > 0
            )
        except (OSError, ValueError):
            return False

    def discard_artifact(
        self,
        reservation: tuple[str, tuple[int, int]],
    ) -> None:
        filename, identity = reservation
        destination = self.output_path(filename)
        try:
            if self._directory_fd is not None:
                artifact_stat = os.stat(
                    filename,
                    dir_fd=self._directory_fd,
                    follow_symlinks=False,
                )
            else:
                artifact_stat = os.stat(destination, follow_symlinks=False)
            if (artifact_stat.st_dev, artifact_stat.st_ino) == identity:
                if self._directory_fd is not None:
                    os.unlink(filename, dir_fd=self._directory_fd)
                else:
                    destination.unlink()
        except OSError:
            pass

    def write_text(self, filename: str, content: str) -> Path:
        destination = self.validate_output(filename)
        hook = self._before_create_hook
        if hook is not None:
            hook()
        temporary_filename = f".{filename}.{secrets.token_hex(12)}.tmp"
        if self._directory_fd is not None:
            self._pinned_identity()
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(
                temporary_filename,
                flags,
                0o600,
                dir_fd=self._directory_fd,
            )
            temporary = self.path / temporary_filename
        else:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.path,
                prefix=f".{filename}.",
                suffix=".tmp",
            )
            temporary = Path(temporary_name)
            temporary_filename = temporary.name
        try:
            if self._directory_fd is None and _is_link_or_reparse(temporary):
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
            if self._directory_fd is not None:
                current_temporary_stat = os.stat(
                    temporary_filename,
                    dir_fd=self._directory_fd,
                    follow_symlinks=False,
                )
            else:
                current_temporary_stat = os.stat(temporary, follow_symlinks=False)
            if (
                current_temporary_stat.st_dev,
                current_temporary_stat.st_ino,
            ) != temporary_identity:
                raise ValueError("exclusive report temporary identity changed")
            if self._directory_fd is not None:
                os.replace(
                    temporary_filename,
                    filename,
                    src_dir_fd=self._directory_fd,
                    dst_dir_fd=self._directory_fd,
                )
            else:
                os.replace(temporary, destination)
            self.verify()
            if self._directory_fd is not None:
                final_stat = os.stat(
                    filename,
                    dir_fd=self._directory_fd,
                    follow_symlinks=False,
                )
            else:
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
            if self._directory_fd is not None:
                try:
                    os.unlink(temporary_filename, dir_fd=self._directory_fd)
                except FileNotFoundError:
                    pass
            elif os.path.lexists(temporary):
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
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.IsProcessInJob.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.BOOL),
        ]
        kernel32.IsProcessInJob.restype = wintypes.BOOL
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

    def contains_pid(self, pid: int) -> bool:
        process_handle = self._kernel32.OpenProcess(0x1000, False, pid)
        if not process_handle:
            return False
        try:
            contained = wintypes.BOOL()
            if not self._kernel32.IsProcessInJob(
                process_handle,
                self._handle,
                ctypes.byref(contained),
            ):
                return False
            return bool(contained.value)
        finally:
            self._kernel32.CloseHandle(process_handle)

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
        status_fd: int | None = None,
        control_fd: int | None = None,
    ) -> None:
        self.process = process
        self.process_group_id = process_group_id
        self.windows_job = windows_job
        self.status_fd = status_fd
        self.control_fd = control_fd
        self.candidate_exit_code: int | None = None

    @staticmethod
    def _linux_process_session(pid: int) -> int | None:
        try:
            content = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
            fields = content.rsplit(")", 1)[1].split()
            return int(fields[3])
        except (OSError, ValueError, IndexError):
            return None

    def owns_pid(self, pid: int) -> bool:
        if self.windows_job is not None:
            return self.windows_job.contains_pid(pid)
        assert self.process_group_id is not None
        return self._linux_process_session(pid) == self.process_group_id

    def candidate_alive(self) -> bool:
        if self.candidate_exit_code is not None:
            return False
        if self.status_fd is None:
            return self.process.poll() is None
        ready, _, _ = select.select([self.status_fd], [], [], 0)
        if ready:
            try:
                self.wait_candidate(0)
            except (OSError, subprocess.TimeoutExpired):
                pass
            return False
        return self.process.poll() is None

    def wait_candidate(self, timeout_seconds: float) -> int:
        if self.status_fd is None:
            self.candidate_exit_code = self.process.wait(timeout=timeout_seconds)
            return self.candidate_exit_code
        ready, _, _ = select.select([self.status_fd], [], [], timeout_seconds)
        if not ready:
            raise subprocess.TimeoutExpired("contained candidate", timeout_seconds)
        status = os.read(self.status_fd, 64).decode("ascii").strip()
        os.close(self.status_fd)
        self.status_fd = None
        if not status or not re.fullmatch(r"-?\d+", status):
            raise OSError("trusted supervisor returned invalid candidate status")
        self.candidate_exit_code = int(status)
        return self.candidate_exit_code

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
            verified = self._terminate_linux_session_members()
            if self.control_fd is not None:
                try:
                    os.write(self.control_fd, b"x")
                except OSError:
                    verified = False
                try:
                    os.close(self.control_fd)
                except OSError:
                    verified = False
                self.control_fd = None
            if self.status_fd is not None:
                try:
                    os.close(self.status_fd)
                except OSError:
                    pass
                self.status_fd = None
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            verified = False
        return verified and self.process.poll() is not None

    def _linux_session_members(self) -> list[int] | None:
        if not sys.platform.startswith("linux"):
            return None
        members: list[int] = []
        try:
            entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        for entry in entries:
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == self.process.pid:
                continue
            if self._linux_process_session(pid) == self.process_group_id:
                members.append(pid)
        return members

    def _signal_linux_members(self, members: Iterable[int], signum: int) -> bool:
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            return False
        verified = True
        for pid in members:
            descriptor: int | None = None
            try:
                descriptor = os.pidfd_open(pid)
                if not self.owns_pid(pid):
                    continue
                signal.pidfd_send_signal(descriptor, signum)
            except ProcessLookupError:
                continue
            except OSError:
                verified = False
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        return verified

    def _terminate_linux_session_members(self) -> bool:
        members = self._linux_session_members()
        if members is None:
            if self.process_group_id is not None:
                try:
                    os.killpg(self.process_group_id, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return False
        verified = self._signal_linux_members(members, signal.SIGTERM)
        grace_deadline = time.monotonic() + 0.5
        while time.monotonic() < grace_deadline:
            remaining = self._linux_session_members()
            if not remaining:
                return verified
            time.sleep(0.05)
        remaining = self._linux_session_members() or []
        verified = self._signal_linux_members(remaining, signal.SIGKILL) and verified
        verify_deadline = time.monotonic() + 5
        while time.monotonic() < verify_deadline:
            if not self._linux_session_members():
                return verified
            time.sleep(0.05)
        return False


def _terminate_failed_posix_launch(process: subprocess.Popen[bytes]) -> None:
    containment = _ProcessContainment(
        process,
        process_group_id=process.pid,
    )
    members = containment._linux_session_members() or []
    containment._signal_linux_members(members, signal.SIGKILL)
    supervisor_descriptor: int | None = None
    try:
        if hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"):
            supervisor_descriptor = os.pidfd_open(process.pid)
            signal.pidfd_send_signal(supervisor_descriptor, signal.SIGKILL)
        elif process.poll() is None:
            process.kill()
    except ProcessLookupError:
        pass
    finally:
        if supervisor_descriptor is not None:
            os.close(supervisor_descriptor)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        remaining = containment._linux_session_members()
        if not remaining:
            break
        containment._signal_linux_members(remaining, signal.SIGKILL)
        time.sleep(0.02)
    try:
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _launch_contained_process(
    command: list[str],
    *,
    cwd: Path,
    environment: Mapping[str, str],
) -> _ProcessContainment:
    _ensure_supported_platform()
    if os.name != "nt":
        descriptors: set[int] = set()
        process: subprocess.Popen[bytes] | None = None
        try:
            status_read, status_write = os.pipe()
            descriptors.update((status_read, status_write))
            control_read, control_write = os.pipe()
            descriptors.update((control_read, control_write))
            ready_read, ready_write = os.pipe()
            descriptors.update((ready_read, ready_write))
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    _POSIX_SUPERVISOR,
                    str(status_write),
                    str(control_read),
                    str(ready_write),
                ],
                cwd=cwd,
                env=environment,
                shell=False,
                start_new_session=True,
                pass_fds=(status_write, control_read, ready_write),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for descriptor in (status_write, control_read, ready_write):
                os.close(descriptor)
                descriptors.discard(descriptor)
            payload = json.dumps({"argv": command}).encode("utf-8") + b"\n"
            if len(payload) > 262_144:
                raise ValueError("candidate command exceeds supervisor payload bound")
            assert process.stdin is not None
            process.stdin.write(payload)
            process.stdin.close()
            ready, _, _ = select.select(
                [ready_read],
                [],
                [],
                _SUPERVISOR_HANDSHAKE_SECONDS,
            )
            if not ready:
                raise TimeoutError("trusted supervisor handshake timed out")
            response = os.read(ready_read, 257)
            os.close(ready_read)
            descriptors.discard(ready_read)
            if len(response) > 256 or not response.endswith(b"\n"):
                raise OSError("trusted supervisor returned invalid launch status")
            try:
                launch_status = json.loads(response)
            except (UnicodeError, json.JSONDecodeError) as error:
                raise OSError(
                    "trusted supervisor returned invalid launch status"
                ) from error
            if launch_status != {"started": True}:
                raise OSError("candidate spawn failed")
            return _ProcessContainment(
                process,
                process_group_id=process.pid,
                status_fd=status_read,
                control_fd=control_write,
            )
        except BaseException:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
                _terminate_failed_posix_launch(process)
                for stream in (process.stdout, process.stderr):
                    if stream is not None and not stream.closed:
                        stream.close()
            for descriptor in descriptors:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            raise

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
        _ensure_supported_platform()
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
        artifact_reservations: list[tuple[str, tuple[int, int]]] = []
        try:
            for artifact_path in gate.artifact_paths:
                artifact_reservations.append(
                    self._safe_report_directory.reserve_artifact(artifact_path)
                )
        except BaseException:
            for reservation in artifact_reservations:
                self._safe_report_directory.discard_artifact(reservation)
            raise
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
                containment.wait_candidate(remaining)
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
        if containment is not None and containment.candidate_exit_code is not None:
            exit_code = containment.candidate_exit_code
        else:
            exit_code = process.returncode if process is not None else None
        artifacts_complete = all(
            self._safe_report_directory.verify_artifact(reservation)
            for reservation in artifact_reservations
        )
        if not artifacts_complete or timed_out or exit_code != 0:
            for reservation in artifact_reservations:
                self._safe_report_directory.discard_artifact(reservation)
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
        if not artifacts_complete:
            raw_stderr = "\n".join(
                part
                for part in (
                    raw_stderr,
                    "gate artifact output could not be verified",
                )
                if part
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
        recorded_command = _redact_command(
            command,
            sensitive_paths=sensitive_paths,
        )
        return GateResult(
            name=recorded_name,
            command=recorded_command,
            passed=(
                not timed_out
                and exit_code == 0
                and cleanup_complete
                and capture_complete
                and artifacts_complete
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
            artifact_paths=(str(reports / "nova-sbom.json"),),
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
            artifact_paths=(str(reports / "conversation-560.json"),),
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


def _deadline_expired(deadline: float) -> bool:
    return time.monotonic() >= deadline


def _windows_connection_owner_pids(
    server_endpoint: tuple[str, int],
    client_endpoint: tuple[str, int],
    deadline: float,
    *,
    maximum_table_bytes: int = _MAX_TCP_TABLE_BYTES,
) -> set[int] | None:
    if os.name != "nt" or _deadline_expired(deadline):
        return None

    class _TcpRowOwnerPid(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_address", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_address", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("owning_pid", wintypes.DWORD),
        ]

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    function = iphlpapi.GetExtendedTcpTable
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    function.restype = wintypes.DWORD
    size = wintypes.ULONG()
    first = function(None, ctypes.byref(size), False, socket.AF_INET, 5, 0)
    if (
        first not in (0, 122)
        or not size.value
        or size.value > maximum_table_bytes
        or _deadline_expired(deadline)
    ):
        return None
    table = ctypes.create_string_buffer(size.value)
    if function(table, ctypes.byref(size), False, socket.AF_INET, 5, 0) != 0:
        return None
    count = ctypes.cast(table, ctypes.POINTER(wintypes.DWORD)).contents.value
    row_size = ctypes.sizeof(_TcpRowOwnerPid)
    if count > _MAX_TCP_ROWS or 4 + count * row_size > size.value:
        return None
    expected_local_address = int.from_bytes(
        socket.inet_aton(server_endpoint[0]),
        sys.byteorder,
    )
    expected_remote_address = int.from_bytes(
        socket.inet_aton(client_endpoint[0]),
        sys.byteorder,
    )
    base = ctypes.addressof(table) + ctypes.sizeof(wintypes.DWORD)
    owners: set[int] = set()
    for index in range(count):
        if index % 256 == 0 and _deadline_expired(deadline):
            return None
        row = _TcpRowOwnerPid.from_address(base + index * row_size)
        if (
            int(row.state) == 5
            and int(row.local_address) == expected_local_address
            and socket.ntohs(int(row.local_port) & 0xFFFF) == server_endpoint[1]
            and int(row.remote_address) == expected_remote_address
            and socket.ntohs(int(row.remote_port) & 0xFFFF) == client_endpoint[1]
        ):
            owners.add(int(row.owning_pid))
    return owners


def _linux_connection_owner_pids(
    server_endpoint: tuple[str, int],
    client_endpoint: tuple[str, int],
    deadline: float,
    *,
    proc_root: Path = Path("/proc"),
    maximum_tcp_bytes: int = _MAX_TCP_TABLE_BYTES,
    maximum_processes: int = _MAX_PROC_PIDS,
    maximum_fds_per_process: int = _MAX_PROC_FDS_PER_PID,
) -> set[int] | None:
    if _deadline_expired(deadline):
        return None
    expected_local = (
        f"{int.from_bytes(socket.inet_aton(server_endpoint[0]), 'little'):08X}:"
        f"{server_endpoint[1]:04X}"
    )
    expected_remote = (
        f"{int.from_bytes(socket.inet_aton(client_endpoint[0]), 'little'):08X}:"
        f"{client_endpoint[1]:04X}"
    )
    inodes: set[str] = set()
    total_bytes = 0
    try:
        with (proc_root / "net" / "tcp").open("rb") as stream:
            for row_index in range(_MAX_TCP_ROWS + 1):
                if _deadline_expired(deadline):
                    return None
                line = stream.readline(4096)
                if not line:
                    break
                total_bytes += len(line)
                if total_bytes > maximum_tcp_bytes or not line.endswith(b"\n"):
                    return None
                if row_index == 0:
                    continue
                fields = line.decode("ascii", errors="strict").split()
                if (
                    len(fields) >= 10
                    and fields[1].upper() == expected_local
                    and fields[2].upper() == expected_remote
                    and fields[3] == "01"
                ):
                    inodes.add(fields[9])
            else:
                return None
    except (OSError, UnicodeError, ValueError):
        return None
    if not inodes:
        return set()
    owners: set[int] = set()
    try:
        with os.scandir(proc_root) as processes:
            process_count = 0
            for process in processes:
                if _deadline_expired(deadline):
                    return None
                if not process.name.isdigit():
                    continue
                if len(os.fsencode(process.name)) > _MAX_PROC_COMPONENT_BYTES:
                    return None
                process_count += 1
                if process_count > maximum_processes:
                    return None
                try:
                    with os.scandir(Path(process.path) / "fd") as descriptors:
                        for descriptor_count, descriptor in enumerate(
                            descriptors,
                            start=1,
                        ):
                            if (
                                descriptor_count > maximum_fds_per_process
                                or _deadline_expired(deadline)
                            ):
                                return None
                            if (
                                len(os.fsencode(descriptor.name))
                                > _MAX_PROC_COMPONENT_BYTES
                            ):
                                return None
                            try:
                                target = os.readlink(descriptor.path)
                            except OSError:
                                continue
                            if len(os.fsencode(target)) > _MAX_PROC_LINK_BYTES:
                                return None
                            if target.startswith("socket:[") and target[8:-1] in inodes:
                                owners.add(int(process.name))
                                break
                except OSError:
                    continue
    except OSError:
        return None
    return owners


def _connection_owned_by_containment(
    connection: socket.socket,
    containment: _ProcessContainment,
    deadline: float,
) -> tuple[bool, str]:
    try:
        client_endpoint = connection.getsockname()
        server_endpoint = connection.getpeername()
    except OSError:
        return False, "connection ownership tuple could not be resolved"
    resolution_deadline = min(deadline, time.monotonic() + 0.5)
    while time.monotonic() < resolution_deadline:
        owners = (
            _windows_connection_owner_pids(
                server_endpoint,
                client_endpoint,
                deadline,
            )
            if os.name == "nt"
            else _linux_connection_owner_pids(
                server_endpoint,
                client_endpoint,
                deadline,
            )
        )
        if owners is None:
            return False, "connection ownership resolution exceeded its bound"
        if owners:
            if not containment.candidate_alive():
                return False, "candidate exited before connection ownership proof"
            if all(containment.owns_pid(pid) for pid in owners):
                return True, ""
            return False, "connection ownership is outside candidate containment"
        time.sleep(min(0.01, max(0, resolution_deadline - time.monotonic())))
    return False, "connection ownership could not be resolved"


def _windows_listener_owner_pids(
    port: int,
    deadline: float | None = None,
) -> set[int] | None:
    deadline = time.monotonic() + 1 if deadline is None else deadline
    if os.name != "nt" or _deadline_expired(deadline):
        return None

    class _TcpRowOwnerPid(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_address", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_address", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("owning_pid", wintypes.DWORD),
        ]

    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    function = iphlpapi.GetExtendedTcpTable
    function.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    function.restype = wintypes.DWORD
    size = wintypes.ULONG()
    first = function(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if (
        first not in (0, 122)
        or not size.value
        or size.value > _MAX_TCP_TABLE_BYTES
        or _deadline_expired(deadline)
    ):
        return None
    table = ctypes.create_string_buffer(size.value)
    if function(table, ctypes.byref(size), False, socket.AF_INET, 3, 0) != 0:
        return None
    count = ctypes.cast(table, ctypes.POINTER(wintypes.DWORD)).contents.value
    row_size = ctypes.sizeof(_TcpRowOwnerPid)
    if count > _MAX_TCP_ROWS or 4 + count * row_size > size.value:
        return None
    base = ctypes.addressof(table) + ctypes.sizeof(wintypes.DWORD)
    owners: set[int] = set()
    for index in range(count):
        if index % 256 == 0 and _deadline_expired(deadline):
            return None
        row = _TcpRowOwnerPid.from_address(base + index * row_size)
        if socket.ntohs(int(row.local_port) & 0xFFFF) == port:
            owners.add(int(row.owning_pid))
    return owners


def _linux_listener_owner_pids(
    port: int,
    deadline: float | None = None,
) -> set[int] | None:
    deadline = time.monotonic() + 1 if deadline is None else deadline
    if not sys.platform.startswith("linux"):
        return None
    inodes: set[str] = set()
    total_bytes = 0
    try:
        with Path("/proc/net/tcp").open("rb") as stream:
            for row_index in range(_MAX_TCP_ROWS + 1):
                if _deadline_expired(deadline):
                    return None
                line = stream.readline(4096)
                if not line:
                    break
                total_bytes += len(line)
                if total_bytes > _MAX_TCP_TABLE_BYTES or not line.endswith(b"\n"):
                    return None
                if row_index == 0:
                    continue
                fields = line.decode("ascii", errors="strict").split()
                if len(fields) >= 10:
                    local_port = int(fields[1].rsplit(":", 1)[1], 16)
                    if local_port == port and fields[3] == "0A":
                        inodes.add(fields[9])
            else:
                return None
    except (OSError, UnicodeError, ValueError, IndexError):
        return None
    owners: set[int] = set()
    try:
        processes = os.scandir("/proc")
    except OSError:
        return None
    with processes:
        process_count = 0
        for process in processes:
            if _deadline_expired(deadline):
                return None
            if not process.name.isdigit():
                continue
            if len(os.fsencode(process.name)) > _MAX_PROC_COMPONENT_BYTES:
                return None
            process_count += 1
            if process_count > _MAX_PROC_PIDS:
                return None
            try:
                descriptors = os.scandir(Path(process.path) / "fd")
            except OSError:
                continue
            with descriptors:
                for descriptor_count, descriptor in enumerate(descriptors, start=1):
                    if (
                        descriptor_count > _MAX_PROC_FDS_PER_PID
                        or _deadline_expired(deadline)
                    ):
                        return None
                    if (
                        len(os.fsencode(descriptor.name))
                        > _MAX_PROC_COMPONENT_BYTES
                    ):
                        return None
                    try:
                        target = os.readlink(descriptor.path)
                    except OSError:
                        continue
                    if len(os.fsencode(target)) > _MAX_PROC_LINK_BYTES:
                        return None
                    if target.startswith("socket:[") and target[8:-1] in inodes:
                        owners.add(int(process.name))
                        break
    return owners


def _listener_owned_by_containment(
    port: int,
    containment: _ProcessContainment,
    deadline: float | None = None,
) -> tuple[bool, str]:
    deadline = time.monotonic() + 1 if deadline is None else deadline
    owners = (
        _windows_listener_owner_pids(port, deadline)
        if os.name == "nt"
        else _linux_listener_owner_pids(port, deadline)
    )
    if owners is None:
        return False, "listener ownership could not be resolved on this platform"
    if not owners:
        return False, "listener ownership could not be resolved"
    if not containment.candidate_alive():
        return False, "candidate exited before listener ownership proof"
    if not all(containment.owns_pid(pid) for pid in owners):
        return False, "listener ownership is outside candidate containment"
    return True, ""


def _remaining_seconds(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("health deadline expired")
    return remaining


def _receive_with_deadline(connection: socket.socket, deadline: float) -> bytes:
    connection.settimeout(_remaining_seconds(deadline))
    return connection.recv(8192)


def _read_health_response(
    port: int,
    deadline: float,
    containment: _ProcessContainment,
) -> bool:
    with socket.create_connection(
        ("127.0.0.1", port),
        timeout=_remaining_seconds(deadline),
    ) as connection:
        owned, reason = _connection_owned_by_containment(
            connection,
            containment,
            deadline,
        )
        if not owned:
            raise _ConnectionOwnershipRejected(reason)
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
    containment: _ProcessContainment,
) -> tuple[bool, bool, str]:
    while time.monotonic() < deadline:
        if not containment.candidate_alive():
            return False, False, "candidate exited before readiness"
        try:
            ready = _read_health_response(port, deadline, containment)
        except _HealthResponseRejected:
            return False, True, ""
        except _ConnectionOwnershipRejected as error:
            return False, False, str(error)
        except (OSError, ValueError, json.JSONDecodeError):
            ready = False
        if ready:
            time.sleep(min(0.05, max(0, deadline - time.monotonic())))
            if not containment.candidate_alive():
                return False, False, "candidate exited after readiness"
            return True, False, ""
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    return False, False, ""


class _OwnershipProxy:
    def __init__(
        self,
        upstream_port: int,
        containment: _ProcessContainment,
        deadline: float,
    ) -> None:
        self._upstream_port = upstream_port
        self._containment = containment
        self._deadline = deadline
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(8)
        self._listener.settimeout(0.1)
        self.port = int(self._listener.getsockname()[1])
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._observed_connections = 0
        self._error = ""
        self._stopped = False

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set() and time.monotonic() < self._deadline:
            try:
                client, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with client:
                try:
                    upstream = socket.create_connection(
                        ("127.0.0.1", self._upstream_port),
                        timeout=_remaining_seconds(self._deadline),
                    )
                except (OSError, TimeoutError):
                    self._error = "probe proxy could not connect to candidate"
                    continue
                with upstream:
                    owned, reason = _connection_owned_by_containment(
                        upstream,
                        self._containment,
                        self._deadline,
                    )
                    if not owned:
                        self._error = reason
                        continue
                    self._observed_connections += 1
                    if not self._relay(client, upstream):
                        return

    def _relay(self, client: socket.socket, upstream: socket.socket) -> bool:
        sources: dict[socket.socket, socket.socket] = {
            client: upstream,
            upstream: client,
        }
        transferred = 0
        while sources and not self._stop.is_set():
            if _deadline_expired(self._deadline):
                self._error = "probe proxy exceeded smoke deadline"
                return False
            try:
                readable, _, _ = select.select(
                    list(sources),
                    [],
                    [],
                    min(0.1, _remaining_seconds(self._deadline)),
                )
            except (OSError, TimeoutError):
                self._error = "probe proxy relay failed"
                return False
            for source in readable:
                destination = sources[source]
                try:
                    content = source.recv(65_536)
                except OSError:
                    content = b""
                if not content:
                    sources.pop(source, None)
                    try:
                        destination.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    continue
                transferred += len(content)
                if transferred > 4 * 1024 * 1024:
                    self._error = "probe proxy exceeded transfer byte limit"
                    return False
                try:
                    destination.settimeout(_remaining_seconds(self._deadline))
                    destination.sendall(content)
                except (OSError, TimeoutError):
                    self._error = "probe proxy relay failed"
                    return False
        return True

    def stop_and_verify(self) -> tuple[bool, str]:
        if not self._stopped:
            self._stopped = True
            self._stop.set()
            try:
                self._listener.close()
            except OSError:
                pass
            self._thread.join(timeout=min(2, max(0, self._deadline - time.monotonic())))
        if self._thread.is_alive():
            return False, "probe ownership proxy did not stop"
        if self._error:
            return False, self._error
        if self._observed_connections < 1:
            return False, "probe connection ownership was not observed"
        return True, ""


def run_clean_start_smoke(
    candidate_root: str | Path,
    report_path: str | Path,
    *,
    timeout_seconds: int = 60,
) -> GateResult:
    """Start, probe, report, and terminate one isolated candidate server."""

    _ensure_supported_platform()
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
    server_command = [sys.executable, "nova_enhanced_server.py", str(port)]
    probe_command = [
        sys.executable,
        "tools/nova_smoke_check.py",
        "--url",
        f"http://127.0.0.1:{port}",
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
    ownership_proxy: _OwnershipProxy | None = None
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

        startup_healthy, health_rejected, ownership_error = _wait_for_health(
            port,
            deadline,
            server_containment,
        )
        if health_rejected:
            launch_error = "health response exceeded its allowed byte boundary"
        elif ownership_error:
            launch_error = ownership_error
        if (
            not startup_healthy
            and not health_rejected
            and server_containment.candidate_alive()
        ):
            timed_out = time.monotonic() >= deadline
        if startup_healthy:
            if not server_containment.candidate_alive():
                startup_healthy = False
                launch_error = "candidate server exited after readiness"
            remaining = deadline - time.monotonic()
            if startup_healthy and remaining <= 0:
                timed_out = True
            elif startup_healthy:
                ownership_proxy = _OwnershipProxy(
                    port,
                    server_containment,
                    deadline,
                )
                ownership_proxy.start()
                probe_command = [
                    sys.executable,
                    "tools/nova_smoke_check.py",
                    "--url",
                    f"http://127.0.0.1:{ownership_proxy.port}",
                ]
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
                ownership_complete, ownership_reason = (
                    ownership_proxy.stop_and_verify()
                )
                server_alive_after_probe = (
                    server_containment.candidate_alive() and ownership_complete
                )
                if not server_alive_after_probe:
                    launch_error = (
                        ownership_reason
                        or "candidate server exited during smoke probe"
                    )
    except OSError as error:
        launch_error = str(error)
    finally:
        containment_complete = True
        capture_complete = True
        proxy_complete = True
        if ownership_proxy is not None:
            proxy_complete, proxy_error = ownership_proxy.stop_and_verify()
            if not proxy_complete and not launch_error:
                launch_error = proxy_error
        if server_containment is not None:
            containment_complete = server_containment.terminate_and_verify()
        if server is not None:
            capture_complete = _finish_capture(server, server_threads)
        cleanup_complete = containment_complete and capture_complete and proxy_complete

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
        command=_redact_command(
            probe_command if startup_healthy else server_command,
            sensitive_paths=sensitive_paths,
        ),
        passed=startup_healthy and probe_passed and cleanup_complete,
        exit_code=exit_code,
        duration_seconds=time.monotonic() - started,
        timed_out=timed_out,
        stdout_tail=stdout,
        stderr_tail=stderr,
    )

    stdout_file = safe_reports.write_text(
        stdout_filename,
        _persisted_log_content(recorded_server_stdout, 65_536),
    )
    stderr_file = safe_reports.write_text(
        stderr_filename,
        _persisted_log_content(recorded_server_stderr, 65_536),
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
