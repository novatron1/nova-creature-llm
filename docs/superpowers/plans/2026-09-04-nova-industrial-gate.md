# Nova Industrial Gate v1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Produce a reproducible, fail-closed integration verdict for the current Nova source, and investigate the server/synthesizer failures before promotion.

**Architecture:** Reuse existing runtime contracts, permissions, structured reports, proof orchestration, and release gates. Keep unit evidence distinct from real browser/isolation evidence. A dirty workspace is identified by both Git HEAD and a source manifest, never represented as a tested clean commit.

**Tech Stack:** Python, pytest/JUnit, existing Nova runtime, Playwright.

**Spec:** User-approved September 4 integration pass in this task.

## Constraints
- Do not merge or promote in this pass.
- Keep NOVA_AGENT_ALLOW_SHELL=false.
- Preserve existing operator configuration and unrelated changes.
- Zero failures required; skipped/missing required evidence cannot authorize promotion.
- Tests must not treat a fake browser or a copied folder as OS isolation.

## Tasks
- [x] Reproduce the 21 failures with JUnit evidence; classify stale assertions, configuration contamination, and runtime bugs.
- [x] Repair confirmed defects with regression tests; isolate test configuration without changing live settings.
- [x] Add an Industrial Gate command with explicit required suites, subprocess deadlines, source hashes, persisted logs/JUnit, and nonzero failure exit.
- [x] Exercise runtime permission, memory, scheduler, reporting, and rollback contracts; report absent production evidence as blocking.
- [x] Run the gate, inspect its report, and document the exact remaining promotion blockers.

## Verification
Run the server/synthesizer suite and runtime suites before/after. Add tests proving an empty/skipped/failed test report cannot pass, source changes invalidate evidence, and omitted integration phases block promotion. Run the new CLI and retain its machine-readable report under reports/industrial-gate/.

## Execution result

Implemented the audit and required release entry; repaired the initial 21 failures and additional regressions discovered during isolation/review. The gate remains blocked by missing OS-isolation, behavioral-baseline, and identity-restart proof and a dirty source tree. The full-suite follow-up records wider failures separately. No promotion or merge was attempted.
