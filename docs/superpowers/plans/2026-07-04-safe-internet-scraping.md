# Safe Internet Scraping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add controlled public web-page scraping to Nova chat and API.

**Architecture:** Keep scraping inside `nova_enhanced_server.py` beside the existing live research/news fetchers. Add strict URL validation before any network call, extract readable HTML without executing scripts, and route chat/API responses through a shared helper.

**Tech Stack:** Python standard library `urllib`, `socket`, `ipaddress`, `html.parser`-style regex extraction already used in the server, existing `NovaHandler` API pattern, pytest.

---

### Task 1: Scraper Behavior Tests

**Files:**
- Modify: `tests/test_nova_enhanced_server.py`

- [ ] **Step 1: Write failing tests**

Add tests that verify:
- Chat command `scrape https://example.com/page` routes before general chat and returns `[SCRAPE]`.
- `/api/scrape` returns title, text, headings, and links from a mocked public fetch.
- Private/local URLs such as `http://127.0.0.1:3000/` are rejected.

- [ ] **Step 2: Run focused tests**

Run: `py -3 -m pytest tests/test_nova_enhanced_server.py -q -k "scrape"`

Expected: tests fail because scraper helpers and endpoint do not exist yet.

### Task 2: Scraper Helpers And Chat Route

**Files:**
- Modify: `nova_enhanced_server.py`

- [ ] **Step 1: Implement validation**

Add URL extraction and validation helpers that only allow `http` and `https`, block local/private/reserved IPs, and restrict non-default ports.

- [ ] **Step 2: Implement extraction**

Add a bounded fetch that reads public HTML, extracts page title, headings, readable text, and links, and returns a structured result.

- [ ] **Step 3: Wire chat route**

Add an early `brain_route` branch for scrape commands so generic chat cannot swallow them.

- [ ] **Step 4: Run focused tests**

Run: `py -3 -m pytest tests/test_nova_enhanced_server.py -q -k "scrape"`

Expected: scraper tests pass.

### Task 3: API Endpoint And Verification

**Files:**
- Modify: `nova_enhanced_server.py`
- Modify: `tests/test_nova_enhanced_server.py`

- [ ] **Step 1: Add API endpoint**

Add `POST /api/scrape` accepting `{"url": "https://..."}` and returning the same structured scrape result.

- [ ] **Step 2: Run full relevant tests**

Run: `py -3 -m pytest tests/test_nova_enhanced_server.py tests/test_nova_cognitive_os.py tests/test_nova_project_manager.py tests/test_nova_project_mod_agent.py tests/test_nova_website_builder_agent.py tests/test_nova_sandbox_game_builder.py -q`

Expected: all tests pass.

- [ ] **Step 3: Restart and public smoke test**

Restart the server on port 3000 and test the Cloudflare app with `scrape https://example.com`.
