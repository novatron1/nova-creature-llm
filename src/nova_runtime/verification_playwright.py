"""Playwright-backed browser verification with evidence artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from .contracts import canonical_json, sha256_json


@dataclass(frozen=True, slots=True)
class AssertionOutcome:
    assertion: dict[str, Any]
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PlaywrightVerificationResult:
    url: str
    passed: bool
    page_title: str
    screenshot_path: str | None
    screenshot_hash: str
    dom_hash: str
    console_summary: dict[str, Any]
    network_summary: dict[str, Any]
    failure_trace: dict[str, Any]
    assertions: list[AssertionOutcome] = field(default_factory=list)
    elapsed_ms: float = 0.0
    verified_at: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["assertions"] = [item.to_dict() for item in self.assertions]
        return data


def verify_playwright_page(
    url: str,
    assertions: list[dict[str, Any]] | None = None,
    *,
    timeout_seconds: int = 30,
    output_dir: str | Path | None = None,
    browser_factory: Callable[[], Any] | None = None,
    page_factory: Callable[[], Any] | None = None,
) -> PlaywrightVerificationResult:
    started = datetime.now(timezone.utc)
    asserted = list(assertions or [])
    output_root = Path(output_dir or (Path("data") / "playwright_verification"))
    output_root.mkdir(parents=True, exist_ok=True)
    console_messages: list[str] = []
    console_errors: list[str] = []
    network_requests: list[str] = []
    network_failures: list[str] = []
    screenshot_path: Path | None = None
    page: Any = None
    browser: Any = None
    cleanup: Callable[[], None] | None = None
    assertion_results: list[AssertionOutcome] = []
    title = ""
    content = ""
    error: str | None = None

    try:
        page = page_factory() if callable(page_factory) else None
        if page is None:
            browser, page, cleanup = _launch_playwright_page(browser_factory=browser_factory, timeout_seconds=timeout_seconds)
        _attach_observers(page, console_messages, console_errors, network_requests, network_failures)
        _goto(page, url, timeout_seconds=timeout_seconds)
        title = _safe_call(page, "title", default="")
        content = _safe_content(page)
        screenshot_path = output_root / f"{_safe_name(url)}-{int(datetime.now().timestamp())}.png"
        _save_screenshot(page, screenshot_path)
        for assertion in asserted:
            outcome = _evaluate_assertion(page, url=url, assertion=assertion)
            assertion_results.append(outcome)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if not title:
            title = _safe_call(page, "title", default="") if page is not None else ""
        if not content:
            content = _safe_content(page) if page is not None else ""
    finally:
        try:
            if page is not None and hasattr(page, "close"):
                page.close()
        except Exception:
            pass
        try:
            if browser is not None and hasattr(browser, "close"):
                browser.close()
        except Exception:
            pass
        try:
            if callable(cleanup):
                cleanup()
        except Exception:
            pass

    screenshot_bytes = screenshot_path.read_bytes() if screenshot_path and screenshot_path.exists() else b""
    screenshot_hash = hashlib.sha256(screenshot_bytes).hexdigest() if screenshot_bytes else ""
    dom_payload = {
        "url": url,
        "title": title,
        "content": content,
        "assertions": [outcome.to_dict() for outcome in assertion_results],
    }
    dom_hash = sha256_json(dom_payload)
    failed_assertions = [outcome.to_dict() for outcome in assertion_results if not outcome.passed]
    passed = not error and not failed_assertions
    failure_trace = {
        "passed": passed,
        "error": error,
        "failed_assertions": failed_assertions,
        "screenshot_path": str(screenshot_path) if screenshot_path else None,
        "dom_hash": dom_hash,
        "console_errors": console_errors[:8],
        "network_failures": network_failures[:8],
    }
    console_summary = {
        "count": len(console_messages),
        "messages": console_messages[:20],
        "errors": console_errors[:8],
    }
    network_summary = {
        "count": len(network_requests),
        "requests": network_requests[:20],
        "failures": network_failures[:8],
    }
    result = PlaywrightVerificationResult(
        url=url,
        passed=passed,
        page_title=title,
        screenshot_path=str(screenshot_path) if screenshot_path else None,
        screenshot_hash=screenshot_hash,
        dom_hash=dom_hash,
        console_summary=console_summary,
        network_summary=network_summary,
        failure_trace=failure_trace,
        assertions=assertion_results,
        elapsed_ms=(datetime.now(timezone.utc) - started).total_seconds() * 1000,
        verified_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        evidence={
            "error": error,
            "output_dir": str(output_root),
            "page_path": _safe_name(url),
        },
    )
    if screenshot_path and screenshot_path.exists():
        result.evidence["screenshot_size"] = screenshot_path.stat().st_size
    return result


def _launch_playwright_page(*, browser_factory: Callable[[], Any] | None, timeout_seconds: int) -> tuple[Any, Any, Callable[[], None] | None]:
    if callable(browser_factory):
        browser = browser_factory()
        page = browser.new_page()
        return browser, page, getattr(browser, "close", None)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise RuntimeError("Playwright is not installed. Provide a browser_factory or page_factory for tests.") from exc
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        return browser, page, playwright.stop
    except Exception:
        playwright.stop()
        raise


def _attach_observers(
    page: Any,
    console_messages: list[str],
    console_errors: list[str],
    network_requests: list[str],
    network_failures: list[str],
) -> None:
    on = getattr(page, "on", None)
    if not callable(on):
        return

    def handle_console(message: Any) -> None:
        text = str(getattr(message, "text", None) or getattr(message, "message", None) or message)
        console_messages.append(text)
        if str(getattr(message, "type", None) or "").lower() == "error":
            console_errors.append(text)

    def handle_request(request: Any) -> None:
        url = str(getattr(request, "url", None) or request)
        network_requests.append(url)

    def handle_request_failed(request: Any) -> None:
        url = str(getattr(request, "url", None) or request)
        network_failures.append(url)

    try:
        on("console", handle_console)
    except Exception:
        pass
    try:
        on("request", handle_request)
    except Exception:
        pass
    try:
        on("requestfailed", handle_request_failed)
    except Exception:
        pass


def _goto(page: Any, url: str, *, timeout_seconds: int) -> None:
    if hasattr(page, "goto") and callable(page.goto):
        page.goto(url, wait_until="networkidle", timeout=int(timeout_seconds) * 1000)
        return
    raise RuntimeError("The provided page object does not support navigation.")


def _safe_content(page: Any) -> str:
    if hasattr(page, "content") and callable(page.content):
        try:
            return str(page.content())
        except Exception:
            pass
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            return str(evaluate("document.documentElement.outerHTML"))
        except Exception:
            pass
    return ""


def _save_screenshot(page: Any, path: Path) -> None:
    if hasattr(page, "screenshot") and callable(page.screenshot):
        page.screenshot(path=str(path), full_page=True)
        return
    raise RuntimeError("The provided page object does not support screenshots.")


def _evaluate_assertion(page: Any, *, url: str, assertion: dict[str, Any]) -> AssertionOutcome:
    kind = str(assertion.get("type") or "text").lower()
    selector = str(assertion.get("selector") or "").strip()
    if kind == "url":
        expected = str(assertion.get("matches") or assertion.get("contains") or "").strip()
        actual = str(getattr(page, "url", url) or url)
        if expected and expected in actual:
            return AssertionOutcome(assertion, True, f"url contains {expected!r}")
        return AssertionOutcome(assertion, False, f"url {actual!r} did not contain {expected!r}")

    locator = None
    if selector and hasattr(page, "locator") and callable(page.locator):
        locator = page.locator(selector)
    elif selector and hasattr(page, "text_content") and callable(page.text_content):
        locator = page

    if kind == "exists":
        passed = bool(_locator_count(locator) if locator is not None else False)
        detail = "selector exists" if passed else f"selector {selector!r} was not found"
        return AssertionOutcome(assertion, passed, detail)

    if kind == "visible":
        passed = bool(_locator_visible(locator) if locator is not None else False)
        detail = "selector visible" if passed else f"selector {selector!r} was not visible"
        return AssertionOutcome(assertion, passed, detail)

    expected_contains = str(assertion.get("contains") or assertion.get("equals") or "").strip()
    text = _locator_text(locator) if locator is not None else _safe_content(page)
    if expected_contains and expected_contains in text:
        return AssertionOutcome(assertion, True, f"text contained {expected_contains!r}")
    if expected_contains:
        return AssertionOutcome(assertion, False, f"text {text!r} did not contain {expected_contains!r}")
    return AssertionOutcome(assertion, bool(text.strip()), "text available" if text.strip() else "no text found")


def _locator_text(locator: Any) -> str:
    if locator is None:
        return ""
    for method_name in ("text_content", "inner_text"):
        method = getattr(locator, method_name, None)
        if callable(method):
            try:
                return str(method() or "")
            except Exception:
                continue
    return ""


def _locator_count(locator: Any) -> bool:
    if locator is None:
        return False
    method = getattr(locator, "count", None)
    if callable(method):
        try:
            return int(method()) > 0
        except Exception:
            return False
    return bool(locator)


def _locator_visible(locator: Any) -> bool:
    if locator is None:
        return False
    method = getattr(locator, "is_visible", None)
    if callable(method):
        try:
            return bool(method())
        except Exception:
            return False
    return bool(locator)


def _safe_call(obj: Any, method_name: str, *, default: str = "") -> str:
    method = getattr(obj, method_name, None)
    if not callable(method):
        return default
    try:
        return str(method() or default)
    except Exception:
        return default


def _safe_name(value: str) -> str:
    value = urlparse(value).netloc + urlparse(value).path
    value = value or "page"
    value = value.replace("/", "_").replace("\\", "_")
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)[:120] or "page"


__all__ = [
    "AssertionOutcome",
    "PlaywrightVerificationResult",
    "verify_playwright_page",
]
