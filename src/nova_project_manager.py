"""Safe project management helpers for Nova sandbox app builder projects."""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_PROJECTS_URL = "/sandbox/app_builder_projects"
DEFAULT_EXPORTS_URL = "/sandbox/exports"
DEFAULT_DEPLOYMENTS_URL = "/sandbox/deployments"
TEXT_EXTENSIONS = {
    ".bat",
    ".c",
    ".cfg",
    ".cpp",
    ".cs",
    ".csv",
    ".css",
    ".gd",
    ".glsl",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".lua",
    ".md",
    ".meta",
    ".php",
    ".prefab",
    ".ps1",
    ".py",
    ".rb",
    ".rs",
    ".shader",
    ".sh",
    ".svelte",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".unity",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}
MAX_EDITABLE_FILE_BYTES = 2 * 1024 * 1024


def list_projects(projects_root: str | Path) -> list[dict[str, Any]]:
    root = Path(projects_root)
    if not root.exists():
        return []
    projects = []
    for project_dir in root.iterdir():
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue
        entry = project_dir / "index.html"
        file_count = sum(1 for path in project_dir.rglob("*") if path.is_file())
        if file_count == 0:
            continue
        manifest = _read_manifest(project_dir)
        name = str(manifest.get("project_name") or _display_name(project_dir.name))
        pages = manifest.get("pages")
        if isinstance(pages, list):
            page_count = len(pages)
        else:
            page_count = int(manifest.get("page_count") or len(list(project_dir.glob("*.html"))) or 0)
        is_website = entry.exists()
        projects.append(
            {
                "id": project_dir.name,
                "name": name,
                "page_count": page_count,
                "project_type": "website" if is_website else "files",
                "entry_file": "index.html" if is_website else None,
                "open_url": f"{DEFAULT_PROJECTS_URL}/{project_dir.name}/index.html" if is_website else None,
                "modified": datetime.fromtimestamp(project_dir.stat().st_mtime).isoformat(timespec="seconds"),
                "file_count": file_count,
            }
        )
    return sorted(projects, key=lambda item: item["modified"], reverse=True)


def list_project_files(projects_root: str | Path, project_id: str) -> list[dict[str, Any]]:
    project_dir = _project_dir(projects_root, project_id)
    files = []
    for path in project_dir.rglob("*"):
        if not path.is_file() or any(part.startswith(".") for part in path.relative_to(project_dir).parts):
            continue
        rel_path = _to_posix(path.relative_to(project_dir))
        text_file = _is_editable_text_file(path)
        too_large_for_editor = text_file and _is_too_large_for_editor(path)
        editable = text_file and not too_large_for_editor
        editor_block_reason = "" if editable else ("too_large" if too_large_for_editor else "binary")
        files.append(
            {
                "path": rel_path,
                "size": path.stat().st_size,
                "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                "editable": editable,
                "too_large_for_editor": too_large_for_editor,
                "editor_block_reason": editor_block_reason,
            }
        )
    return sorted(files, key=lambda item: item["path"])


def read_project_file(projects_root: str | Path, project_id: str, relative_path: str) -> dict[str, Any]:
    project_dir = _project_dir(projects_root, project_id)
    target = _safe_child_path(project_dir, relative_path)
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("Project file not found")
    if not _is_editable_text_file(target):
        raise ValueError("Only text project files can be opened in edit mode")
    if _is_too_large_for_editor(target):
        raise ValueError(
            f"Project file is too large for the live editor/preview "
            f"({target.stat().st_size} bytes; limit {MAX_EDITABLE_FILE_BYTES} bytes)"
        )
    content = target.read_text(encoding="utf-8", errors="replace")
    return {
        "project_id": project_id,
        "path": _to_posix(target.relative_to(project_dir)),
        "content": content,
        "size": target.stat().st_size,
    }


def write_project_file(
    projects_root: str | Path,
    project_id: str,
    relative_path: str,
    content: str,
) -> dict[str, Any]:
    project_dir = _project_dir(projects_root, project_id)
    target = _safe_child_path(project_dir, relative_path)
    if not _is_editable_text_path(target):
        raise ValueError("Only text project files can be saved in edit mode")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(str(content), encoding="utf-8")
    return {
        "project_id": project_id,
        "path": _to_posix(target.relative_to(project_dir)),
        "size": target.stat().st_size,
        "modified": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
    }


def export_project_zip(
    projects_root: str | Path,
    exports_root: str | Path,
    project_id: str,
) -> dict[str, Any]:
    project_dir = _project_dir(projects_root, project_id)
    export_dir = Path(exports_root)
    export_dir.mkdir(parents=True, exist_ok=True)
    zip_path = (export_dir / f"{project_dir.name}.zip").resolve()
    try:
        zip_path.relative_to(export_dir.resolve())
    except ValueError as exc:
        raise ValueError("Export path must stay inside the exports folder") from exc
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(project_dir.rglob("*")):
            if path.is_file() and not any(part.startswith(".") for part in path.relative_to(project_dir).parts):
                archive.write(path, _to_posix(path.relative_to(project_dir)))
    return {
        "project_id": project_dir.name,
        "zip_path": zip_path,
        "zip_url": f"{DEFAULT_EXPORTS_URL}/{zip_path.name}",
        "size": zip_path.stat().st_size,
    }


def deploy_project(
    projects_root: str | Path,
    deployments_root: str | Path,
    project_id: str,
) -> dict[str, Any]:
    project_dir = _project_dir(projects_root, project_id)
    deploy_root = Path(deployments_root).resolve()
    deploy_root.mkdir(parents=True, exist_ok=True)
    target = (deploy_root / project_dir.name).resolve()
    try:
        target.relative_to(deploy_root)
    except ValueError as exc:
        raise ValueError("Deploy path must stay inside the deployments folder") from exc
    if target.exists():
        if target == deploy_root:
            raise ValueError("Refusing to replace deployment root")
        shutil.rmtree(target)
    shutil.copytree(project_dir, target)
    index_file = target / "index.html"
    return {
        "project_id": project_dir.name,
        "deploy_path": target,
        "deploy_url": f"{DEFAULT_DEPLOYMENTS_URL}/{project_dir.name}/index.html" if index_file.exists() else None,
        "deployed_at": datetime.now().isoformat(timespec="seconds"),
    }


def import_project_zip(
    projects_root: str | Path,
    zip_bytes: bytes,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    root = Path(projects_root)
    root.mkdir(parents=True, exist_ok=True)
    safe_id = _safe_import_project_id(project_id or "Imported_Project")
    project_dir = (root / safe_id).resolve()
    try:
        project_dir.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Imported project path must stay inside the projects folder") from exc
    if project_dir.exists():
        safe_id = _unique_project_id(root, safe_id)
        project_dir = (root / safe_id).resolve()
    project_dir.mkdir(parents=True)
    try:
        with zipfile.ZipFile(_BytesReader(zip_bytes)) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            member_paths = [_safe_zip_member(info.filename) for info in members]
            strip_root = _single_top_level_folder(member_paths)
            for info, member_path in zip(members, member_paths):
                if info.is_dir():
                    continue
                rel_path = _strip_top_folder(member_path) if strip_root else member_path
                target = _safe_child_path(project_dir, rel_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(info))
    except zipfile.BadZipFile as exc:
        shutil.rmtree(project_dir, ignore_errors=True)
        raise ValueError("Import file is not a valid ZIP") from exc
    project_type = "website" if (project_dir / "index.html").exists() else "files"
    return {
        "id": project_dir.name,
        "name": _display_name(project_dir.name),
        "project_type": project_type,
        "open_url": f"{DEFAULT_PROJECTS_URL}/{project_dir.name}/index.html" if project_type == "website" else None,
    }


def import_project_file(
    projects_root: str | Path,
    file_bytes: bytes,
    *,
    filename: str,
    project_id: str | None = None,
) -> dict[str, Any]:
    root = Path(projects_root)
    root.mkdir(parents=True, exist_ok=True)
    safe_filename = _normalize_relative_path(Path(str(filename or "imported_file")).name, "safe project path")
    fallback_id = Path(safe_filename).stem or "Imported_File"
    safe_id = _safe_import_project_id(project_id or fallback_id)
    project_dir = (root / safe_id).resolve()
    try:
        project_dir.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("Imported project path must stay inside the projects folder") from exc
    if project_dir.exists():
        safe_id = _unique_project_id(root, safe_id)
        project_dir = (root / safe_id).resolve()
    project_dir.mkdir(parents=True)
    target = _safe_child_path(project_dir, safe_filename)
    target.write_bytes(bytes(file_bytes))
    project_type = "website" if safe_filename == "index.html" else "files"
    return {
        "id": project_dir.name,
        "name": _display_name(project_dir.name),
        "project_type": project_type,
        "open_url": f"{DEFAULT_PROJECTS_URL}/{project_dir.name}/index.html" if project_type == "website" else None,
    }


class _BytesReader:
    def __init__(self, data: bytes):
        self._data = data

    def seekable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        import io

        if not hasattr(self, "_buffer"):
            self._buffer = io.BytesIO(self._data)
        return self._buffer.seek(offset, whence)

    def tell(self) -> int:
        import io

        if not hasattr(self, "_buffer"):
            self._buffer = io.BytesIO(self._data)
        return self._buffer.tell()

    def read(self, size: int = -1) -> bytes:
        import io

        if not hasattr(self, "_buffer"):
            self._buffer = io.BytesIO(self._data)
        return self._buffer.read(size)


def _project_dir(projects_root: str | Path, project_id: str) -> Path:
    root = Path(projects_root).resolve()
    if not project_id or "/" in project_id or "\\" in project_id or project_id in {".", ".."}:
        raise ValueError("Project id must be a saved project folder name")
    candidate = (root / project_id).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Project path must stay inside the projects folder") from exc
    if not candidate.exists() or not candidate.is_dir():
        raise FileNotFoundError("Project not found")
    return candidate


def _safe_child_path(project_dir: Path, relative_path: str) -> Path:
    posix_path = _normalize_relative_path(relative_path, "safe project path")
    target = (project_dir / posix_path).resolve()
    try:
        target.relative_to(project_dir.resolve())
    except ValueError as exc:
        raise ValueError("File must stay inside a safe project path") from exc
    return target


def _safe_zip_member(member_name: str) -> str:
    return _normalize_relative_path(member_name, "safe zip path")


def _single_top_level_folder(paths: list[str]) -> bool:
    if not paths:
        return False
    split_paths = [PurePosixPath(path).parts for path in paths]
    if not all(len(parts) > 1 for parts in split_paths):
        return False
    top_levels = {parts[0] for parts in split_paths}
    return len(top_levels) == 1


def _strip_top_folder(path: str) -> str:
    parts = PurePosixPath(path).parts
    return _to_posix(PurePosixPath(*parts[1:]))


def _normalize_relative_path(value: str, label: str) -> str:
    cleaned = str(value or "").replace("\\", "/").strip()
    pure = PurePosixPath(cleaned)
    if not cleaned or pure.is_absolute() or ":" in cleaned:
        raise ValueError(f"File must use a {label}")
    if any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"File must use a {label}")
    return _to_posix(pure)


def _safe_import_project_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or "")).strip("_")
    if not safe:
        safe = "Imported_Project"
    return safe[:80]


def _unique_project_id(root: Path, project_id: str) -> str:
    for index in range(2, 1000):
        candidate = f"{project_id}_{index}"
        if not (root / candidate).exists():
            return candidate
    raise ValueError("Could not create a unique imported project name")


def _read_manifest(project_dir: Path) -> dict[str, Any]:
    manifest_path = project_dir / "site_manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}


def _display_name(folder_name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", folder_name)).strip()


def _is_editable_text_path(path: Path) -> bool:
    suffix = path.suffix.casefold()
    return suffix in TEXT_EXTENSIONS or suffix == ""


def _is_editable_text_file(path: Path) -> bool:
    if not _is_editable_text_path(path):
        return False
    if not path.exists():
        return True
    try:
        path.read_bytes()[:4096].decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _is_too_large_for_editor(path: Path) -> bool:
    try:
        return path.exists() and path.stat().st_size > MAX_EDITABLE_FILE_BYTES
    except OSError:
        return False


def _to_posix(path: str | Path | PurePosixPath) -> str:
    return str(path).replace("\\", "/")
