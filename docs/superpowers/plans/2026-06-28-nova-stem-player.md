# Nova Stem Player Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a React/Vite stem-control music workstation that Nova can generate from chat.

**Architecture:** Extend the existing sandbox builder with a third template generator. Keep Nova routing server-side and keep the generated app self-contained under `sandbox/app_builder_projects/Nova_Stem_Player`.

**Tech Stack:** Python builder/router tests, React, Vite, TypeScript, Web Audio API, Vitest.

---

## File Structure

- `src/nova_sandbox_game_builder.py`: request detector and generator for the app files.
- `nova_enhanced_server.py`: route matching music player requests to the builder.
- `nova_chat_web.html`: project and preview links.
- `tests/test_nova_sandbox_game_builder.py`: detector and output tests.
- `tests/test_nova_enhanced_server.py`: route output test if compatible with existing seams.
- `sandbox/app_builder_projects/Nova_Stem_Player/`: generated app files.

## Tasks

### Task 1: Builder Detection

**Files:**
- Modify: `src/nova_sandbox_game_builder.py`
- Modify: `tests/test_nova_sandbox_game_builder.py`

- [ ] Add failing tests for `is_stem_music_player_request`, covering positive music-player/stem prompts and negative music history/questions.
- [ ] Run `py -3.11 -m pytest tests/test_nova_sandbox_game_builder.py -q` and confirm failure because the function is missing.
- [ ] Implement the detector with build verbs, music-player terms, and stem-control terms.
- [ ] Rerun the same test and confirm pass.

### Task 2: React/Vite App Generator

**Files:**
- Modify: `src/nova_sandbox_game_builder.py`
- Modify: `tests/test_nova_sandbox_game_builder.py`
- Create generated files under `sandbox/app_builder_projects/Nova_Stem_Player/`

- [ ] Add failing tests for `build_stem_music_player(tmp_path)`, asserting `package.json`, `index.html`, `src/App.tsx`, `src/audio/stemEngine.ts`, `src/data/demoLibrary.ts`, `src/App.test.tsx`, and metadata files are written.
- [ ] Run the builder tests and confirm failure because the generator is missing.
- [ ] Implement the generator and app file templates.
- [ ] Generate the app into the real sandbox project.
- [ ] Rerun builder tests and confirm pass.

### Task 3: Nova Server Route

**Files:**
- Modify: `nova_enhanced_server.py`
- Modify: `tests/test_nova_enhanced_server.py`

- [ ] Add or extend a server test so a music-player request returns `[APP BUILDER] Created Nova Stem Player`, project URL, and `source=sandbox_app_builder`.
- [ ] Run the server test and confirm failure.
- [ ] Add the route before generic LLM conversation, mirroring the current game-builder path.
- [ ] Rerun focused server tests and confirm pass.

### Task 4: UI Links

**Files:**
- Modify: `nova_chat_web.html`

- [ ] Add project and preview buttons for `/sandbox/app_builder_projects/Nova_Stem_Player/index.html`.
- [ ] Verify the link text appears once in Projects and once in Preview.

### Task 5: Generated App Validation

**Files:**
- Generated app files under `sandbox/app_builder_projects/Nova_Stem_Player/`

- [ ] Run `npm.cmd install` in the generated app.
- [ ] Run `npm.cmd test -- --run`.
- [ ] Run `npm.cmd run build`.
- [ ] Start the app with `npm.cmd run dev -- --host 127.0.0.1`.
- [ ] Verify desktop and mobile render in browser.

### Task 6: Git Publish

**Files:**
- Only intentional app/builder/test/docs changes.

- [ ] Run `git status -sb` and inspect staged scope.
- [ ] Commit with a terse message.
- [ ] Push `codex/nova-stem-player` to `origin`.
