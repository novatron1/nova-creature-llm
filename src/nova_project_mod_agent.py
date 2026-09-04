"""Loaded-file mod helper for Nova sandbox projects."""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import nova_project_manager as projects


DESTRUCTIVE_PATTERN = re.compile(
    r"\b(delete|destroy|erase|wipe|clear|remove)\b.*\b(file|project|folder|everything|all|whole)\b",
    re.IGNORECASE,
)


def mod_loaded_file(
    projects_root: str | Path,
    project_id: str,
    relative_path: str,
    prompt: str,
) -> dict[str, Any]:
    """Apply a safe chat-style modification to one loaded editable project file."""
    clean_prompt = " ".join(str(prompt or "").split()).strip()
    if not clean_prompt:
        raise ValueError("Tell Nova what to change in the loaded file")
    if DESTRUCTIVE_PATTERN.search(clean_prompt):
        raise ValueError("Destructive loaded-file mods need confirmation first")

    try:
        loaded = projects.read_project_file(projects_root, project_id, relative_path)
    except ValueError as error:
        return _create_asset_mod_plan(projects_root, project_id, relative_path, clean_prompt, str(error))
    original = loaded["content"]
    suffix = Path(relative_path).suffix.casefold()
    content, changes = _apply_prompt(original, suffix, clean_prompt)
    if content == original:
        content = _append_note(original, suffix, clean_prompt)
        changes.append("added a Nova mod note")

    saved = projects.write_project_file(projects_root, project_id, relative_path, content)
    return {
        "project_id": project_id,
        "path": saved["path"],
        "content": content,
        "changed": content != original,
        "summary": "; ".join(changes) if changes else "No safe changes were needed",
        "size": saved["size"],
        "modified": saved["modified"],
    }


def _create_asset_mod_plan(
    projects_root: str | Path,
    project_id: str,
    relative_path: str,
    prompt: str,
    reason: str,
) -> dict[str, Any]:
    plan_path = _asset_plan_path(relative_path)
    content = "\n".join(
        [
            "# Binary or stored asset mod plan",
            "",
            f"Target asset: `{relative_path}`",
            f"Requested change: {prompt}",
            "",
            "Nova kept the original asset untouched because this file cannot be safely rewritten in the live text editor.",
            f"Editor block reason: {reason}",
            "",
            "What to import next:",
            "- The editable source files for the app/site, such as HTML, CSS, JS, Python, Unity, Godot, project folders, or build scripts.",
            "- Any matching asset folders, presets, configs, or documentation that explain how this binary was built.",
            "",
            "Safe mod workflow:",
            "1. Import the source ZIP or folder that created this asset.",
            "2. Ask Nova to make the change against those editable source files.",
            "3. Export or deploy the edited project from Nova.",
            "",
            "If source files are not available, Nova can still help design a replacement web app or write a step-by-step external mod checklist.",
            "",
        ]
    )
    saved = projects.write_project_file(projects_root, project_id, plan_path, content)
    return {
        "project_id": project_id,
        "path": saved["path"],
        "content": content,
        "changed": True,
        "summary": "Created editable mod plan for stored asset; original asset left untouched",
        "size": saved["size"],
        "modified": saved["modified"],
    }


def _asset_plan_path(relative_path: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", str(relative_path or "stored_asset")).strip("_")
    safe_name = safe_name[:96] or "stored_asset"
    return f"nova_mod_requests/{safe_name}_mod_plan.md"


def _apply_prompt(content: str, suffix: str, prompt: str) -> tuple[str, list[str]]:
    lowered = prompt.casefold()
    changes: list[str] = []
    updated = content

    title = _extract_target_text(prompt, ("title", "name", "headline", "heading"))
    if title and suffix in {".html", ".htm", ""}:
        updated = _set_html_title_and_heading(updated, title)
        changes.append(f"set page title to {title}")

    if any(phrase in lowered for phrase in ("button bigger", "buttons bigger", "bigger buttons", "make buttons big", "make the buttons bigger")):
        updated = _add_style(updated, suffix, "buttons", BUTTON_STYLE)
        changes.append("made buttons bigger")

    if any(word in lowered for word in ("dark", "darker", "black background", "night mode")):
        updated = _add_style(updated, suffix, "dark", DARK_STYLE)
        changes.append("added darker visual styling")

    note = _extract_note(prompt)
    if note:
        updated = _append_note(updated, suffix, note)
        changes.append("added note")

    return updated, changes


def _extract_target_text(prompt: str, labels: tuple[str, ...]) -> str:
    label_group = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:change|set|make|rename|update)\b.*?\b(?:{label_group})\b\s+(?:to|as|called)\s+(.+?)(?:\s+\band\b|[.!?]?$)",
        prompt,
        re.IGNORECASE,
    )
    if not match:
        return ""
    return _clean_phrase(match.group(1))


def _extract_note(prompt: str) -> str:
    match = re.search(r"\badd\s+(?:a\s+)?note\s+(?:that\s+)?(.+)", prompt, re.IGNORECASE)
    if not match:
        return ""
    return _clean_phrase(match.group(1))


def _clean_phrase(value: str) -> str:
    cleaned = str(value or "").strip().strip("\"'` ")
    cleaned = re.split(r"\s+\b(?:and|then|also)\b\s+", cleaned, maxsplit=1, flags=re.IGNORECASE)[0]
    return cleaned.strip(" .!?\"'`")


def _set_html_title_and_heading(content: str, title: str) -> str:
    safe_title = html.escape(title)
    updated = content
    if re.search(r"<title\b[^>]*>.*?</title>", updated, re.IGNORECASE | re.DOTALL):
        updated = re.sub(
            r"<title\b[^>]*>.*?</title>",
            f"<title>{safe_title}</title>",
            updated,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    else:
        updated = _inject_before(updated, "</head>", f"<title>{safe_title}</title>")

    if re.search(r"<h1\b[^>]*>.*?</h1>", updated, re.IGNORECASE | re.DOTALL):
        updated = re.sub(
            r"<h1\b[^>]*>.*?</h1>",
            f"<h1>{safe_title}</h1>",
            updated,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    else:
        updated = _inject_before(updated, "</body>", f'<h1 data-nova-mod="title">{safe_title}</h1>')
    return updated


BUTTON_STYLE = (
    "button, .button, [role=\"button\"] { "
    "font-size: 1.1rem; padding: 0.85rem 1rem; min-height: 44px; "
    "}"
)

DARK_STYLE = (
    "body { background: #111827; color: #f8fafc; } "
    ".panel, .card, main, section { border-color: rgba(255,255,255,.18); }"
)


def _add_style(content: str, suffix: str, mod_name: str, css: str) -> str:
    style = f'<style data-nova-mod="{html.escape(mod_name)}">{css}</style>'
    if suffix in {".css"}:
        return content.rstrip() + f"\n\n/* Nova mod: {mod_name} */\n{css}\n"
    if suffix in {".html", ".htm", ""}:
        return _inject_before(content, "</head>", style)
    return content.rstrip() + f"\n\nNova mod CSS ({mod_name}):\n{css}\n"


def _append_note(content: str, suffix: str, note: str) -> str:
    safe_note = html.escape(note)
    if suffix in {".html", ".htm", ""}:
        block = f'<section data-nova-mod="note"><strong>Nova mod note:</strong> {safe_note}</section>'
        return _inject_before(content, "</body>", block)
    comment_prefix = "/*" if suffix in {".css", ".js", ".ts", ".jsx", ".tsx"} else ""
    comment_suffix = " */" if comment_prefix else ""
    return content.rstrip() + f"\n\n{comment_prefix}Nova mod note: {note}{comment_suffix}\n"


def _inject_before(content: str, marker: str, insertion: str) -> str:
    index = content.lower().find(marker.lower())
    if index >= 0:
        return content[:index] + insertion + content[index:]
    return content.rstrip() + insertion
