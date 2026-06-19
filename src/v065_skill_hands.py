"""v065 — Skill Hands

Safe tool hands for Nova: read files, write reports, create sandbox scripts,
run tests, read errors, repair safely. Must not overwrite core files without backup.
"""

from __future__ import annotations

import hashlib, json, shutil, subprocess, sys
from pathlib import Path
from datetime import datetime
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ACTIONS = {
    "read_text_files": {
        "description": "Read text files from the project",
        "blocked": False,
        "requires_backup": False,
    },
    "list_project_files": {
        "description": "List files in the project directory",
        "blocked": False,
        "requires_backup": False,
    },
    "write_reports": {
        "description": "Write reports to reports/ directory",
        "blocked": False,
        "requires_backup": False,
    },
    "create_sandbox_files": {
        "description": "Create files in sandbox/generated_scripts/",
        "blocked": False,
        "requires_backup": False,
    },
    "create_test_files": {
        "description": "Create test and checker files",
        "blocked": False,
        "requires_backup": False,
    },
    "run_allowed_scripts": {
        "description": "Run Python scripts that are in the project",
        "blocked": False,
        "requires_backup": False,
    },
    "summarize_reports": {
        "description": "Summarize report contents",
        "blocked": False,
        "requires_backup": False,
    },
    "compare_hashes": {
        "description": "Compare SHA256 hashes",
        "blocked": False,
        "requires_backup": False,
    },
    "verify_checkpoints": {
        "description": "Verify checkpoint files exist and have content",
        "blocked": False,
        "requires_backup": False,
    },
    "create_backups_before_edits": {
        "description": "Create timestamped backups before overwriting files",
        "blocked": False,
        "requires_backup": False,
    },
}

BLOCKED_ACTIONS = {
    "delete_checkpoints": {
        "description": "Delete checkpoint files",
        "blocked": True,
        "reason": "Checkpoints must be preserved",
    },
    "delete_memory": {
        "description": "Delete memory files",
        "blocked": True,
        "reason": "Memory must be preserved",
    },
    "overwrite_core_without_backup": {
        "description": "Overwrite core files without backup",
        "blocked": True,
        "reason": "Core files require backup before overwriting",
    },
    "run_destructive_shell": {
        "description": "Run destructive shell commands (rm -rf, dd, etc.)",
        "blocked": True,
        "reason": "Destructive shell commands are blocked",
    },
    "run_real_robot_hardware": {
        "description": "Run real robot hardware commands",
        "blocked": True,
        "reason": "Robot hardware must have safety spine, sensors, and approval",
    },
    "install_packages_without_approval": {
        "description": "Install packages without explicit approval",
        "blocked": True,
        "reason": "Package installation requires explicit approval",
    },
    "send_data_outside_project": {
        "description": "Send data outside project without approval",
        "blocked": True,
        "reason": "Data export requires explicit approval",
    },
}


def root() -> Path:
    return ROOT


def is_allowed(action: str) -> bool:
    return action in ALLOWED_ACTIONS and not ALLOWED_ACTIONS[action]["blocked"]


def is_blocked(action: str) -> bool:
    return action in BLOCKED_ACTIONS and BLOCKED_ACTIONS[action]["blocked"]


def check_action(action: str) -> dict[str, Any]:
    if action in ALLOWED_ACTIONS:
        info = ALLOWED_ACTIONS[action]
        return {
            "action": action,
            "allowed": not info["blocked"],
            "blocked": info["blocked"],
            "reason": info["description"],
            "requires_backup": info["requires_backup"],
        }
    if action in BLOCKED_ACTIONS:
        info = BLOCKED_ACTIONS[action]
        return {
            "action": action,
            "allowed": not info["blocked"],
            "blocked": True,
            "reason": info["reason"],
            "requires_backup": False,
        }
    return {"action": action, "allowed": False, "blocked": True, "reason": "Unknown action"}


def create_backup(path: Path) -> Path | None:
    """Create a timestamped backup before overwriting."""
    if not path.exists():
        return None
    backup_dir = ROOT / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"{path.name}.{ts}.bak"
    shutil.copy2(str(path), str(backup_path))
    return backup_path


def sha256(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size < 10:
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def read_file(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def write_report(report_name: str, data: dict[str, Any]) -> Path:
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    path = reports_dir / report_name
    path.write_text(json.dumps(data, indent=2))
    return path


def run_script(script_path: str, args: list[str] | None = None) -> dict[str, Any]:
    """Run a Python script safely."""
    full_path = ROOT / script_path
    if not full_path.exists():
        return {"success": False, "error": f"Script not found: {script_path}"}
    cmd = [sys.executable, str(full_path)] + (args or [])
    try:
        result = subprocess.run(cmd, text=True, capture_output=True, timeout=60, cwd=ROOT)
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-500:],
            "stderr": result.stderr[-200:],
            "error": None if result.returncode == 0 else result.stderr[:200],
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "timeout"}
    except Exception as e:
        return {"success": False, "error": repr(e)}


def list_allowed_actions() -> list[dict[str, Any]]:
    return [{"action": k, **v} for k, v in ALLOWED_ACTIONS.items()]


def list_blocked_actions() -> list[dict[str, Any]]:
    return [{"action": k, **v} for k, v in BLOCKED_ACTIONS.items()]


def main() -> int:
    print("Nova Creature v065 — Skill Hands\n")
    print("ALLOWED ACTIONS:")
    for a in list_allowed_actions():
        print(f"  ✅ {a['action']}: {a['description']}")
    print()
    print("BLOCKED ACTIONS:")
    for a in list_blocked_actions():
        print(f"  ❌ {a['action']}: {a['reason']}")
    print()
    reports_dir = ROOT / "reports"
    reports_dir.mkdir(exist_ok=True)
    (reports_dir / "v065_skill_hands_status.json").write_text(json.dumps({
        "version": "v065_skill_hands",
        "created_at": datetime.now().isoformat(),
        "allowed_actions": list_allowed_actions(),
        "blocked_actions": list_blocked_actions(),
    }, indent=2))
    print("Report: reports/v065_skill_hands_status.json")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
