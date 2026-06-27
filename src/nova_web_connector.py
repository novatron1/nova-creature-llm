"""
Nova Web Connector — Online Search for Current Information
===========================================================
Nova stays in control. The local LLM cannot guess current facts.
Every web result includes source URLs.

Config:
  NOVA_USE_WEB=true|false
  NOVA_WEB_PROVIDER=duckduckgo|mock
  NOVA_WEB_TIMEOUT=20
  NOVA_WEB_MAX_RESULTS=5
  NOVA_REQUIRE_SOURCES=true
"""

import json, os, sys, re, time, urllib.request, urllib.parse, urllib.error
from datetime import datetime
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Config ────────────────────────────────────────────────────────────────

CONFIG = {
    "use_web": os.environ.get("NOVA_USE_WEB", "false").lower() == "true",
    "provider": os.environ.get("NOVA_WEB_PROVIDER", "duckduckgo"),
    "timeout": int(os.environ.get("NOVA_WEB_TIMEOUT", "20")),
    "max_results": int(os.environ.get("NOVA_WEB_MAX_RESULTS", "5")),
    "require_sources": os.environ.get("NOVA_REQUIRE_SOURCES", "true").lower() == "true",
}


class HTMLStripper(HTMLParser):
    """Strip HTML tags for DDG text snippets."""
    def __init__(self):
        super().__init__()
        self.text = []
    def handle_data(self, data):
        self.text.append(data)
    def get_text(self):
        return ' '.join(self.text)


def strip_html(html):
    stripper = HTMLStripper()
    stripper.feed(html)
    return stripper.get_text()


def search_duckduckgo(query, max_results=5, timeout=20):
    """
    Search DuckDuckGo (lite version, no API key needed).
    Returns list of result dicts: {title, snippet, url}
    """
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({"q": query}).encode()
    headers = {"User-Agent": "Mozilla/5.0 (compatible; Nova-Creature/1.0)"}

    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return {"success": False, "error": f"ddg_request_failed: {e}", "results": []}

    # Parse results from DDG lite HTML
    results = []
    try:
        # DDG lite uses table rows: title link, then URL in link-text span
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        i = 0
        while i < len(rows) and len(results) < max_results:
            row = rows[i]
            # Check if this row has an href link
            urls = re.findall(r'href="(https?://[^"]+)"', row)
            if not urls:
                i += 1
                continue
            url = urls[0]
            # Extract title text
            title_match = re.search(r'<a[^>]*>(.*?)</a>', row)
            title = strip_html(title_match.group(1)).strip() if title_match else ""
            # Remove leading number like "1.&nbsp;"
            title = re.sub(r'^\d+\s*[.\u00a0]\s*', '', title).strip()
            # Look ahead for snippet in next non-empty rows
            snippet = ""
            for j in range(i+1, min(i+3, len(rows))):
                next_text = strip_html(rows[j]).strip()
                if next_text and 'link-text' not in rows[j]:
                    snippet = next_text[:300]
                    break
            if title or url:
                results.append({
                    "title": title[:200],
                    "snippet": snippet if snippet else title[:200],
                    "url": url,
                })
            i += 1
    except Exception as e:
        return {"success": False, "error": f"ddg_parse_failed: {e}", "results": []}

    return {
        "success": len(results) > 0,
        "error": None if results else "no_results",
        "results": results,
        "query": query,
        "provider": "duckduckgo",
        "timestamp": datetime.now().isoformat(),
    }


def search(query, max_results=None, timeout=None):
    """
    Main search entry point. Routes to configured provider.

    Args:
        query: search query string.
        max_results: override config max_results.
        timeout: override config timeout.

    Returns:
        dict with {success, results, error, provider, query, timestamp}
    """
    if not CONFIG["use_web"]:
        return {
            "success": False,
            "error": "web_disabled",
            "results": [],
            "provider": CONFIG["provider"],
            "query": query,
            "timestamp": datetime.now().isoformat(),
        }

    max_r = max_results or CONFIG["max_results"]
    t = timeout or CONFIG["timeout"]
    provider = CONFIG["provider"]

    if provider == "duckduckgo":
        return search_duckduckgo(query, max_results=max_r, timeout=t)
    else:
        return {
            "success": False,
            "error": f"unsupported_provider: {provider}",
            "results": [],
            "provider": provider,
            "query": query,
            "timestamp": datetime.now().isoformat(),
        }


def format_results(result_dict, max_snippet_len=200):
    """
    Format web results into a clean text block for LLM context.

    Args:
        result_dict: return value from search().
        max_snippet_len: max chars per snippet.

    Returns:
        str: formatted text block.
    """
    if not result_dict.get("success"):
        return ""

    results = result_dict.get("results", [])
    if not results:
        return ""

    lines = ["Web Search Results:"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")[:100]
        snippet = r.get("snippet", "")[:max_snippet_len]
        url = r.get("url", "")
        lines.append(f"  [{i}] {title}")
        if snippet:
            lines.append(f"      {snippet}")
        if url:
            lines.append(f"      Source: {url}")
    return "\n".join(lines)


def make_source_citations(result_dict):
    """
    Generate source citation text for the final answer.

    Args:
        result_dict: return value from search().

    Returns:
        str: citation lines.
    """
    if not result_dict.get("success"):
        return ""

    results = result_dict.get("results", [])
    if not results:
        return ""

    lines = [f"\n\nSources ({result_dict.get('provider', 'web')}):"]
    for r in results[:3]:
        url = r.get("url", "")
        if url:
            lines.append(f"  - {url}")
    return "\n".join(lines)


# ─── CLI Test ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) or "latest AI news"
    print(f"Searching: {query}")
    print(f"Config: use_web={CONFIG['use_web']}, provider={CONFIG['provider']}")
    print()

    # Enable web for test
    CONFIG["use_web"] = True

    result = search(query)
    if result["success"]:
        print(format_results(result))
        print()
        print(make_source_citations(result))
    else:
        print(f"Search failed: {result['error']}")
        if result.get("results"):
            print("Partial results:", result["results"][:2])
