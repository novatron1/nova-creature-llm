from __future__ import annotations

import json
import mimetypes
from pathlib import Path
from urllib.parse import unquote


def resolve_confined_path(root: Path, request_path: str) -> Path:
    root = root.resolve()
    relative = unquote(request_path).lstrip("/") or "index.html"
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError("Path escapes configured root")
    return target


def content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def encode_json(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
