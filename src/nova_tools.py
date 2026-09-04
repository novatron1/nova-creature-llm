"""
Safe tool registry for Nova's agentic wrapper.

Tools are intentionally narrow. Read-only project tools are allowed by default.
Writes require explicit approval. Shell/web tools are disabled unless config
allows them, and still require approval when enabled.
"""

from __future__ import annotations

from pathlib import Path
import os
import re
import shlex
import subprocess
from typing import Any

from nova_agentic_core import AgentTool, get_agent_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", ".pytest_cache"}
SECRET_NAMES = {
    ".env",
    ".nova_llm_config",
    "id_rsa",
    "id_dsa",
    "known_hosts",
}
SECRET_MARKERS = ("secret", "token", "credential", "credentials", "password", "cookie")
ALLOWLISTED_TEST_COMMANDS = {
    "py -m pytest -p no:cacheprovider",
    "py -m pytest tests/test_nova_agentic_core.py -p no:cacheprovider",
    "py -m pytest tests\\test_nova_agentic_core.py -p no:cacheprovider",
}
DESTRUCTIVE_COMMAND_RE = re.compile(
    r"(?i)\b(rm|del|erase|format|shutdown|restart-computer|stop-computer|reg\s+delete|git\s+reset|git\s+clean|"
    r"pip\s+install|npm\s+install|winget\s+install|curl\s+.*(?:token|key)|Invoke-WebRequest\s+.*(?:token|key))\b"
)


def _is_secret_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if any(name.lower() in parts for name in SECRET_NAMES):
        return True
    lowered = str(path).lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def _resolve_project_path(path_value: str | os.PathLike | None) -> Path:
    raw = str(path_value or ".").strip()
    if not raw:
        raw = "."
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    resolved_root = PROJECT_ROOT.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError:
        raise ValueError("Blocked path outside Nova project root.")
    if _is_secret_path(resolved):
        raise ValueError("Blocked path that may contain secrets or credentials.")
    return resolved


def read_project_file(args: dict[str, Any]) -> dict:
    path = _resolve_project_path(args.get("path"))
    max_bytes = int(args.get("max_bytes", 50000))
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Project file not found: {args.get('path')}")
    data = path.read_bytes()[:max_bytes]
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        content = data.decode("utf-8", errors="replace")
    return {
        "ok": True,
        "path": path.relative_to(PROJECT_ROOT.resolve()).as_posix(),
        "content": content,
        "truncated": path.stat().st_size > max_bytes,
    }


def list_project_files(args: dict[str, Any]) -> dict:
    start = _resolve_project_path(args.get("path") or ".")
    max_files = int(args.get("max_files", 100))
    if not start.exists():
        raise FileNotFoundError(f"Project path not found: {args.get('path')}")
    files = []
    if start.is_file():
        candidates = [start]
    else:
        candidates = []
        for root, dirs, names in os.walk(start):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not _is_secret_path(Path(root) / d)]
            for name in names:
                candidates.append(Path(root) / name)
                if len(candidates) >= max_files:
                    break
            if len(candidates) >= max_files:
                break
    for path in candidates[:max_files]:
        if _is_secret_path(path):
            continue
        try:
            rel = path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
        except ValueError:
            continue
        files.append({"path": rel, "size": path.stat().st_size, "is_file": path.is_file()})
    return {"ok": True, "root": str(PROJECT_ROOT.resolve()), "files": files}


def search_project_text(args: dict[str, Any]) -> dict:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("search_project_text requires a query.")
    start = _resolve_project_path(args.get("path") or ".")
    max_results = int(args.get("max_results", 20))
    matches = []
    haystack_root = start if start.is_dir() else start.parent
    for root, dirs, names in os.walk(haystack_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not _is_secret_path(Path(root) / d)]
        for name in names:
            path = Path(root) / name
            if _is_secret_path(path) or path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".exe", ".dll", ".pyc"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for line_no, line in enumerate(text.splitlines(), start=1):
                if query.lower() in line.lower():
                    matches.append(
                        {
                            "path": path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix(),
                            "line": line_no,
                            "text": line[:300],
                        }
                    )
                    break
            if len(matches) >= max_results:
                return {"ok": True, "query": query, "matches": matches}
    return {"ok": True, "query": query, "matches": matches}


def write_project_file(args: dict[str, Any]) -> dict:
    path = _resolve_project_path(args.get("path"))
    content = str(args.get("content") or "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": path.relative_to(PROJECT_ROOT.resolve()).as_posix(),
        "bytes_written": len(content.encode("utf-8")),
    }


def run_project_tests(args: dict[str, Any]) -> dict:
    command = str(args.get("command") or "py -m pytest -p no:cacheprovider").strip()
    if command not in ALLOWLISTED_TEST_COMMANDS:
        raise PermissionError("Test command is not allowlisted.")
    completed = subprocess.run(
        shlex.split(command, posix=False),
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=int(args.get("timeout", 120)),
    )
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_shell_command(args: dict[str, Any]) -> dict:
    command = str(args.get("command") or "").strip()
    if not command:
        raise ValueError("run_shell_command requires a command.")
    if DESTRUCTIVE_COMMAND_RE.search(command):
        raise PermissionError("Blocked destructive or credential-risk shell command.")
    completed = subprocess.run(
        shlex.split(command, posix=False),
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        timeout=int(args.get("timeout", 30)),
    )
    return {
        "ok": completed.returncode == 0,
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def web_search(args: dict[str, Any]) -> dict:
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("web_search requires a query.")
    return {
        "ok": False,
        "query": query,
        "message": "Web search is disabled in the local safe tool registry unless an external connector is enabled.",
    }


def get_tool_registry() -> dict[str, AgentTool]:
    return {
        "read_project_file": AgentTool(
            name="read_project_file",
            description="Read a file inside the Nova project folder.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            risk_level="safe",
            requires_approval=False,
            callable=read_project_file,
        ),
        "list_project_files": AgentTool(
            name="list_project_files",
            description="List files inside the Nova project folder.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            risk_level="safe",
            requires_approval=False,
            callable=list_project_files,
        ),
        "search_project_text": AgentTool(
            name="search_project_text",
            description="Search text inside files in the Nova project folder.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}, "path": {"type": "string"}}},
            risk_level="safe",
            requires_approval=False,
            callable=search_project_text,
        ),
        "write_project_file": AgentTool(
            name="write_project_file",
            description="Write a file inside the Nova project folder.",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}},
            risk_level="high",
            requires_approval=True,
            callable=write_project_file,
        ),
        "run_project_tests": AgentTool(
            name="run_project_tests",
            description="Run approved project test commands.",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            risk_level="medium",
            requires_approval=True,
            callable=run_project_tests,
        ),
        "run_shell_command": AgentTool(
            name="run_shell_command",
            description="Run a shell command. Disabled by default.",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            risk_level="high",
            requires_approval=True,
            callable=run_shell_command,
        ),
        "web_search": AgentTool(
            name="web_search",
            description="Search the web. Disabled by default.",
            input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
            risk_level="medium",
            requires_approval=True,
            callable=web_search,
        ),
    }


def validate_tool_call(tool_name: str, args: dict[str, Any] | None, state=None) -> dict:
    config = getattr(state, "config", None) or get_agent_config()
    registry = get_tool_registry()
    tool = registry.get(tool_name)
    if not tool:
        return {"allowed": False, "approval_required": False, "reason": f"Unknown tool: {tool_name}"}

    args = args or {}
    approval_granted = bool(getattr(state, "approval_granted", False))

    if tool_name == "run_shell_command":
        if not config.allow_shell:
            return {"allowed": False, "approval_required": False, "reason": "Shell tool is disabled by default."}
        command = str(args.get("command") or "")
        if DESTRUCTIVE_COMMAND_RE.search(command):
            return {"allowed": False, "approval_required": False, "reason": "Blocked destructive shell command."}

    if tool_name == "web_search" and not config.allow_web:
        return {"allowed": False, "approval_required": False, "reason": "Web search tool is disabled by default."}

    if tool_name in {"read_project_file", "list_project_files", "search_project_text", "write_project_file"}:
        try:
            _resolve_project_path(args.get("path") or ".")
        except Exception as exc:
            return {"allowed": False, "approval_required": False, "reason": str(exc)}

    if tool_name == "run_project_tests":
        command = str(args.get("command") or "py -m pytest -p no:cacheprovider").strip()
        if command in ALLOWLISTED_TEST_COMMANDS:
            return {"allowed": True, "approval_required": False, "reason": "Allowlisted test command."}

    if tool.requires_approval and config.require_approval and not approval_granted:
        return {
            "allowed": False,
            "approval_required": True,
            "reason": f"{tool_name} is {tool.risk_level} risk and requires approval.",
        }

    return {"allowed": True, "approval_required": False, "reason": "Allowed."}

