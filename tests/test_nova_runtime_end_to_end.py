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


def test_proof_job_result_to_dict_is_json_serializable(tmp_path: Path) -> None:
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
    payload = result.to_dict()

    assert payload["run"]["state"] == "completed"
    assert payload["run"]["history"]


# Fixture browser tests exercise orchestration, not real-browser readiness.
import pytest
import subprocess


@pytest.mark.parametrize("failure", ["test", "browser", "app"])
def test_failed_verification_restores_exact_bytes_without_success_memory(tmp_path, failure):
    project = tmp_path / "project"
    project.mkdir()
    original = b'def answer():\r\n    return "hello"\r\n'
    if failure == "app":
        original += b'raise RuntimeError("app failure")\r\n'
    (project / "app.py").write_bytes(original)
    (project / "test_app.py").write_text("def test_result():\n    assert " + str(failure != "test") + "\n")
    class FailedPage(_FakePage):
        def content(self):
            return "wrong result"
    result = run_proof_job(project_root=project, output_dir=tmp_path / "work",
                          page_factory=FailedPage if failure == "browser" else _fake_page_factory)
    assert result.run.state.value == "rolled_back"
    assert result.report.final_verification["passed"] is False
    assert (tmp_path / "work" / "app.py").read_bytes() == original
    assert (project / "app.py").read_bytes() == original
    assert not (tmp_path / "work" / "provenance_memory.jsonl").exists()
    assert result.report.rollback_information["restored"] is True
    assert result.run.contract.metadata["isolation"]["os_sandbox"] is False


def test_pytest_subprocess_has_finite_timeout(tmp_path, monkeypatch):
    from nova_runtime import orchestrator
    def fake_run(*args, **kwargs):
        assert 0 < kwargs["timeout"] <= 300
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = orchestrator._run_pytest(tmp_path)
    assert result.returncode != 0
    assert "timeout" in result.stderr.lower()


def test_bounded_process_terminates_sleeping_child(tmp_path):
    from nova_runtime.orchestrator import _run_bounded
    result = _run_bounded([sys.executable, "-c", "import time; time.sleep(10)"], tmp_path, 0.1)
    assert result.returncode == 124


def test_verification_exception_restores_original(tmp_path, monkeypatch):
    from nova_runtime import orchestrator
    project = tmp_path / "project"
    project.mkdir()
    original = b'def answer():\n    return "hello"\n'
    (project / "app.py").write_bytes(original)
    def fail(*args, **kwargs):
        raise OSError("verification disk error")
    monkeypatch.setattr(orchestrator, "verify_playwright_page", fail)
    with pytest.raises(OSError, match="verification disk error"):
        run_proof_job(project_root=project, output_dir=tmp_path / "work")
    assert (tmp_path / "work" / "app.py").read_bytes() == original
