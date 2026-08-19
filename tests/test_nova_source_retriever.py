from __future__ import annotations

import socket
import sys
from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nova_source_retriever import (  # noqa: E402
    FetchedPage,
    NovaSourceRetriever,
    score_source,
    validate_public_url,
)


def _public_resolver(host, port, type=socket.SOCK_STREAM):  # noqa: A002
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def _search_html(results):
    blocks = []
    for title, url, snippet in results:
        redirect = "https://duckduckgo.com/l/?uddg=" + quote(url, safe="")
        blocks.append(
            '<div class="result">'
            f'<a class="result__a" href="{redirect}">{title}</a>'
            f'<a class="result__snippet">{snippet}</a>'
            "</div>"
        )
    return "<html><body>" + "".join(blocks) + "</body></html>"


def test_retrieval_requires_an_explicit_online_request():
    retriever = NovaSourceRetriever(resolver=_public_resolver, fetcher=lambda *_: None)

    decision = retriever.authorize("Who is the mayor today?")

    assert decision.allowed is False
    assert decision.reason == "explicit_request_required"
    assert decision.as_trace()["content_logged"] is False


def test_private_mode_blocks_before_any_network_fetch():
    calls = []

    def fetcher(*args):
        calls.append(args)
        raise AssertionError("private requests must never reach the network")

    retriever = NovaSourceRetriever(resolver=_public_resolver, fetcher=fetcher)

    result = retriever.retrieve(
        "search the web for the current mayor",
        {"private_mode": True},
    )

    assert result.status == "blocked"
    assert result.policy.reason == "private_mode"
    assert calls == []


def test_secret_and_local_path_queries_are_blocked_before_network_fetch():
    retriever = NovaSourceRetriever(
        resolver=_public_resolver,
        fetcher=lambda *_: (_ for _ in ()).throw(AssertionError("must not fetch")),
    )

    secret = retriever.retrieve("look up api_key=sk-abcdefghijklmnopqrstuvwxyz123456 online")
    local_path = retriever.retrieve(r"search the web for C:\Users\Nova\private-notes.txt")

    assert secret.policy.reason == "sensitive_content"
    assert local_path.policy.reason == "sensitive_content"


def test_public_url_validation_blocks_ssrf_targets():
    assert validate_public_url("http://127.0.0.1:8765/private")[0] is False
    assert validate_public_url("http://169.254.169.254/latest/meta-data")[0] is False
    assert validate_public_url("file:///etc/passwd")[0] is False
    assert validate_public_url("https://example.test/page", resolver=_public_resolver) == (True, "public")


def test_retriever_fetches_multiple_unique_sources_in_stable_order():
    search_results = [
        ("Government source", "https://agency.gov/report", "Official report summary."),
        ("University source", "https://research.edu/study", "Research study summary."),
        ("Organization source", "https://example.org/guide", "Independent guide summary."),
    ]

    def fetcher(url, timeout, maximum_bytes):
        if "duckduckgo.com/lite" in url:
            return FetchedPage(url, 200, "text/html; charset=utf-8", _search_html(search_results))
        title = url.rsplit("/", 1)[-1].replace("-", " ").title()
        body = (
            "<html><head>"
            f"<title>{title}</title>"
            f'<meta name="description" content="Evidence from {url} about the requested public fact.">'
            "</head><body><main>Longer evidence body for the public question.</main></body></html>"
        )
        return FetchedPage(url, 200, "text/html; charset=utf-8", body)

    retriever = NovaSourceRetriever(
        resolver=_public_resolver,
        fetcher=fetcher,
        maximum_sources=3,
    )
    result = retriever.retrieve("search the web for a public science fact")

    assert result.status == "success"
    assert [item.domain for item in result.evidence] == [
        "agency.gov",
        "research.edu",
        "example.org",
    ]
    assert all(item.snippet.startswith("Evidence from") for item in result.evidence)
    assert result.evidence[0].reliability_score > result.evidence[2].reliability_score


def test_retriever_counts_subdomains_as_one_publisher():
    search_results = [
        ("NASA Science", "https://science.nasa.gov/earth", "Earth science evidence."),
        ("NASA Glenn", "https://www1.grc.nasa.gov/earth", "More NASA evidence."),
        ("University", "https://example.edu/earth", "Independent university evidence."),
    ]

    def fetcher(url, timeout, maximum_bytes):
        if "duckduckgo.com/lite" in url:
            return FetchedPage(url, 200, "text/html", _search_html(search_results))
        return FetchedPage(
            url,
            200,
            "text/html",
            "<html><head><title>Source</title>"
            '<meta name="description" content="Earth evidence from this publisher.">'
            "</head></html>",
        )

    result = NovaSourceRetriever(
        resolver=_public_resolver,
        fetcher=fetcher,
        maximum_sources=3,
    ).retrieve("search the web for Earth evidence")

    assert result.status == "success"
    assert {item.publisher_id for item in result.evidence} == {"nasa.gov", "example.edu"}
    assert result.safe_trace()["source_count"] == 2


def test_retrieval_trace_does_not_contain_query_or_page_text():
    secret_marker = "PUBLIC-QUERY-CONTENT-MUST-NOT-BE-LOGGED"

    def fetcher(url, timeout, maximum_bytes):
        if "duckduckgo.com/lite" in url:
            return FetchedPage(
                url,
                200,
                "text/html",
                _search_html([("Source", "https://example.org/page", "Search excerpt")]),
            )
        return FetchedPage(
            url,
            200,
            "text/html",
            "<html><head><title>Source</title>"
            '<meta name="description" content="Fetched evidence must stay out of operational trace.">'
            "</head></html>",
        )

    retriever = NovaSourceRetriever(resolver=_public_resolver, fetcher=fetcher)
    result = retriever.retrieve("search the web for " + secret_marker)
    safe_text = str(result.safe_trace())

    assert result.status == "success"
    assert secret_marker not in safe_text
    assert "Fetched evidence must stay out" not in safe_text
    assert result.safe_trace()["policy"]["content_logged"] is False


def test_reliability_score_describes_provenance_not_truth():
    government, gov_reasons = score_source("https://data.example.gov/report")
    unknown, unknown_reasons = score_source("http://example.com/post")

    assert government > unknown
    assert "government_domain" in gov_reasons
    assert "government_domain" not in unknown_reasons
