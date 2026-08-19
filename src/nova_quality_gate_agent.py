from __future__ import annotations

import json
import re
import textwrap
from datetime import datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


DEFAULT_PROJECTS_URL = "/sandbox/app_builder_projects"
REPORT_FILE = "quality_gate_report.json"
SCREENSHOT_DIR = "quality_gate_screenshots"
VISUAL_VIEWPORTS = (
    {"name": "desktop", "width": 1366, "height": 768},
    {"name": "mobile", "width": 390, "height": 844},
)
HTML_LINK_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
TITLE_RE = re.compile(r"<title>[^<]+</title>", re.IGNORECASE)
HEAD_RE = re.compile(r"<head\b[^>]*>", re.IGNORECASE)


def is_quality_gate_request(text: str | None) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return False
    phrases = (
        "quality gate",
        "quality check",
        "run quality",
        "check every page",
        "test every page",
        "prove the website",
        "prove the site",
        "verify the website",
        "verify the site",
    )
    return any(phrase in normalized for phrase in phrases)


def run_quality_gate_for_request(
    text: str | None,
    projects_root: str | Path,
    *,
    fix: bool = True,
) -> dict[str, Any]:
    project_id = select_project_id(text, projects_root)
    if not project_id:
        raise FileNotFoundError("No saved website project found for the Quality Gate Agent")
    return run_quality_gate(projects_root, project_id, fix=fix)


def select_project_id(text: str | None, projects_root: str | Path) -> str | None:
    root = Path(projects_root)
    if not root.exists():
        return None
    raw = str(text or "")
    match = re.search(r"/sandbox/app_builder_projects/([^/\s]+)/", raw)
    if match:
        return unquote(match.group(1))
    projects = [path for path in root.iterdir() if path.is_dir() and (path / "index.html").exists()]
    if not projects:
        return None
    normalized = _normalize(raw).replace("-", " ")
    for project in projects:
        candidates = {
            _normalize(project.name),
            _normalize(project.name.replace("_", " ")),
            _normalize(_display_name(project.name)),
        }
        if any(candidate and candidate in normalized for candidate in candidates):
            return project.name
    return max(projects, key=lambda path: path.stat().st_mtime).name


def run_quality_gate(
    projects_root: str | Path,
    project_id: str,
    *,
    fix: bool = False,
    visual: bool = True,
) -> dict[str, Any]:
    project_dir = _project_dir(projects_root, project_id)
    if not (project_dir / "index.html").exists():
        raise FileNotFoundError("Quality Gate requires an index.html website project")
    if fix:
        fixes = _apply_basic_fixes(project_dir)
    else:
        fixes = []
    report = _inspect_project(project_dir, visual=visual)
    report["fixes_applied"] = fixes
    report["generated_at"] = datetime.now().isoformat(timespec="seconds")
    report["report_file"] = REPORT_FILE
    (project_dir / REPORT_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def format_quality_gate_report(report: dict[str, Any]) -> str:
    project_name = report.get("project_name") or report.get("project_id") or "Project"
    blockers = report.get("blockers") or []
    lines = [
        f"[QUALITY GATE] {project_name} {'passed' if report.get('passed') else 'needs work'} ({report.get('score', 0)}/100).",
        f"Pages inspected: {report.get('pages_inspected', 0)}",
        f"Links checked: {report.get('links_checked', 0)}",
        f"Visual snapshots: {report.get('visuals_created', 0)}",
        "Blockers: " + ("none" if not blockers else "; ".join(blockers[:4])),
    ]
    fixes = report.get("fixes_applied") or []
    if fixes:
        lines.append("Auto-fixes: " + ", ".join(fixes[:8]))
    if report.get("project_url"):
        lines.append("Open: " + report["project_url"])
    visuals = [visual for visual in report.get("visuals", []) if visual.get("screenshot_url")]
    if visuals:
        lines.append("Visual proof:")
        for visual in visuals[:4]:
            lines.append(f"  - {visual.get('page', 'page')} {visual.get('viewport', '')}: {visual['screenshot_url']}")
    if report.get("report_file"):
        lines.append("Report: " + report["report_file"])
    return "\n".join(lines)


def _inspect_project(project_dir: Path, *, visual: bool = True) -> dict[str, Any]:
    pages = _discover_pages(project_dir)
    page_reports = [_inspect_page(project_dir, page) for page in pages]
    internal_links = _collect_internal_links(project_dir, pages)
    missing_links = [link for link in internal_links if not (project_dir / link["target"]).exists()]
    visuals = _create_visual_snapshots(project_dir, pages) if visual else []
    expected_visuals = len(pages) * len(VISUAL_VIEWPORTS) if visual else 0
    blank_visuals = [item for item in visuals if item["blank"]]
    overflow_visuals = [item for item in visuals if item["overflow_risk"]]
    console_visuals = [item for item in visuals if item["console_error_risk"]]
    checks = [
        _check("index page exists", (project_dir / "index.html").exists(), "index.html is present"),
        _check("html pages discovered", bool(pages), f"{len(pages)} HTML page(s) found"),
        _check("title on every page", all(page["has_title"] for page in page_reports), _page_detail(page_reports, "missing title", "has_title")),
        _check("viewport on every page", all(page["has_viewport"] for page in page_reports), _page_detail(page_reports, "missing viewport", "has_viewport")),
        _check("favicon on every page", all(page["has_favicon"] for page in page_reports), _page_detail(page_reports, "missing favicon", "has_favicon")),
        _check("h1 on every page", all(page["has_h1"] for page in page_reports), _page_detail(page_reports, "missing h1", "has_h1")),
        _check("main landmark on every page", all(page["has_main"] for page in page_reports), _page_detail(page_reports, "missing main landmark", "has_main")),
        _check("responsive css on every page", all(page["has_responsive_css"] for page in page_reports), _page_detail(page_reports, "missing responsive css", "has_responsive_css")),
        _check("internal links resolve", not missing_links, _missing_link_detail(missing_links)),
        _check("no placeholder content", all(not page["has_placeholder"] for page in page_reports), _page_detail(page_reports, "placeholder text found", "has_placeholder", invert=True)),
        _check("visual snapshots created", (not visual) or len(visuals) == expected_visuals, f"{len(visuals)} of {expected_visuals} snapshots created"),
        _check("no blank visual pages", not blank_visuals, _visual_detail(blank_visuals, "blank visual pages")),
        _check("no horizontal overflow risk", not overflow_visuals, _visual_detail(overflow_visuals, "horizontal overflow risk")),
        _check("no console error risk", not console_visuals, _visual_detail(console_visuals, "console error risk")),
    ]
    blockers = [item["detail"] for item in checks if not item["passed"]]
    passed_count = sum(1 for item in checks if item["passed"])
    score = round((passed_count / len(checks)) * 100) if checks else 0
    return {
        "ok": True,
        "passed": all(item["passed"] for item in checks),
        "score": score,
        "project_id": project_dir.name,
        "project_name": _display_name(project_dir.name),
        "project_url": f"{DEFAULT_PROJECTS_URL}/{project_dir.name}/index.html",
        "pages_inspected": len(pages),
        "links_checked": len(internal_links),
        "pages": page_reports,
        "visuals": visuals,
        "visuals_created": len(visuals),
        "visual_snapshot_dir": SCREENSHOT_DIR,
        "checks": checks,
        "blockers": blockers,
    }


def _inspect_page(project_dir: Path, page: Path) -> dict[str, Any]:
    html = page.read_text(encoding="utf-8", errors="replace")
    rel = _to_posix(page.relative_to(project_dir))
    lower = html.lower()
    return {
        "file": rel,
        "has_title": bool(TITLE_RE.search(html)),
        "has_viewport": '<meta name="viewport"' in lower,
        "has_favicon": 'rel="icon"' in lower or "rel='icon'" in lower,
        "has_h1": bool(re.search(r"<h1\b", html, re.IGNORECASE)),
        "has_main": bool(re.search(r"<main\b", html, re.IGNORECASE)),
        "has_responsive_css": _has_responsive_css(html),
        "has_placeholder": bool(re.search(r"\b(lorem ipsum|todo|placeholder)\b", lower)),
    }


def _create_visual_snapshots(project_dir: Path, pages: list[Path]) -> list[dict[str, Any]]:
    snapshot_dir = project_dir / SCREENSHOT_DIR
    snapshot_dir.mkdir(exist_ok=True)
    visuals = []
    for page in pages:
        rel = _to_posix(page.relative_to(project_dir))
        html = page.read_text(encoding="utf-8", errors="replace")
        title = _extract_title(html) or _display_name(project_dir.name)
        heading = _extract_h1(html) or title
        body_text = _extract_body_text(html)
        body_words = re.findall(r"[A-Za-z0-9]+", body_text)
        blank = len(body_words) < 2
        for viewport in VISUAL_VIEWPORTS:
            filename = f"{_safe_snapshot_name(rel)}-{viewport['name']}.svg"
            snapshot = snapshot_dir / filename
            overflow_risk = _has_overflow_risk(html, int(viewport["width"]))
            console_error_risk = bool(re.search(r"\b(console\.error|throw\s+new\s+Error|debugger;)\b", html, re.IGNORECASE))
            snapshot.write_text(
                _render_snapshot_svg(
                    project_name=_display_name(project_dir.name),
                    page=rel,
                    title=title,
                    heading=heading,
                    body_text=body_text,
                    viewport=viewport,
                    blank=blank,
                    overflow_risk=overflow_risk,
                    console_error_risk=console_error_risk,
                ),
                encoding="utf-8",
            )
            screenshot_file = f"{SCREENSHOT_DIR}/{filename}"
            visuals.append(
                {
                    "page": rel,
                    "viewport": viewport["name"],
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "screenshot_file": screenshot_file,
                    "screenshot_url": f"{DEFAULT_PROJECTS_URL}/{project_dir.name}/{screenshot_file}",
                    "blank": blank,
                    "overflow_risk": overflow_risk,
                    "console_error_risk": console_error_risk,
                }
            )
    return visuals


def _render_snapshot_svg(
    *,
    project_name: str,
    page: str,
    title: str,
    heading: str,
    body_text: str,
    viewport: dict[str, Any],
    blank: bool,
    overflow_risk: bool,
    console_error_risk: bool,
) -> str:
    width = int(viewport["width"])
    height = int(viewport["height"])
    label = f"{viewport['name']} {width}x{height}"
    status = "needs review" if blank or overflow_risk or console_error_risk else "pass"
    preview_text = body_text if body_text else "No visible body text detected."
    wrapped = textwrap.wrap(preview_text, width=72 if width > 700 else 36)[:12]
    lines = [
        (48, project_name, 26, "#f7f7ff", "700"),
        (88, page, 16, "#aeb7ff", "500"),
        (136, title, 22, "#ffffff", "700"),
        (176, heading, 18, "#d7d8ff", "600"),
    ]
    y = 228
    for line in wrapped:
        lines.append((y, line, 15, "#d8d8ec", "400"))
        y += 28
    badges = [
        ("blank", blank),
        ("overflow", overflow_risk),
        ("console", console_error_risk),
    ]
    text_nodes = "\n".join(
        f'<text x="40" y="{line_y}" font-size="{font_size}" fill="{fill}" font-weight="{weight}">{html_escape(text)}</text>'
        for line_y, text, font_size, fill, weight in lines
    )
    badge_nodes = []
    x = 40
    for name, failed in badges:
        fill = "#4f1d33" if failed else "#173d2a"
        stroke = "#ff8f8f" if failed else "#59d889"
        label_text = f"{name}: {'fail' if failed else 'pass'}"
        badge_width = max(96, 58 + len(label_text) * 7)
        badge_nodes.append(
            f'<rect x="{x}" y="{height - 74}" width="{badge_width}" height="34" rx="17" fill="{fill}" stroke="{stroke}" />'
        )
        badge_nodes.append(
            f'<text x="{x + 16}" y="{height - 52}" font-size="13" fill="#f4f4ff">{html_escape(label_text)}</text>'
        )
        x += badge_width + 12
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{html_escape(page)} visual quality proof">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0b0b16"/>
    <stop offset="1" stop-color="#201729"/>
  </linearGradient>
</defs>
<rect width="100%" height="100%" fill="url(#bg)"/>
<rect x="20" y="20" width="{width - 40}" height="{height - 40}" rx="18" fill="#121224" stroke="#5c5cc8"/>
<text x="{width - 40}" y="54" text-anchor="end" font-size="14" fill="#8ff0b3">visual quality gate: {status}</text>
<text x="{width - 40}" y="82" text-anchor="end" font-size="13" fill="#aeb0dc">{html_escape(label)}</text>
{text_nodes}
{''.join(badge_nodes)}
</svg>
"""


def _extract_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _collapse_text(match.group(1)) if match else ""


def _extract_h1(html: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    return _collapse_text(match.group(1)) if match else ""


def _extract_body_text(html: str) -> str:
    match = re.search(r"<body\b[^>]*>(.*?)</body>", html, re.IGNORECASE | re.DOTALL)
    source = match.group(1) if match else html
    source = re.sub(r"<(script|style|svg|canvas)\b.*?</\1>", " ", source, flags=re.IGNORECASE | re.DOTALL)
    source = re.sub(r"<[^>]+>", " ", source)
    return _collapse_text(source)


def _collapse_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


def _safe_snapshot_name(page: str) -> str:
    stem = re.sub(r"\.html?$", "", page, flags=re.IGNORECASE) or "index"
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem.replace("/", "__"))
    return stem.strip("_") or "index"


def _has_overflow_risk(html: str, viewport_width: int) -> bool:
    lower = html.lower()
    responsive = _has_responsive_css(html) or "max-width:100%" in lower or "max-width: 100%" in lower
    fixed_widths = [int(value) for value in re.findall(r"(?:width|min-width)\s*:\s*(\d{3,5})px", html, re.IGNORECASE)]
    fixed_widths.extend(int(value) for value in re.findall(r"\bwidth=[\"'](\d{3,5})[\"']", html, re.IGNORECASE))
    if any(width > viewport_width for width in fixed_widths) and not responsive:
        return True
    if viewport_width < 600 and not responsive:
        tokens = re.findall(r"[^\s<>]{48,}", _extract_body_text(html))
        return bool(tokens)
    return False


def _visual_detail(visuals: list[dict[str, Any]], label: str) -> str:
    if not visuals:
        return "all visual checks pass"
    return label + ": " + ", ".join(f"{item['page']} {item['viewport']}" for item in visuals[:5])


def _discover_pages(project_dir: Path) -> list[Path]:
    manifest_pages = _manifest_pages(project_dir)
    pages = []
    for rel in manifest_pages:
        path = (project_dir / rel).resolve()
        try:
            path.relative_to(project_dir.resolve())
        except ValueError:
            continue
        if path.exists() and path.suffix.lower() == ".html":
            pages.append(path)
    if not pages:
        pages = sorted(path for path in project_dir.glob("*.html") if path.is_file())
    return sorted(dict.fromkeys(pages), key=lambda path: _to_posix(path.relative_to(project_dir)))


def _manifest_pages(project_dir: Path) -> list[str]:
    manifest = project_dir / "site_manifest.json"
    if not manifest.exists():
        return []
    try:
        loaded = json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:
        return []
    pages = loaded.get("pages", []) if isinstance(loaded, dict) else []
    results = []
    for page in pages:
        if isinstance(page, dict) and page.get("file"):
            results.append(str(page["file"]))
        elif isinstance(page, str):
            results.append(page)
    return results


def _collect_internal_links(project_dir: Path, pages: list[Path]) -> list[dict[str, str]]:
    links = []
    for page in pages:
        html = page.read_text(encoding="utf-8", errors="replace")
        for match in HTML_LINK_RE.finditer(html):
            href = match.group(1).strip()
            target = _internal_target(project_dir, page, href)
            if target:
                links.append({"source": _to_posix(page.relative_to(project_dir)), "href": href, "target": target})
    return links


def _internal_target(project_dir: Path, page: Path, href: str) -> str | None:
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    parsed = urlparse(href)
    if parsed.scheme or parsed.netloc:
        return None
    raw_path = unquote(parsed.path or "")
    if not raw_path:
        return None
    target = (project_dir / raw_path.lstrip("/")).resolve() if raw_path.startswith("/") else (page.parent / raw_path).resolve()
    try:
        target.relative_to(project_dir.resolve())
    except ValueError:
        return _to_posix(Path(raw_path))
    return _to_posix(target.relative_to(project_dir))


def _apply_basic_fixes(project_dir: Path) -> list[str]:
    fixes = []
    for page in _discover_pages(project_dir):
        html = page.read_text(encoding="utf-8", errors="replace")
        original = html
        title = _display_name(project_dir.name)
        if "<head" not in html.lower():
            html = re.sub(r"<html\b[^>]*>", lambda m: m.group(0) + "\n<head></head>", html, count=1, flags=re.IGNORECASE)
        if not TITLE_RE.search(html):
            html = _insert_into_head(html, f"<title>{title}</title>")
            fixes.append("metadata:title")
        if '<meta name="viewport"' not in html.lower():
            html = _insert_into_head(html, '<meta name="viewport" content="width=device-width, initial-scale=1">')
            fixes.append("metadata:viewport")
        if 'rel="icon"' not in html.lower() and "rel='icon'" not in html.lower():
            html = _insert_into_head(html, '<link rel="icon" href="data:,">')
            fixes.append("metadata:favicon")
        if not _has_responsive_css(html):
            html = _insert_into_head(
                html,
                "<style>@media (max-width: 720px){body{overflow-wrap:anywhere;}img,canvas,video{max-width:100%;height:auto;}}</style>",
            )
            fixes.append("responsive:mobile_media_query")
        if html != original:
            page.write_text(html, encoding="utf-8")
    return sorted(dict.fromkeys(fixes))


def _insert_into_head(html: str, snippet: str) -> str:
    match = HEAD_RE.search(html)
    if match:
        return html[: match.end()] + "\n  " + snippet + html[match.end() :]
    return snippet + "\n" + html


def _has_responsive_css(html: str) -> bool:
    lower = html.lower()
    return "@media" in lower or "clamp(" in lower or "minmax(" in lower


def _project_dir(projects_root: str | Path, project_id: str) -> Path:
    root = Path(projects_root).resolve()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise ValueError("Project id must be a saved project folder name")
    project_dir = (root / project_id).resolve()
    try:
        project_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("Project path must stay inside the projects folder") from exc
    if not project_dir.exists() or not project_dir.is_dir():
        raise FileNotFoundError("Project not found")
    return project_dir


def _check(name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "detail": detail}


def _page_detail(page_reports: list[dict[str, Any]], label: str, key: str, *, invert: bool = False) -> str:
    matches = [page["file"] for page in page_reports if bool(page[key]) is invert]
    return "all pages pass" if not matches else label + ": " + ", ".join(matches[:5])


def _missing_link_detail(missing_links: list[dict[str, str]]) -> str:
    if not missing_links:
        return "all internal links resolve"
    return "missing links: " + "; ".join(f"{link['source']} -> {link['href']}" for link in missing_links[:5])


def _display_name(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ")).strip().title()


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").casefold()).strip()


def _to_posix(path: Path) -> str:
    return path.as_posix()
