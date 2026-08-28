from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.orchestrator import run_proof_job  # noqa: E402


class _FakePage:
    def __init__(self) -> None:
        self.url = ""
        self._content = ""

    def on(self, *_args, **_kwargs) -> None:
        return None

    def goto(self, url: str, **_kwargs) -> None:
        self.url = url
        parsed = urlparse(url)
        path = Path(parsed.path.lstrip("/"))
        self._content = path.read_text(encoding="utf-8")

    def title(self) -> str:
        if "<title>" in self._content:
            start = self._content.index("<title>") + len("<title>")
            end = self._content.index("</title>")
            return self._content[start:end]
        return "Nova proof"

    def content(self) -> str:
        return self._content

    def screenshot(self, *, path: str, full_page: bool = True) -> None:
        Path(path).write_bytes(b"fake-screenshot")

    def close(self) -> None:
        return None


def _fake_page_factory() -> _FakePage:
    return _FakePage()


def test_end_to_end_proof_job_produces_verified_report(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "app.py").write_text(
        'def answer():\n    return "hello"\n',
        encoding="utf-8",
    )
    (project_root / "test_app.py").write_text(
        "from app import answer\n\n\n"
        "def test_answer():\n"
        '    assert answer() == "hello, nova"\n',
        encoding="utf-8",
    )

    result = run_proof_job(
        project_root=project_root,
        output_dir=tmp_path / "workspace",
        page_factory=_fake_page_factory,
    )

    assert result.report.final_verification["passed"] is True
    assert result.run.state.value == "completed"
    assert Path(result.report_path).exists()
