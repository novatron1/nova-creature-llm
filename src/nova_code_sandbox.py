"""Isolated subprocess execution for small, authorized Nova code tasks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import Iterable
import uuid


CODE_SANDBOX_VERSION = "1.0"
DEFAULT_ALLOWED_LANGUAGES = frozenset({"python"})
SECRET_FILE_NAMES = {
    ".env",
    ".nova_llm_config",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
    "credentials.json",
}


@dataclass
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    files_created: list[str]
    runtime: float
    timeout_status: bool
    policy_violations: list[str] = field(default_factory=list)
    output_truncated: bool = False
    network_allowed: bool = False
    working_directory_cleaned: bool = True
    memory_limit_supported: bool = False
    version: str = CODE_SANDBOX_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


_BOOTSTRAP = r'''
import builtins
import io
import os
from pathlib import Path
import sys

ROOT = Path.cwd().resolve()
MAX_OUTPUT = int(os.environ.get("NOVA_SANDBOX_OUTPUT_LIMIT", "65536"))

class BoundedWriter(io.TextIOBase):
    def __init__(self, raw):
        self.raw = raw
        self.used = 0
        self.truncated = False
    def writable(self):
        return True
    def write(self, value):
        text = str(value)
        encoded = text.encode("utf-8", errors="replace")
        remaining = max(0, MAX_OUTPUT - self.used)
        if remaining:
            piece = encoded[:remaining].decode("utf-8", errors="ignore")
            self.raw.write(piece)
            self.raw.flush()
            self.used += len(piece.encode("utf-8"))
        if len(encoded) > remaining:
            self.truncated = True
        return len(text)
    def flush(self):
        self.raw.flush()

stdout_writer = BoundedWriter(sys.stdout)
stderr_writer = BoundedWriter(sys.stderr)
sys.stdout = stdout_writer
sys.stderr = stderr_writer

original_open = builtins.open
def confined_open(file, *args, **kwargs):
    if isinstance(file, int):
        return original_open(file, *args, **kwargs)
    target = Path(file)
    if not target.is_absolute():
        target = ROOT / target
    resolved = target.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise PermissionError("NOVA_SANDBOX_POLICY:file_access_outside_sandbox") from exc
    return original_open(resolved, *args, **kwargs)
builtins.open = confined_open

def audit(event, args):
    blocked = (
        event.startswith("socket.")
        or event in {
            "subprocess.Popen",
            "os.system",
            "os.posix_spawn",
            "os.spawn",
            "ctypes.dlopen",
        }
    )
    if blocked:
        raise PermissionError("NOVA_SANDBOX_POLICY:" + event)
sys.addaudithook(audit)

source = original_open(ROOT / "_nova_user_code.py", "r", encoding="utf-8").read()
try:
    exec(compile(source, "_nova_user_code.py", "exec"), {"__name__": "__main__"})
finally:
    marker = ROOT / "_nova_sandbox_status.json"
    original_open(marker, "w", encoding="utf-8").write(
        '{"stdout_truncated":%s,"stderr_truncated":%s}'
        % (str(stdout_writer.truncated).lower(), str(stderr_writer.truncated).lower())
    )
'''


def _safe_input_file(path: Path) -> None:
    lowered = path.name.lower()
    if lowered in SECRET_FILE_NAMES or any(
        marker in lowered for marker in ("secret", "credential", "private_key", "access_token")
    ):
        raise PermissionError(f"Refusing to copy possible secret into sandbox: {path.name}")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(path)


def _posix_limit(memory_limit_mb: int):
    def apply() -> None:
        import resource

        memory = max(32, int(memory_limit_mb)) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        os.setsid()

    return apply


def _terminate_tree(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()


def execute_code(
    code: str,
    *,
    language: str = "python",
    timeout_seconds: int = 10,
    memory_limit_mb: int = 256,
    output_limit_bytes: int = 65_536,
    allowed_files: Iterable[str | Path] = (),
    allowed_languages: Iterable[str] = DEFAULT_ALLOWED_LANGUAGES,
) -> SandboxResult:
    """Run authorized code in a disposable, network-blocked subprocess."""

    selected = str(language or "").strip().lower()
    if selected not in {str(item).lower() for item in allowed_languages}:
        return SandboxResult(
            exit_code=None,
            stdout="",
            stderr="",
            files_created=[],
            runtime=0.0,
            timeout_status=False,
            policy_violations=[f"language_not_allowed:{selected}"],
        )
    if selected != "python":
        return SandboxResult(
            exit_code=None,
            stdout="",
            stderr="",
            files_created=[],
            runtime=0.0,
            timeout_status=False,
            policy_violations=[f"language_not_implemented:{selected}"],
        )
    if len(str(code or "").encode("utf-8")) > 256_000:
        return SandboxResult(
            exit_code=None,
            stdout="",
            stderr="",
            files_created=[],
            runtime=0.0,
            timeout_status=False,
            policy_violations=["code_size_limit"],
        )

    temp_root = Path(tempfile.mkdtemp(prefix="nova-code-"))
    started = time.monotonic()
    stdout = ""
    stderr = ""
    exit_code: int | None = None
    timed_out = False
    violations: list[str] = []
    created: list[str] = []
    truncated = False
    memory_supported = os.name != "nt"
    try:
        (temp_root / "_nova_user_code.py").write_text(str(code or ""), encoding="utf-8")
        (temp_root / "_nova_bootstrap.py").write_text(_BOOTSTRAP, encoding="utf-8")
        input_dir = temp_root / "inputs"
        for raw_path in allowed_files:
            source = Path(raw_path).resolve()
            _safe_input_file(source)
            input_dir.mkdir(exist_ok=True)
            destination = input_dir / source.name
            if destination.exists():
                destination = input_dir / f"{uuid.uuid4().hex[:8]}-{source.name}"
            shutil.copy2(source, destination)

        safe_environment = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "NOVA_SANDBOX_OUTPUT_LIMIT": str(max(1024, int(output_limit_bytes))),
            "PATH": str(Path(sys.executable).parent),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "WINDIR": os.environ.get("WINDIR", ""),
        }
        creationflags = 0
        preexec_fn = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            preexec_fn = _posix_limit(memory_limit_mb)
        process = subprocess.Popen(
            [sys.executable, "-I", "-S", str(temp_root / "_nova_bootstrap.py")],
            cwd=str(temp_root),
            env=safe_environment,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            preexec_fn=preexec_fn,
        )
        try:
            stdout, stderr = process.communicate(timeout=max(1, int(timeout_seconds)))
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_tree(process)
            stdout, stderr = process.communicate(timeout=5)
            exit_code = process.returncode

        for match in re.findall(r"NOVA_SANDBOX_POLICY:([A-Za-z0-9_.-]+)", stderr):
            if match not in violations:
                violations.append(match)
        marker = temp_root / "_nova_sandbox_status.json"
        if marker.exists():
            try:
                status = json.loads(marker.read_text(encoding="utf-8"))
                truncated = bool(
                    status.get("stdout_truncated") or status.get("stderr_truncated")
                )
            except (json.JSONDecodeError, OSError):
                pass
        internal = {
            "_nova_user_code.py",
            "_nova_bootstrap.py",
            "_nova_sandbox_status.json",
        }
        created = sorted(
            path.relative_to(temp_root).as_posix()
            for path in temp_root.rglob("*")
            if path.is_file()
            and path.name not in internal
            and "inputs" not in path.relative_to(temp_root).parts
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return SandboxResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        files_created=created,
        runtime=time.monotonic() - started,
        timeout_status=timed_out,
        policy_violations=violations,
        output_truncated=truncated,
        network_allowed=False,
        working_directory_cleaned=not temp_root.exists(),
        memory_limit_supported=memory_supported,
    )


__all__ = [
    "CODE_SANDBOX_VERSION",
    "DEFAULT_ALLOWED_LANGUAGES",
    "SandboxResult",
    "execute_code",
]
