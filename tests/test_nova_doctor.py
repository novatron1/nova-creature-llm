from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.nova_doctor import build_report, check_port, check_path  # noqa: E402


def test_doctor_reports_writable_existing_path_without_secrets(tmp_path: Path) -> None:
    report = build_report(
        root=tmp_path,
        checks=[
            check_path("workspace", tmp_path, required=True),
            check_path("missing-model", tmp_path / "missing", required=False),
        ],
    )

    assert report["ok"] is True
    assert report["checks"][0]["status"] == "ok"
    assert report["checks"][1]["status"] == "optional_missing"
    serialized = str(report)
    assert "api_key" not in serialized.lower()
    assert "password" not in serialized.lower()


def test_doctor_marks_unavailable_required_port(tmp_path: Path) -> None:
    report = build_report(
        root=tmp_path,
        checks=[check_port("Nova", "127.0.0.1", 1, required=True)],
    )

    assert report["ok"] is False
    assert report["checks"][0]["status"] in {"unreachable", "error"}

