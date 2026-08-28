from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from nova_runtime.verification_playwright import verify_playwright_page  # noqa: E402


class _FakeMessage:
    def __init__(self, kind: str, text: str) -> None:
        self.type = kind
        self.text = text


class _FakeRequest:
    def __init__(self, url: str) -> None:
        self.url = url


class _FakeLocator:
    def __init__(self, text: str, *, visible: bool = True, count: int = 1) -> None:
        self._text = text
        self._visible = visible
        self._count = count

    def text_content(self):
        return self._text

    def inner_text(self):
        return self._text

    def is_visible(self):
        return self._visible

    def count(self):
        return self._count


class _FakePage:
    def __init__(self) -> None:
        self.url = ""
        self.closed = False
        self._events: dict[str, list] = {}
        self._locators = {
            "body": _FakeLocator("Nova is ready for a browser test."),
            "main": _FakeLocator("Nova main content", visible=True, count=1),
        }

    def on(self, event: str, callback):
        self._events.setdefault(event, []).append(callback)

    def goto(self, url: str, **_kwargs):
        self.url = url
        for callback in self._events.get("request", []):
            callback(_FakeRequest(url))
        for callback in self._events.get("console", []):
            callback(_FakeMessage("log", "browser loaded"))
            callback(_FakeMessage("error", "simulated console issue"))

    def title(self):
        return "Nova Creature"

    def content(self):
        return "<html><body><main>Nova is ready for a browser test.</main></body></html>"

    def locator(self, selector: str):
        return self._locators.get(selector, _FakeLocator("", visible=False, count=0))

    def screenshot(self, *, path: str, full_page: bool = True):
        Path(path).write_bytes(b"fake-png-bytes")

    def close(self):
        self.closed = True


def test_playwright_verification_result_has_artifacts(tmp_path) -> None:
    result = verify_playwright_page(
        "http://127.0.0.1:3000/",
        assertions=[{"type": "text", "selector": "body", "contains": "Nova"}],
        output_dir=tmp_path,
        page_factory=_FakePage,
    )

    assert result.passed is True
    assert result.screenshot_hash
    assert result.dom_hash
    assert result.console_summary["count"] >= 1
    assert result.network_summary["count"] >= 1
    assert result.failure_trace["passed"] is True
    assert result.screenshot_path and Path(result.screenshot_path).exists()


def test_playwright_verification_failure_trace_captures_failed_assertions(tmp_path) -> None:
    result = verify_playwright_page(
        "http://127.0.0.1:3000/",
        assertions=[{"type": "text", "selector": "body", "contains": "missing text"}],
        output_dir=tmp_path,
        page_factory=_FakePage,
    )

    assert result.passed is False
    assert result.failure_trace["passed"] is False
    assert result.failure_trace["failed_assertions"]
    assert result.failure_trace["failed_assertions"][0]["passed"] is False
