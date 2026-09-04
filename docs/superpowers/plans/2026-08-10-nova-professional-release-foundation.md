# Nova Professional Release Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a reproducible, privacy-safe, session-isolated Nova source release and promote Companion only after the exact candidate passes every professional readiness gate.

**Architecture:** Implement the existing Release Lock plan first so subsequent work occurs against an explicit candidate boundary. Add a bounded SessionRuntimeStore and typed RequestExecutionContext beside the current gateway, migrate the legacy brain globals behind a compatibility adapter, record only allowlisted content-free events, and use one truthful readiness controller to gate Companion promotion. Preserve the current Cognitive OS, provider interfaces, persistent memory, Classic UI, models, and user data.

**Tech Stack:** Python 3.11 standard library, existing nova_protocol dataclasses, Nova Gateway, pytest, Node's built-in test runner, Git worktrees, JSON/JSONL, and local HTTP smoke tests.

## Global Constraints

- Do not clean, reset, overwrite, bulk-stage, or commit unrelated files from the live dirty worktree.
- Do not stop, restart, or reconfigure the user's running Nova service during implementation or isolated verification.
- Do not modify model weights, checkpoints, adapters, private memory, training datasets, generated media, or provider credentials.
- Tests use temporary directories, isolated configuration, fake providers, and non-retaining evaluation requests.
- Reports never contain prompts, responses, memory values, attachments, image/audio content, authentication material, or secrets.
- Evaluation remains local, free, non-retaining, non-mutating, and unable to suppress normal accounting.
- Ambiguous release content, stale evidence, missing evidence, unsafe paths, failed tests, and failed live cases block promotion.
- Classic remains available at /classic; Companion rollback remains NOVA_COMPANION_DEFAULT=false followed by a normal operator-controlled restart.
- No remote push, public deployment, package installation, or automatic destructive Git operation is part of this plan.
- Every commit stages only the files listed by its task after git diff --cached --name-only confirms the boundary.

---

## File Structure

### Reuse without redesign

- docs/superpowers/plans/2026-07-30-nova-release-lock.md — complete Release Lock implementation plan executed as Phase 1.
- src/nova_protocol/models.py — authoritative NovaRequest, NovaResponse, and NovaStreamEvent definitions.
- src/nova_conversation_context.py — bounded client-supplied conversation interpretation.
- src/nova_evaluation_policy.py — immutable acceptance registry and fail-closed evaluation policy.
- tools/run_nova_companion_acceptance.py — privacy-safe live acceptance transport and report writer.

### Create

- src/nova_session_runtime.py — validated session keys, bounded transient state, leases, expiry, and safe metrics.
- src/nova_request_execution.py — typed request context, deadlines, cancellation, retention policy, and outcomes.
- src/nova_readiness.py — content-free event schema, event sink, gate states, and readiness snapshots.
- src/nova_readiness_http.py — local-management HTTP controller for safe readiness output.
- src/nova_companion_quality.py — scenario-level acceptance contracts.
- src/nova_companion_promotion.py — deterministic promotion predicate and rollback proof.
- tools/nova_professional_release.py — read-only-by-default operator CLI.
- tests/test_nova_session_runtime.py
- tests/test_nova_request_execution.py
- tests/test_nova_gateway_session_isolation.py
- tests/test_nova_readiness.py
- tests/test_nova_readiness_http.py
- tests/test_nova_companion_quality.py
- tests/test_nova_companion_promotion.py
- tests/test_nova_professional_release.py

### Modify

- src/nova_gateway/core.py:90-790 — own the session store, bind execution contexts, and finalize outcomes.
- src/nova_gateway/providers.py:89-410 — propagate execution context and share cancellation.
- src/nova_gateway/http.py:315-702 — expose readiness locally and preserve validated identity.
- nova_enhanced_server.py:1164-1705,7804-10176,11702-12980,13403-13950 — consume scoped state.
- src/nova_conversation_context.py:40-982 — correction, interruption, and reconnect resolution.
- src/nova_evaluation_policy.py:19-130 — scenario contract metadata without weakening exact matching.
- tools/run_nova_companion_acceptance.py:150-328 — apply content-free quality contracts.
- tests/test_nova_gateway_core.py
- tests/test_nova_gateway_http.py
- tests/test_nova_companion_evaluation_only.py
- tests/test_nova_enhanced_server.py
- tests/test_run_nova_companion_acceptance.py
- tests/test_nova_companion_routes.py
- config/nova_gateway.example.yaml
- README_COGNITIVE_OS.md
- README_LAPTOP_INSTALL.md
- docs/NOVA_COGNITIVE_OPERATING_LAYER.md

---

### Task 1: Establish the reproducible Release Lock boundary

**Files:**
- Plan: docs/superpowers/plans/2026-07-30-nova-release-lock.md
- Create/modify: exactly the files enumerated under that plan's File Structure

**Interfaces:**
- Consumes: repository path, committed source revision, snapshot policy, and explicit operator command.
- Produces: SnapshotPolicy, SnapshotReport, deterministic manifest, guarded candidate worktree, gate report, rollback reference, and explicit promotion controller.

- [ ] **Step 1: Execute the complete Release Lock implementation plan**

Use every test-first task and commit in:

    docs/superpowers/plans/2026-07-30-nova-release-lock.md

Do not begin Task 2 until synthetic repository tests prove the source worktree and local master remain unchanged on failure.

- [ ] **Step 2: Run the focused Release Lock suite**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_release_policy.py tests/test_nova_release_manifest.py tests/test_nova_release_worktree.py tests/test_nova_release_gates.py tests/test_nova_release_lock.py tests/test_nova_release_security.py -q

Expected: zero failures and zero errors.

- [ ] **Step 3: Generate a classification-only preflight**

Run the Release Lock preflight command from docs/NOVA_RELEASE_LOCK.md. It may write only beneath the verified Git administrative report root, must make no worktree changes, and must return either a complete classification or an explicit ambiguous-path block.

- [ ] **Step 4: Record the candidate boundary**

Record candidate worktree, branch, source commit, policy version, and manifest version in the Release Lock run report. Later tasks operate in that candidate worktree or a feature worktree derived from its commit, never by bulk-staging the live workspace.

---

### Task 2: Build the bounded session runtime store

**Files:**
- Create: src/nova_session_runtime.py
- Create: tests/test_nova_session_runtime.py

**Interfaces:**
- Consumes: client_id, conversation_id, session_id, monotonic clock, and persist Boolean.
- Produces: SessionKey.from_values(), SessionTurnState, SessionLease, SessionRuntimeStore.acquire(), clear(), prune(), and safe_metrics().

- [ ] **Step 1: Write failing identity, isolation, bound, expiry, and discard tests**

    from nova_session_runtime import SessionKey, SessionRuntimeStore

    def test_sessions_with_different_clients_never_share_turn_state() -> None:
        store = SessionRuntimeStore(max_records=4, idle_ttl_seconds=60)
        first = SessionKey.from_values("client-a", "conversation", "session")
        second = SessionKey.from_values("client-b", "conversation", "session")
        with store.acquire(first) as lease:
            lease.state.previous_user = "private-a"
            lease.commit()
        with store.acquire(second) as lease:
            assert lease.state.previous_user == ""

    def test_non_persistent_lease_discards_evaluation_state() -> None:
        store = SessionRuntimeStore()
        key = SessionKey.from_values("eval", "conversation", "session")
        with store.acquire(key, persist=False) as lease:
            lease.state.previous_user = "evaluation prompt"
            lease.commit()
        assert store.contains(key) is False

Also assert separators, control characters, empty values, and values over 160 characters raise ValueError. safe_metrics() exposes counts and limits only.

- [ ] **Step 2: Run the test and verify the module is absent**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_session_runtime.py -q

Expected: collection fails with ModuleNotFoundError for nova_session_runtime.

- [ ] **Step 3: Implement exact key and state types**

    @dataclass(frozen=True, slots=True)
    class SessionKey:
        client_id: str
        conversation_id: str
        session_id: str

        @classmethod
        def from_values(cls, client_id: str, conversation_id: str, session_id: str) -> "SessionKey":
            values = []
            for label, raw in (
                ("client_id", client_id),
                ("conversation_id", conversation_id),
                ("session_id", session_id),
            ):
                value = str(raw or "").strip()
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,159}", value) is None:
                    raise ValueError(f"Invalid {label}.")
                values.append(value)
            return cls(*values)

    @dataclass(slots=True)
    class SessionTurnState:
        previous_user: str = ""
        previous_answer: str = ""
        web_lookup_topic: str = ""
        web_lookup_kind: str = ""
        web_lookup_items: list[dict[str, Any]] = field(default_factory=list)
        generation: int = 0

        def clone(self) -> "SessionTurnState":
            return SessionTurnState(
                previous_user=self.previous_user,
                previous_answer=self.previous_answer,
                web_lookup_topic=self.web_lookup_topic,
                web_lookup_kind=self.web_lookup_kind,
                web_lookup_items=copy.deepcopy(self.web_lookup_items),
                generation=self.generation,
            )

Validation uses the full-match expression [A-Za-z0-9][A-Za-z0-9._:@-]{0,159}. Clone web_lookup_items with copy.deepcopy.

- [ ] **Step 4: Implement leases and bounded eviction**

SessionRuntimeStore defaults to max_records=1024 and idle_ttl_seconds=3600. Each entry owns an RLock, state, last-access monotonic timestamp, and active count. acquire(key, persist=True) returns a context-managed cloned lease. commit() increments generation and replaces state only when persist is true. prune() removes expired inactive entries, then least-recently-used inactive entries above the maximum. Active entries are never evicted.

- [ ] **Step 5: Run tests**

Include two threads entering different keys concurrently and same-key commits remaining ordered. Expected: all pass.

- [ ] **Step 6: Commit**

    git add src/nova_session_runtime.py tests/test_nova_session_runtime.py
    git diff --cached --name-only
    git commit -m "feat: add bounded Nova session runtime"

---

### Task 3: Add the typed request execution boundary

**Files:**
- Create: src/nova_request_execution.py
- Create: tests/test_nova_request_execution.py

**Interfaces:**
- Consumes: NovaRequest, SessionRuntimeStore, cancellation Event, clock, and timeout.
- Produces: ExecutionStatus, ExecutionStopped, ExecutionOutcome, RequestExecutionContext.open(), remaining_seconds(), raise_if_stopped(), complete(), fail(), and safe_event_fields().

- [ ] **Step 1: Write failing deadline, cancellation, retention, and safe-field tests**

    def test_evaluation_context_is_non_retaining_and_content_free() -> None:
        request = nova_request(metadata={
            "evaluation_only": True,
            "_nova_evaluation_trusted": True,
        })
        with RequestExecutionContext.open(request, SessionRuntimeStore(), timeout_seconds=30) as execution:
            assert execution.retention_allowed is False
            assert execution.session_lease.persist is False
            fields = execution.safe_event_fields()
            assert "messages" not in fields
            assert "metadata" not in fields

Use a fake clock to prove a reached deadline raises ExecutionStopped with TIMEOUT and a set event produces CANCELLED.

- [ ] **Step 2: Run tests and verify import failure**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_request_execution.py -q

- [ ] **Step 3: Implement statuses and outcome**

    class ExecutionStatus(str, Enum):
        RUNNING = "running"
        SUCCESS = "success"
        SAFE_REFUSAL = "safe_refusal"
        UNAVAILABLE = "unavailable"
        CANCELLED = "cancelled"
        TIMEOUT = "timeout"
        INTERNAL_ERROR = "internal_error"

    @dataclass(frozen=True, slots=True)
    class ExecutionOutcome:
        status: ExecutionStatus
        error_code: str = ""
        duration_ms: int = 0

RequestExecutionContext.open() builds a SessionKey from NovaRequest, trusts evaluation only when both existing flags are true, opens a non-persistent evaluation lease, and never serializes itself through NovaRequest.to_dict().

- [ ] **Step 4: Implement cancellation and deadlines**

Use one threading.Event per execution. remaining_seconds() is nonnegative. raise_if_stopped() checks cancellation before timeout. Exit discards uncommitted state on exception and releases the lease in finally.

- [ ] **Step 5: Run and commit**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_request_execution.py tests/test_nova_session_runtime.py -q
    git add src/nova_request_execution.py tests/test_nova_request_execution.py
    git diff --cached --name-only
    git commit -m "feat: add typed Nova request execution context"

---

### Task 4: Bind execution and sessions through the Gateway

**Files:**
- Modify: src/nova_gateway/core.py:90-790
- Modify: src/nova_gateway/providers.py:89-410
- Modify: src/nova_gateway/http.py:459-702
- Modify: tests/test_nova_gateway_core.py
- Modify: tests/test_nova_gateway_http.py
- Create: tests/test_nova_gateway_session_isolation.py

**Interfaces:**
- Consumes: SessionRuntimeStore, RequestExecutionContext, and NovaRequest identity.
- Produces: NovaGatewayCore.session_store, internal request attribute _nova_execution_context, provider context key execution_context, and owner-scoped shared cancellation.

- [ ] **Step 1: Write concurrent-session tests**

Create requests with equal conversation/session IDs and different client IDs. A fake runner writes execution_context.session_lease.state.previous_user, waits on a barrier, and returns. Assert no crossover. Add same-key ordering and evaluation-discard tests.

- [ ] **Step 2: Run tests and observe missing constructor support**

Expected: NovaGatewayCore(session_store=store) fails before implementation.

- [ ] **Step 3: Extend NovaGatewayCore**

Add constructor parameters:

    session_store: SessionRuntimeStore | None = None
    execution_timeout_seconds: float = 180.0

Set self.session_store and add _open_execution(request). Wrap generate() and stream(). Attach execution with setattr(request, "_nova_execution_context", execution) so dataclasses.asdict() ignores it. Remove the attribute in finally.

- [ ] **Step 4: Propagate context and cancellation**

In ExistingNovaProvider._request_context():

    execution = getattr(request, "_nova_execution_context", None)
    if execution is not None:
        context["execution_context"] = execution

Streaming reuses execution.cancel_event. cancel(request_id, client_id=request.client_id) retains the owner check and signals the active execution.

- [ ] **Step 5: Commit only successful state**

After answer validation, update scoped final user/assistant values and commit only when retention is allowed. Provider failure, validation failure, timeout, cancellation, and evaluation do not commit. Existing world-model and cost behavior remains unchanged.

- [ ] **Step 6: Run and commit**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_gateway_session_isolation.py tests/test_nova_gateway_core.py tests/test_nova_gateway_http.py tests/test_nova_gateway_adapters.py -q
    git add src/nova_gateway/core.py src/nova_gateway/providers.py src/nova_gateway/http.py tests/test_nova_gateway_session_isolation.py tests/test_nova_gateway_core.py tests/test_nova_gateway_http.py
    git diff --cached --name-only
    git commit -m "feat: isolate Nova gateway sessions"

---

### Task 5: Migrate legacy brain globals behind the session adapter

**Files:**
- Modify: nova_enhanced_server.py:1164-1705,7804-10176,11702-12980
- Modify: tests/test_nova_enhanced_server.py
- Modify: tests/test_nova_companion_evaluation_only.py

**Interfaces:**
- Consumes: context["execution_context"] and SessionTurnState.
- Produces: _turn_state(), _previous_exchange(), _record_turn_result(), _record_web_lookup(), and unscoped fallback behavior.

- [ ] **Step 1: Write failing scoped-state tests**

Call _run_nova_chat_turn_impl() with two fake execution contexts. Seed different prior exchanges and web topics. Assert follow-up, relationship, science, and live-news routes read only their own state. Gateway-scoped calls must not alter the five _LAST_* conversation globals.

- [ ] **Step 2: Add the compatibility adapter**

    def _turn_state(context=None):
        execution = (context or {}).get("execution_context") if isinstance(context, dict) else None
        return execution.session_lease.state if execution is not None else None

    def _previous_exchange(context=None):
        state = _turn_state(context)
        if state is not None:
            return state.previous_user, state.previous_answer
        return _LAST_USER_TEXT, _LAST_NOVA_RESPONSE

_record_turn_result() updates scoped state when present; only an unscoped legacy call updates globals.

- [ ] **Step 3: Replace authoritative reads**

At brain_route() and _run_nova_chat_turn_impl() entry, obtain previous exchange and web lookup fields from scoped state. Pass values into helpers rather than reading globals.

- [ ] **Step 4: Replace authoritative writes**

Replace production assignment pairs to _LAST_USER_TEXT and _LAST_NOVA_RESPONSE with:

    _record_turn_result(context, text, response)

Replace web lookup assignments with _record_web_lookup(context, topic, kind, items). Keep _LAST_TRAINING_REPORT separate.

- [ ] **Step 5: Remove scoped evaluation snapshot/restore**

The legacy lock may remain for unscoped calls. Gateway evaluation uses its non-persistent lease and must not blank or restore another session's globals. Preserve all existing non-mutation tests.

- [ ] **Step 6: Run focused tests**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_gateway_session_isolation.py tests/test_nova_companion_evaluation_only.py tests/test_nova_enhanced_server.py -q -k "context or follow or evaluation or concurrent or gateway or web_lookup"

- [ ] **Step 7: Commit**

Stage only the server and listed tests, verify names, and commit:

    git commit -m "fix: scope Nova conversation state by session"

---

### Task 6: Add privacy-safe readiness events and HTTP output

**Files:**
- Create: src/nova_readiness.py
- Create: src/nova_readiness_http.py
- Create: tests/test_nova_readiness.py
- Create: tests/test_nova_readiness_http.py
- Modify: src/nova_gateway/core.py
- Modify: src/nova_gateway/http.py
- Modify: nova_enhanced_server.py:13403-13950

**Interfaces:**
- Consumes: execution safe fields, release summary, gate artifacts, and session safe metrics.
- Produces: GateState, SafeOperationalEvent, PrivacySafeEventSink.emit(), ReadinessSnapshot, build_readiness_snapshot(), and NovaReadinessHttpController.

- [ ] **Step 1: Write failing allowlist and truthfulness tests**

    def test_event_sink_rejects_content_fields(tmp_path: Path) -> None:
        sink = PrivacySafeEventSink(tmp_path / "events.jsonl")
        with pytest.raises(ValueError):
            sink.emit("request.completed", {"prompt": "private"})

    def test_missing_gate_is_not_a_pass() -> None:
        snapshot = build_readiness_snapshot(required_gates=("python",), observed={})
        assert snapshot.gates["python"].state is GateState.NOT_RUN
        assert snapshot.ready is False

Forbidden fields include prompt, response, content, messages, memory_value, authorization, api_key, token, attachment, image, audio, path, and arguments.

- [ ] **Step 2: Implement schemas**

GateState values are PASS, FAIL, BLOCKED, NOT_RUN, and LIMITED. Events allow trace/request IDs, one-way session hash, route/stage, provider category, local/remote Boolean, tool name, outcome, memory-used Boolean, response length, duration, safety/cancellation/timeout category, and sanitized error code.

- [ ] **Step 3: Add atomic JSONL persistence**

Validate keys, bound strings to 160 characters, reduce exceptions to class names, and append canonical JSON under one lock. safe_metrics() exposes counts and last-event time only.

- [ ] **Step 4: Emit lifecycle events**

Emit start, routed, completed, refused, unavailable, cancelled, timeout, and internal-error categories around generate() and stream(). Never emit request dictionaries, raw metadata, trace content, tool arguments/results, or exception strings.

- [ ] **Step 5: Expose readiness locally**

Add GET /nova/v1/readiness. Include versions, gate states, session metrics, provider health categories, UI flags, and ready. Exclude absolute paths and report contents. Remote unauthenticated callers receive the existing permission error.

- [ ] **Step 6: Test and commit**

Run readiness, Gateway HTTP/security, and enhanced-server route tests. Commit with:

    git commit -m "feat: add truthful Nova release readiness"

---

### Task 7: Define and pass the eight blocked Companion quality contracts

**Files:**
- Create: src/nova_companion_quality.py
- Create: tests/test_nova_companion_quality.py
- Modify: src/nova_evaluation_policy.py:19-130
- Modify: src/nova_conversation_context.py:40-982
- Modify: nova_enhanced_server.py:7804-10176,11702-12980
- Modify: tools/run_nova_companion_acceptance.py:150-328
- Modify: tests/test_run_nova_companion_acceptance.py
- Modify: tests/test_nova_companion_evaluation_only.py

**Interfaces:**
- Consumes: CompanionAcceptanceCase, response text, bounded history, and answer status.
- Produces: QualityDecision and evaluate_companion_response() plus shared contextual resolutions.

- [ ] **Step 1: Write scenario-level contract tests**

Reject empty and generic output for every case. Add these behaviors:

- affection_02: warm without claiming literal human feelings.
- follow_up_02: grounded in the latest substantive exchange.
- correction_01: acknowledges green, treats it as conversation-only, and performs no persistent save.
- uncertainty_02: explicitly permits reasonable disagreement and avoids false certainty.
- interruption_01: stops the prior explanation and remains concise.
- reconnect_01: says only supplied context is available.
- reconnect_02: confirms availability without inventing telemetry.
- reconnect_03: names the latest substantive subject, the short breathing reminder in the registered sequence.

- [ ] **Step 2: Implement content-free decisions**

    @dataclass(frozen=True, slots=True)
    class QualityDecision:
        passed: bool
        reason_codes: Sequence[str]

    def evaluate_companion_response(
        case: CompanionAcceptanceCase,
        content: str,
        history: Sequence[Mapping[str, str]],
    ) -> QualityDecision:
        text = str(content or "").strip()
        lower = " ".join(text.casefold().split())
        reasons: list[str] = []
        if not text:
            reasons.append("empty")
        if contains_generic_fallback(text):
            reasons.append("generic_fallback")
        prompt = case.prompt.casefold()
        if case.scenario == "affection":
            if not any(word in lower for word in ("care", "glad", "here", "talk")):
                reasons.append("cold_affection")
            if any(claim in lower for claim in ("i felt lonely", "i literally missed")):
                reasons.append("false_human_feeling")
        if case.scenario == "correction" and "green" in prompt:
            if "green" not in lower or "conversation" not in lower:
                reasons.append("missed_correction")
        if case.scenario == "uncertainty" and "reasonable people disagree" in prompt:
            if not any(marker in lower for marker in ("can disagree", "may disagree", "different meanings", "subjective")):
                reasons.append("false_certainty")
        if case.scenario == "interruption" and prompt.startswith("stop"):
            if len(text) > 240 or "continuing" in lower:
                reasons.append("continued_after_stop")
        if case.scenario in {"follow_up", "reconnect"}:
            focus = conversation_focus(history)
            if "just before" in prompt:
                subject_words = {
                    word for word in re.findall(r"[a-z0-9]+", focus.subject.casefold())
                    if len(word) > 3
                }
                if not subject_words or not subject_words.intersection(re.findall(r"[a-z0-9]+", lower)):
                    reasons.append("lost_reconnect_subject")
        return QualityDecision(not reasons, tuple(reasons))

Use fixed codes: empty, generic_fallback, missed_correction, false_certainty, continued_after_stop, and lost_reconnect_subject. Reports store codes, never response text.

- [ ] **Step 3: Add shared resolutions**

Extend resolve_contextual_followup() for general correction, stop, reconnection, and availability intents. Use conversation_focus(history). Production routing must not inspect evaluation_case_id when composing answers.

- [ ] **Step 4: Update the runner**

Call evaluate_companion_response(). Store reason codes, HTTP status, latency, intent, memory-used, safety, and response length. Preserve training hashes and exact 25-case count.

- [ ] **Step 5: Run deterministic and isolated live acceptance**

Run quality/evaluation tests with fake providers. Start an isolated candidate server on a non-user port, then:

    py -3.11 tools/run_nova_companion_acceptance.py --base-url http://127.0.0.1:<isolated-port> --output reports/nova_companion_acceptance.json

Expected: 25/25, 5/5 routes, unchanged training hash, evaluation_only=true, content_logged=false. A failure keeps promotion blocked and triggers diagnosis of the shared mechanism.

- [ ] **Step 6: Commit**

Commit listed files with:

    git commit -m "fix: close Nova Companion quality gate"

---

### Task 8: Add deterministic promotion and operator CLI

**Files:**
- Create: src/nova_companion_promotion.py
- Create: tools/nova_professional_release.py
- Create: tests/test_nova_companion_promotion.py
- Create: tests/test_nova_professional_release.py
- Modify: config/nova_gateway.example.yaml
- Modify: tests/test_nova_companion_routes.py

**Interfaces:**
- Consumes: matching Release Lock report, readiness snapshot, live report, full tests, conversation evaluation, training hash, and Classic proof.
- Produces: PromotionDecision, evaluate_companion_promotion(), and read-only status/prepare CLI commands.

- [ ] **Step 1: Write predicate tests**

    def test_not_run_gate_blocks_promotion() -> None:
        decision = evaluate_companion_promotion(candidate(gates={"python": "NOT_RUN"}))
        assert decision.allowed is False
        assert "python:not_run" in decision.blockers

    def test_exact_candidate_with_all_evidence_can_prepare_promotion() -> None:
        decision = evaluate_companion_promotion(fully_passing_candidate())
        assert decision.allowed is True
        assert decision.rollback_value == "NOVA_COMPANION_DEFAULT=false"

- [ ] **Step 2: Implement immutable requirements**

Require matching candidate manifest hash, Python and JavaScript passes, 560/560 conversation evaluation, 25/25 live cases, 5/5 routes, unchanged training hash, security/content scans, clean-start smoke, install/start proof, /classic 200, and root/Companion distinction.

- [ ] **Step 3: Implement read-only-by-default CLI**

status prints safe JSON and exits nonzero when blocked. prepare writes a sanitized candidate configuration patch and instructions but does not restart the user service, merge master, or change live .nova_llm_config.

- [ ] **Step 4: Prove rollback routing**

Use isolated servers with default true and false. /classic stays 200; root equals Companion only when true and Classic when false.

- [ ] **Step 5: Run and commit**

Run promotion, CLI, Companion route, PWA, and source tests. Commit:

    git commit -m "feat: gate Nova Companion promotion on release evidence"

---

### Task 9: Verify the candidate and maintain documentation

**Files:**
- Modify: README_COGNITIVE_OS.md
- Modify: README_LAPTOP_INSTALL.md
- Modify: docs/NOVA_COGNITIVE_OPERATING_LAYER.md
- Create from observed run: reports/nova_professional_release_readiness.json
- Create from observed run: reports/NOVA_PROFESSIONAL_RELEASE_READINESS.md

**Interfaces:**
- Consumes: all earlier tasks and exact candidate.
- Produces: fresh evidence, operating documentation, and honest promotion status.

- [ ] **Step 1: Run focused suites**

    $env:PYTHONPATH = (Resolve-Path ./src)
    py -3.11 -m pytest tests/test_nova_session_runtime.py tests/test_nova_request_execution.py tests/test_nova_gateway_session_isolation.py tests/test_nova_readiness.py tests/test_nova_readiness_http.py tests/test_nova_companion_quality.py tests/test_nova_companion_promotion.py tests/test_nova_professional_release.py -q

- [ ] **Step 2: Run complete Python and JavaScript suites**

Run py -3.11 -m pytest -q and the complete Node command discovered by Release Lock. Record counts, durations, commands, exit statuses, candidate hash, and tool versions.

- [ ] **Step 3: Run conversation and live gates**

Run the 560-case non-retaining evaluation and fresh 25-turn acceptance against the exact candidate. Record content-free results and recheck the training hash.

- [ ] **Step 4: Run clean-start, health, install, and rollback proofs**

Use temporary config/data. Verify required routes, local chat, routing status, temporary memory compatibility, image fixture, /classic, /companion, and both default states. Do not use live user data.

- [ ] **Step 5: Scan artifacts**

Run release security and credential/content-field searches against candidate and reports. Expected: no secret or private-content findings.

- [ ] **Step 6: Update documentation**

Cover prerequisites, dependencies, sanitized config, start/shutdown, readiness states, provider availability, Release Lock, recovery, Classic fallback, rollback, and private-data exclusions.

- [ ] **Step 7: Generate readiness reports**

Include manifest hash, every gate, test counts, live score, route score, training hash, security result, limitations, blockers, rollback, and final status. Missing evidence is NOT_RUN.

- [ ] **Step 8: Run promotion decision**

All passing gates allow a candidate commit and rollback reference. Any non-pass records BLOCKED and leaves live default unchanged.

- [ ] **Step 9: Commit content-free evidence**

Review git diff --check, staged names, and report scans. Commit:

    git commit -m "docs: verify Nova professional release readiness"

---

## Plan Self-Review Checklist

- [ ] Release Lock is proven before later tasks depend on a candidate boundary.
- [ ] Every public type is defined before a later task consumes it.
- [ ] Session keys include client, conversation, and session identity.
- [ ] Different sessions can run concurrently; same-session state is ordered.
- [ ] Request serialization never traverses locks, events, leases, or execution objects.
- [ ] Evaluation leases never persist or interact with normal state.
- [ ] Legacy globals are fallback compatibility only.
- [ ] Cancellation, timeout, provider failure, and validation failure cannot commit state.
- [ ] Readiness events use an allowlist and contain no content or private paths.
- [ ] Quality repairs use shared mechanisms, not case-ID response branches.
- [ ] The exact candidate must reach 25/25; historical scores cannot authorize promotion.
- [ ] Classic and one-flag rollback remain tested.
- [ ] Every task has focused tests, a bounded file list, and an independent commit.
- [ ] No task modifies models, checkpoints, adapters, private memory, training data, or the running service.
