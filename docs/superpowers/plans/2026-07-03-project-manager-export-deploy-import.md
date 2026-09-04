# Project Manager Export Deploy Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add saved project management, ZIP export, local deploy previews, and safe import/edit mode for Nova sandbox projects.

**Architecture:** Create a focused project manager helper that owns safe project filesystem operations under `sandbox/app_builder_projects`. Expose it through JSON/download endpoints in `nova_enhanced_server.py`, then add Projects and Files UI controls in `nova_chat_web.html` that call those endpoints.

**Tech Stack:** Python standard library (`pathlib`, `zipfile`, `shutil`, `json`), existing `BaseHTTPRequestHandler` server, vanilla HTML/CSS/JS.

---

### Task 1: Project Manager Core

**Files:**
- Create: `src/nova_project_manager.py`
- Test: `tests/test_nova_project_manager.py`

- [ ] Write failing tests for listing projects, reading/writing safe files, exporting ZIP, local deploy copy, and ZIP import.
- [ ] Implement safe path resolution so operations cannot escape the project root.
- [ ] Implement `list_projects`, `list_project_files`, `read_project_file`, `write_project_file`, `export_project_zip`, `deploy_project`, and `import_project_zip`.
- [ ] Run `py -3 -m pytest tests/test_nova_project_manager.py`.

### Task 2: Server API

**Files:**
- Modify: `nova_enhanced_server.py`
- Test: `tests/test_nova_enhanced_server.py`

- [ ] Write failing tests for `/api/projects`, `/api/projects/<id>/files`, `/api/projects/<id>/file`, `/api/projects/<id>/export.zip`, `/api/projects/<id>/deploy`, and `/api/projects/import`.
- [ ] Add JSON helpers and endpoint routing.
- [ ] Keep downloads and static project serving CORS-safe.
- [ ] Run `py -3 -m pytest tests/test_nova_enhanced_server.py tests/test_nova_project_manager.py`.

### Task 3: UI Controls

**Files:**
- Modify: `nova_chat_web.html`
- Test: `tests/test_nova_enhanced_server.py`

- [ ] Add Projects panel cards populated from `/api/projects`.
- [ ] Add Open, Preview, Export ZIP, Deploy, and Edit buttons.
- [ ] Add Files panel project picker, file list, editor, Save button, ZIP import input, and import status.
- [ ] Add string-marker tests for the new controls.

### Task 4: Live Verification

**Files:**
- Generated artifacts under `sandbox/app_builder_projects`, `sandbox/exports`, and `sandbox/deployments`.

- [ ] Restart `nova_enhanced_server.py` on port `3000`.
- [ ] Verify the music website appears in Projects.
- [ ] Export ZIP and confirm it contains all six pages.
- [ ] Deploy preview and load the copied site.
- [ ] Edit a safe file through the API and confirm the rendered page changes.
- [ ] Browser-check desktop and mobile UI paths with no console errors.
