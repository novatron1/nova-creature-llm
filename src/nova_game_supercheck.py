"""Small, deterministic playability check for Nova-created browser games.

This is intentionally separate from the general website quality gate.  A game
needs a render surface, a public runtime state hook, an input path, and a
running loop; checking those signals catches the most common "it built but it
doesn't play" failures without executing arbitrary project code on the server.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote


REPORT_FILE = "game_supercheck_report.json"
GAME_API_RE = re.compile(r"window\.Nova[A-Za-z0-9_$]*\s*=", re.IGNORECASE)
INPUT_RE = re.compile(r"addEventListener\s*\(\s*['\"](?:keydown|keyup|pointerdown|touchstart)", re.IGNORECASE)
LOOP_RE = re.compile(r"requestAnimationFrame\s*\(|set(?:Interval|Timeout)\s*\(", re.IGNORECASE)
WEBGL_RE = re.compile(r"(?:three(?:\.js)?|webgl|canvas|getContext\s*\(\s*['\"]webgl)", re.IGNORECASE)


def is_game_supercheck_request(text: str | None) -> bool:
    normalized = " ".join(str(text or "").lower().split())
    if not normalized:
        return False
    phrases = (
        "check the game",
        "test the game",
        "verify the game",
        "playtest",
        "play test",
        "make sure the game works",
        "does the game work",
        "run a superpowers check",
        "super check the game",
    )
    return any(phrase in normalized for phrase in phrases)


def run_game_supercheck(projects_root: str | Path, project_id: str) -> dict[str, Any]:
    """Inspect one saved game and persist a safe, content-light report."""

    project_dir = _project_dir(projects_root, project_id)
    entry = project_dir / "index.html"
    if not entry.exists():
        raise FileNotFoundError("Game Superpowers Check requires an index.html entry file")
    html = entry.read_text(encoding="utf-8", errors="replace")
    lower = html.lower()
    checks = {
        "entry_file": _check("index.html is present", True),
        "metadata": _check(
            "title and mobile viewport are present",
            bool(re.search(r"<title\b[^>]*>[^<]+</title>", html, re.IGNORECASE))
            and '<meta name="viewport"' in lower,
        ),
        "render_surface": _check(
            "a canvas or game render surface is present",
            bool(re.search(r"<canvas\b|id\s*=\s*['\"][^'\"]*(?:game|canvas|playfield)[^'\"]*['\"]", html, re.IGNORECASE)),
        ),
        "webgl": _check("WebGL or Three.js runtime is referenced", bool(WEBGL_RE.search(html))),
        "playable_api": _check(
            "the game exposes a Nova runtime state API",
            bool(GAME_API_RE.search(html)),
        ),
        "input": _check(
            "keyboard, pointer, or touch input is wired",
            bool(INPUT_RE.search(html)),
        ),
        "runtime_loop": _check("a render or update loop is wired", bool(LOOP_RE.search(html))),
        "responsive": _check(
            "responsive layout signals are present",
            "@media" in lower
            or "max-width" in lower
            or "100vw" in lower
            or "100vh" in lower
            or "resize" in lower,
        ),
        "error_guards": _check(
            "no obvious fatal error markers are embedded",
            not bool(re.search(r"console\.error\s*\(|throw\s+new\s+error\s*\(|debugger\s*;", html, re.IGNORECASE)),
        ),
        "no_placeholders": _check(
            "no placeholder or TODO content is embedded",
            not bool(re.search(r"\b(?:lorem ipsum|placeholder|todo)\b", lower)),
        ),
    }
    failed = [item["detail"] for item in checks.values() if not item["passed"]]
    passed_count = sum(1 for item in checks.values() if item["passed"])
    score = round((passed_count / len(checks)) * 100) if checks else 0
    report: dict[str, Any] = {
        "ok": True,
        "skill": "superpowers_game_check",
        "passed": not failed,
        "score": score,
        "project_id": project_dir.name,
        "project_name": _display_name(project_dir.name),
        "project_url": f"/sandbox/app_builder_projects/{quote(project_dir.name)}/index.html",
        "entry_file": "index.html",
        "checks": checks,
        "blockers": failed,
        "fixes_applied": [],
        "report_file": REPORT_FILE,
    }
    (project_dir / REPORT_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def run_game_supercheck_for_request(text: str | None, projects_root: str | Path) -> dict[str, Any]:
    project_id = select_game_project_id(text, projects_root)
    if not project_id:
        raise FileNotFoundError("No saved browser game was found for the Superpowers Check")
    return run_game_supercheck(projects_root, project_id)


def select_game_project_id(text: str | None, projects_root: str | Path) -> str | None:
    root = Path(projects_root)
    if not root.exists():
        return None
    normalized = " ".join(str(text or "").lower().replace("_", " ").split())
    projects: list[Path] = []
    for project in root.iterdir():
        entry = project / "index.html"
        if not project.is_dir() or not entry.exists():
            continue
        html = entry.read_text(encoding="utf-8", errors="replace")
        if WEBGL_RE.search(html) or GAME_API_RE.search(html) or 'data-renderer="three' in html.lower():
            projects.append(project)
            display = _display_name(project.name).lower()
            if display and display in normalized:
                return project.name
    if not projects:
        return None
    return max(projects, key=lambda path: path.stat().st_mtime).name


def format_game_supercheck_report(report: dict[str, Any]) -> str:
    project_name = report.get("project_name") or report.get("project_id") or "Game"
    status = "passed" if report.get("passed") else "needs work"
    blockers = report.get("blockers") or []
    lines = [
        f"[SUPERPOWERS GAME CHECK] {project_name} {status} ({report.get('score', 0)}/100).",
        "Checks: " + ("all playable checks passed" if not blockers else "; ".join(blockers[:4])),
        "Playtest targets: render surface, input, runtime loop, mobile layout, and error markers.",
    ]
    if report.get("project_url"):
        lines.append("Open: " + str(report["project_url"]))
    lines.append("Report: " + str(report.get("report_file") or REPORT_FILE))
    return "\n".join(lines)


def _check(detail: str, passed: bool) -> dict[str, Any]:
    return {"passed": bool(passed), "detail": detail}


def _project_dir(projects_root: str | Path, project_id: str) -> Path:
    root = Path(projects_root).resolve()
    raw = str(project_id or "")
    if not raw or "/" in raw or "\\" in raw or raw in {".", ".."}:
        raise ValueError("Project id must be a saved game folder name")
    project_dir = (root / raw).resolve()
    try:
        project_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Game project path must stay inside the projects root") from exc
    if not project_dir.exists():
        raise FileNotFoundError(f"Game project not found: {raw}")
    return project_dir


def _display_name(project_id: str) -> str:
    return re.sub(r"\s+", " ", str(project_id).replace("_", " ")).strip() or "Nova Game"
