"""Privacy-gated, provider-independent web evidence retrieval for Nova.

The retriever is deliberately bounded: it only runs after an explicit online
request, refuses private or secret-looking content, searches one public index,
and fetches a small number of public HTTPS/HTTP pages.  Operational traces never
contain the user's query or fetched page text.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
import base64
from html.parser import HTMLParser
import ipaddress
import os
import re
import socket
from typing import Any, Callable, Mapping
import urllib.error
import urllib.request
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

from nova_claim_consensus import publisher_identity


RETRIEVAL_SCHEMA_VERSION = "1.0"
DEFAULT_SEARCH_URL = "https://lite.duckduckgo.com/lite/"
_MAX_PAGE_BYTES = 250_000
_MAX_SEARCH_BYTES = 500_000
_ONLINE_PHRASES = (
    "go online",
    "check online",
    "search online",
    "search the web",
    "web search",
    "look this up",
    "look that up",
    "look it up",
    "look up",
    "research the",
    "research this",
    "research that",
)
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"\b(?:authorization|bearer)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|password|passwd|secret|access[_ -]?token)\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"(?:[A-Za-z]:\\|\\\\[A-Za-z0-9_.-]+\\)[^\r\n]{2,}", re.IGNORECASE),
    re.compile(r"(?:^|\s)(?:~\/|\/home\/|\/Users\/|\/etc\/|\/var\/)[^\s]+", re.IGNORECASE),
)
_LOW_EVIDENCE_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "pinterest.com",
    "tiktok.com",
    "x.com",
    "youtube.com",
}


def _env_bool(name: str, default: bool) -> bool:
    value = str(os.environ.get(name, "true" if default else "false")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def _canonical(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _public_search_terms(query: str) -> str:
    value = re.sub(r"\s+", " ", str(query or "")).strip()
    patterns = (
        r"^\s*(?:please\s+)?search\s+the\s+web\s+(?:for\s+)?",
        r"^\s*(?:please\s+)?search\s+online\s+(?:for\s+)?",
        r"^\s*(?:please\s+)?web\s+search\s+(?:for\s+)?",
        r"^\s*(?:please\s+)?go\s+online\s+(?:and\s+)?(?:search\s+for\s+)?",
        r"^\s*(?:please\s+)?check\s+online\s+(?:for\s+)?",
        r"^\s*(?:please\s+)?look\s+(?:this|that|it)\s+up\s+(?:online\s+)?",
        r"^\s*(?:please\s+)?look\s+up\s+",
        r"^\s*(?:please\s+)?research\s+(?:the|this|that)?\s*",
    )
    for pattern in patterns:
        updated = re.sub(pattern, "", value, flags=re.IGNORECASE).strip()
        if updated != value:
            value = updated
            break
    value = re.sub(r"\s+(?:online|on the web)\s*$", "", value, flags=re.IGNORECASE).strip(" .?!")
    return value[:500] or str(query or "").strip()[:500]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _domain_matches(domain: str, candidates: set[str]) -> bool:
    value = str(domain or "").lower().removeprefix("www.")
    return any(value == candidate or value.endswith("." + candidate) for candidate in candidates)


def _public_hostname(hostname: str, resolver: Callable[..., Any] = socket.getaddrinfo) -> bool:
    host = str(hostname or "").strip().lower().rstrip(".")
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        literal = ipaddress.ip_address(host)
        return not (
            literal.is_private
            or literal.is_loopback
            or literal.is_link_local
            or literal.is_multicast
            or literal.is_reserved
            or literal.is_unspecified
        )
    except ValueError:
        pass
    try:
        addresses = {
            item[4][0].split("%", 1)[0]
            for item in resolver(host, None, type=socket.SOCK_STREAM)
            if item and len(item) >= 5 and item[4]
        }
    except (OSError, socket.gaierror):
        return False
    if not addresses:
        return False
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            return False
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_multicast
            or parsed.is_reserved
            or parsed.is_unspecified
        ):
            return False
    return True


def validate_public_url(
    url: str,
    *,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> tuple[bool, str]:
    """Return whether a URL is safe for Nova's outbound public-page fetch."""

    try:
        parsed = urlparse(str(url or "").strip())
    except ValueError:
        return False, "invalid_url"
    if parsed.scheme not in {"http", "https"}:
        return False, "unsupported_scheme"
    if parsed.username or parsed.password:
        return False, "embedded_credentials"
    if not parsed.hostname:
        return False, "missing_hostname"
    if not _public_hostname(parsed.hostname, resolver):
        return False, "non_public_host"
    return True, "public"


@dataclass(frozen=True)
class RetrievalPolicyDecision:
    allowed: bool
    reason: str
    explicit_online_request: bool
    private_mode: bool
    query_length: int

    def as_trace(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "explicit_online_request": self.explicit_online_request,
            "private_mode": self.private_mode,
            "query_length": self.query_length,
            "content_logged": False,
        }


@dataclass(frozen=True)
class FetchedPage:
    url: str
    status: int
    content_type: str
    text: str


@dataclass(frozen=True)
class SourceEvidence:
    evidence_id: str
    title: str
    url: str
    domain: str
    publisher_id: str
    snippet: str
    checked_at: str
    status: int
    source_type: str
    reliability_score: float
    reliability_reasons: tuple[str, ...] = ()

    def safe_summary(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "domain": self.domain,
            "publisher_id": self.publisher_id,
            "status": self.status,
            "source_type": self.source_type,
            "reliability_score": round(self.reliability_score, 3),
            "reliability_reasons": list(self.reliability_reasons),
        }

    def as_legacy_source(self) -> dict[str, Any]:
        return {
            "name": self.title,
            "title": self.title,
            "url": self.url,
            "domain": self.domain,
            "publisher_id": self.publisher_id,
            "status": self.status,
            "snippet": self.snippet,
            "checked_at": self.checked_at,
            "source_type": self.source_type,
            "reliability_score": round(self.reliability_score, 3),
            "reliability_reasons": list(self.reliability_reasons),
        }


@dataclass(frozen=True)
class RetrievalResult:
    status: str
    policy: RetrievalPolicyDecision
    evidence: tuple[SourceEvidence, ...] = ()
    errors: tuple[str, ...] = ()
    schema_version: str = RETRIEVAL_SCHEMA_VERSION

    def safe_trace(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "policy": self.policy.as_trace(),
            "source_count": len(self.evidence),
            "sources": [item.safe_summary() for item in self.evidence],
            "error_categories": list(self.errors),
        }

    def as_legacy_sources(self) -> list[dict[str, Any]]:
        return [item.as_legacy_source() for item in self.evidence]


@dataclass(frozen=True)
class _SearchResult:
    title: str
    url: str
    snippet: str


class _SearchResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[_SearchResult] = []
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._active_url = ""
        self._in_title = False
        self._in_snippet = False
        self._in_bing_result = False
        self._in_bing_heading = False
        self._in_bing_title = False
        self._in_bing_snippet = False
        self._bing_url = ""
        self._bing_title_parts: list[str] = []
        self._bing_snippet_parts: list[str] = []

    @staticmethod
    def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
        values = dict(attrs).get("class") or ""
        return {part.strip().lower() for part in values.split() if part.strip()}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attrs)
        lower = tag.lower()
        if lower == "li" and "b_algo" in classes:
            self._in_bing_result = True
            self._in_bing_heading = False
            self._in_bing_title = False
            self._in_bing_snippet = False
            self._bing_url = ""
            self._bing_title_parts = []
            self._bing_snippet_parts = []
        elif lower == "h2" and self._in_bing_result:
            self._in_bing_heading = True
        elif lower == "a" and self._in_bing_heading and not self._bing_url:
            self._bing_url = str(dict(attrs).get("href") or "")
            self._in_bing_title = True
        elif lower == "p" and self._in_bing_result and self._bing_url:
            self._in_bing_snippet = True
        elif lower == "a" and ({"result__a", "result-link"} & classes):
            self._active_url = str(dict(attrs).get("href") or "")
            self._title_parts = []
            self._in_title = True
        elif {"result__snippet", "result-snippet"} & classes:
            self._snippet_parts = []
            self._in_snippet = True

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower == "a" and self._in_bing_title:
            self._in_bing_title = False
        elif lower == "p" and self._in_bing_snippet:
            self._in_bing_snippet = False
        elif lower == "h2" and self._in_bing_heading:
            self._in_bing_heading = False
        elif lower == "li" and self._in_bing_result:
            title = re.sub(r"\s+", " ", " ".join(self._bing_title_parts)).strip()
            snippet = re.sub(r"\s+", " ", " ".join(self._bing_snippet_parts)).strip()
            if title and self._bing_url:
                self.results.append(_SearchResult(title[:240], self._bing_url, snippet[:600]))
            self._in_bing_result = False
        elif lower == "a" and self._in_title:
            title = re.sub(r"\s+", " ", " ".join(self._title_parts)).strip()
            if title and self._active_url:
                self.results.append(_SearchResult(title=title[:240], url=self._active_url, snippet=""))
            self._in_title = False
        elif self._in_snippet and lower in {"a", "div", "span"}:
            snippet = re.sub(r"\s+", " ", " ".join(self._snippet_parts)).strip()
            if snippet and self.results and not self.results[-1].snippet:
                last = self.results[-1]
                self.results[-1] = _SearchResult(last.title, last.url, snippet[:600])
            self._in_snippet = False

    def handle_data(self, data: str) -> None:
        if self._in_bing_title:
            self._bing_title_parts.append(data)
        if self._in_bing_snippet:
            self._bing_snippet_parts.append(data)
        if self._in_title:
            self._title_parts.append(data)
        if self._in_snippet:
            self._snippet_parts.append(data)


class _PageTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.text_parts: list[str] = []
        self._in_title = False
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "template", "noscript", "svg"}:
            self._ignored_depth += 1
            return
        if lower == "title":
            self._in_title = True
        if lower == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            name = (values.get("name") or values.get("property") or "").lower()
            if name in {"description", "og:description"} and not self.description:
                self.description = re.sub(r"\s+", " ", values.get("content", "")).strip()[:600]

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"script", "style", "template", "noscript", "svg"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if lower == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        value = re.sub(r"\s+", " ", data).strip()
        if not value:
            return
        if self._in_title:
            self.title_parts.append(value)
        elif len(value) >= 20:
            self.text_parts.append(value)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, resolver: Callable[..., Any], maximum_redirects: int = 3) -> None:
        super().__init__()
        self.resolver = resolver
        self.maximum_redirects = maximum_redirects

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        redirect_count = int(getattr(req, "_nova_redirect_count", 0)) + 1
        if redirect_count > self.maximum_redirects:
            raise urllib.error.URLError("redirect_limit")
        target = urljoin(req.full_url, newurl)
        safe, reason = validate_public_url(target, resolver=self.resolver)
        if not safe:
            raise urllib.error.URLError(reason)
        redirected = super().redirect_request(req, fp, code, msg, headers, target)
        if redirected is not None:
            setattr(redirected, "_nova_redirect_count", redirect_count)
        return redirected


def _default_fetch(
    url: str,
    timeout: int,
    maximum_bytes: int,
    *,
    resolver: Callable[..., Any] = socket.getaddrinfo,
) -> FetchedPage:
    safe, reason = validate_public_url(url, resolver=resolver)
    if not safe:
        raise ValueError(reason)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "NovaCreatureEvidenceRetriever/1.0",
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
        },
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler(resolver))
    with opener.open(request, timeout=timeout) as response:
        final_url = str(response.geturl() or url)
        final_safe, final_reason = validate_public_url(final_url, resolver=resolver)
        if not final_safe:
            raise ValueError(final_reason)
        status = int(getattr(response, "status", response.getcode()))
        content_type = str(response.headers.get("Content-Type") or "")
        charset = response.headers.get_content_charset() or "utf-8"
        text = response.read(maximum_bytes + 1)
        if len(text) > maximum_bytes:
            text = text[:maximum_bytes]
        return FetchedPage(final_url, status, content_type, text.decode(charset, errors="replace"))


def _resolve_search_result_url(value: str) -> str:
    url = str(value or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        encoded = (parse_qs(parsed.query).get("uddg") or [""])[0]
        if encoded:
            return unquote(encoded)
    if parsed.netloc.endswith("bing.com") and parsed.path.startswith("/ck/"):
        encoded = (parse_qs(parsed.query).get("u") or [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        if encoded:
            try:
                padding = "=" * (-len(encoded) % 4)
                decoded = base64.urlsafe_b64decode(encoded + padding).decode("utf-8", errors="strict")
                if decoded.startswith(("http://", "https://")):
                    return decoded
            except (ValueError, UnicodeDecodeError):
                pass
    return url


def _page_summary(page: FetchedPage, fallback_title: str, fallback_snippet: str, query: str) -> tuple[str, str]:
    content_type = page.content_type.lower()
    if "html" not in content_type and "<html" not in page.text[:1000].lower():
        snippet = re.sub(r"\s+", " ", page.text).strip()[:600]
        return fallback_title[:240], snippet or fallback_snippet[:600]
    parser = _PageTextParser()
    parser.feed(page.text)
    title = re.sub(r"\s+", " ", " ".join(parser.title_parts)).strip()[:240] or fallback_title[:240]
    body = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    terms = [term for term in re.findall(r"[A-Za-z0-9]{4,}", query.lower())[:8]]
    body_excerpt = ""
    if body:
        lower_body = body.lower()
        start = 0
        for term in reversed(terms):
            found = lower_body.find(term)
            if found >= 0:
                start = max(0, found - 100)
                break
        body_excerpt = body[start : start + 600].strip()
    candidates = [
        parser.description,
        body_excerpt,
        str(fallback_snippet or "").strip()[:600],
    ]

    def relevance(value: str) -> tuple[int, int]:
        words = set(re.findall(r"[a-z0-9]{3,}", str(value or "").lower()))
        return len(words & set(terms)), len(str(value or ""))

    best = max((value for value in candidates if value), key=relevance, default="")
    return title, best[:600]


def score_source(url: str, *, fetched: bool = True) -> tuple[float, tuple[str, ...]]:
    """Score provenance characteristics, not whether the claim itself is true."""

    parsed = urlparse(url)
    domain = str(parsed.hostname or "").lower()
    score = 0.35
    reasons: list[str] = ["public_web_source"]
    if parsed.scheme == "https":
        score += 0.1
        reasons.append("https")
    if fetched:
        score += 0.1
        reasons.append("page_fetched")
    if domain.endswith((".gov", ".mil")):
        score += 0.3
        reasons.append("government_domain")
    elif domain.endswith(".edu"):
        score += 0.25
        reasons.append("education_domain")
    elif domain.endswith(".org"):
        score += 0.12
        reasons.append("organization_domain")
    if domain in {"who.int", "un.org", "reuters.com", "apnews.com"}:
        score += 0.12
        reasons.append("established_primary_or_wire_source")
    return min(0.98, score), tuple(reasons)


@dataclass
class NovaSourceRetriever:
    """Retrieve a few public sources only when Nova's privacy policy allows."""

    enabled: bool = True
    require_explicit_request: bool = True
    block_private: bool = True
    maximum_sources: int = 3
    timeout_seconds: int = 6
    search_url: str = DEFAULT_SEARCH_URL
    resolver: Callable[..., Any] = socket.getaddrinfo
    fetcher: Callable[[str, int, int], FetchedPage] | None = None
    _fetch: Callable[[str, int, int], FetchedPage] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.maximum_sources = max(1, min(int(self.maximum_sources), 5))
        self.timeout_seconds = max(2, min(int(self.timeout_seconds), 15))
        if self.fetcher is None:
            self._fetch = lambda url, timeout, maximum: _default_fetch(
                url,
                timeout,
                maximum,
                resolver=self.resolver,
            )
        else:
            self._fetch = self.fetcher

    def health_check(self) -> dict[str, Any]:
        parsed = urlparse(self.search_url)
        return {
            "ok": bool(self.enabled),
            "enabled": bool(self.enabled),
            "require_explicit_request": bool(self.require_explicit_request),
            "block_private": bool(self.block_private),
            "maximum_sources": self.maximum_sources,
            "timeout_seconds": self.timeout_seconds,
            "search_provider_domain": str(parsed.hostname or ""),
            "schema_version": RETRIEVAL_SCHEMA_VERSION,
        }

    @classmethod
    def from_environment(cls) -> "NovaSourceRetriever":
        return cls(
            enabled=_env_bool("NOVA_WEB_RETRIEVAL_ENABLED", True),
            require_explicit_request=_env_bool("NOVA_WEB_RETRIEVAL_REQUIRE_EXPLICIT", True),
            block_private=_env_bool("NOVA_WEB_RETRIEVAL_BLOCK_PRIVATE", True),
            maximum_sources=_env_int("NOVA_WEB_RETRIEVAL_MAX_SOURCES", 3, 1, 5),
            timeout_seconds=_env_int("NOVA_WEB_RETRIEVAL_TIMEOUT_SECONDS", 6, 2, 15),
            search_url=os.environ.get("NOVA_WEB_RETRIEVAL_SEARCH_URL", DEFAULT_SEARCH_URL).strip()
            or DEFAULT_SEARCH_URL,
        )

    def authorize(self, query: str, context: Mapping[str, Any] | None = None) -> RetrievalPolicyDecision:
        context = context if isinstance(context, Mapping) else {}
        gateway = context.get("nova_gateway") if isinstance(context.get("nova_gateway"), Mapping) else {}
        explicit = any(phrase in _canonical(query) for phrase in _ONLINE_PHRASES)
        private_mode = bool(
            context.get("private_mode")
            or context.get("contains_private_data")
            or context.get("contains_private_files")
            or context.get("privacy_mode") == "local_only"
            or gateway.get("private_mode")
            or gateway.get("contains_private_data")
            or gateway.get("contains_private_files")
            or gateway.get("privacy_mode") == "local_only"
        )
        reason = "allowed"
        allowed = True
        if not self.enabled:
            allowed, reason = False, "retrieval_disabled"
        elif self.block_private and private_mode:
            allowed, reason = False, "private_mode"
        elif context.get("allow_web_retrieval") is False or gateway.get("allow_web_retrieval") is False:
            allowed, reason = False, "client_policy"
        elif any(pattern.search(str(query or "")) for pattern in _SECRET_PATTERNS):
            allowed, reason = False, "sensitive_content"
        elif self.require_explicit_request and not explicit:
            allowed, reason = False, "explicit_request_required"
        return RetrievalPolicyDecision(
            allowed=allowed,
            reason=reason,
            explicit_online_request=explicit,
            private_mode=private_mode,
            query_length=len(str(query or "")),
        )

    def _search(self, query: str) -> list[_SearchResult]:
        search_base = self.search_url
        safe, reason = validate_public_url(search_base, resolver=self.resolver)
        if not safe:
            raise ValueError("unsafe_search_endpoint:" + reason)
        separator = "&" if "?" in search_base else "?"
        page = self._fetch(search_base + separator + "q=" + quote_plus(query), self.timeout_seconds, _MAX_SEARCH_BYTES)
        if not (200 <= page.status < 400):
            raise urllib.error.URLError("search_http_status")
        parser = _SearchResultsParser()
        parser.feed(page.text)
        results: list[_SearchResult] = []
        publishers: set[str] = set()
        for result in parser.results:
            url = _resolve_search_result_url(result.url)
            safe, _ = validate_public_url(url, resolver=self.resolver)
            if not safe:
                continue
            domain = str(urlparse(url).hostname or "").lower()
            publisher = publisher_identity(domain)
            if not domain or not publisher or publisher in publishers:
                continue
            publishers.add(publisher)
            results.append(_SearchResult(result.title, url, result.snippet))
            if len(results) >= self.maximum_sources * 6:
                break
        query_tokens = set(re.findall(r"[a-z0-9]{3,}", query.lower()))

        def candidate_rank(item: _SearchResult) -> tuple[float, int, str]:
            domain = str(urlparse(item.url).hostname or "").lower()
            searchable = " ".join((item.title, item.snippet, domain)).lower()
            overlap = len(query_tokens & set(re.findall(r"[a-z0-9]{3,}", searchable)))
            provenance, _ = score_source(item.url, fetched=False)
            low_evidence_penalty = 0.45 if _domain_matches(domain, _LOW_EVIDENCE_DOMAINS) else 0.0
            rank = (overlap / max(1, len(query_tokens))) * 0.75 + provenance * 0.25 - low_evidence_penalty
            return (-rank, -overlap, domain)

        results.sort(key=candidate_rank)
        return results

    def _fetch_evidence(self, index: int, result: _SearchResult, query: str) -> SourceEvidence:
        page = self._fetch(result.url, self.timeout_seconds, _MAX_PAGE_BYTES)
        if not (200 <= page.status < 400):
            raise urllib.error.URLError("source_http_status")
        title, snippet = _page_summary(page, result.title, result.snippet, query)
        domain = str(urlparse(page.url).hostname or urlparse(result.url).hostname or "").lower()
        publisher = publisher_identity(domain)
        score, reasons = score_source(page.url, fetched=True)
        return SourceEvidence(
            evidence_id=f"web-{index + 1}",
            title=title or domain,
            url=page.url,
            domain=domain,
            publisher_id=publisher,
            snippet=snippet[:600],
            checked_at=_utc_timestamp(),
            status=page.status,
            source_type="live_web_page",
            reliability_score=score,
            reliability_reasons=reasons,
        )

    def retrieve(self, query: str, context: Mapping[str, Any] | None = None) -> RetrievalResult:
        policy = self.authorize(query, context)
        if not policy.allowed:
            return RetrievalResult("blocked", policy)
        search_terms = _public_search_terms(query)
        try:
            candidates = self._search(search_terms)
        except Exception as exc:
            return RetrievalResult("unavailable", policy, errors=(type(exc).__name__,))
        if not candidates:
            return RetrievalResult("unavailable", policy, errors=("no_public_results",))

        evidence_by_index: dict[int, SourceEvidence] = {}
        errors: list[str] = []
        selected = candidates[: self.maximum_sources]
        with ThreadPoolExecutor(max_workers=min(3, len(selected)), thread_name_prefix="nova-web") as pool:
            futures = {
                pool.submit(self._fetch_evidence, index, result, search_terms): index
                for index, result in enumerate(selected)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    evidence_by_index[index] = future.result()
                except Exception as exc:
                    errors.append(type(exc).__name__)
        evidence = tuple(evidence_by_index[index] for index in sorted(evidence_by_index))
        if evidence and errors:
            status = "partial"
        elif evidence:
            status = "success"
        else:
            status = "unavailable"
        return RetrievalResult(status, policy, evidence=evidence, errors=tuple(sorted(set(errors))))
