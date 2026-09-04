# Nova Creature Runtime Integration Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the NovaMind control-plane concepts into Nova Creature as one canonical runtime layer that can carry a real job from contract to verification, memory write, and structured report.

**Architecture:** Build a single runtime foundation on top of the existing gateway, agent, memory, tool, project, and verification modules. The first layer defines the contract, run state, tool/resource abstraction, permission gateway, evidence ledger, provenance-aware memory, Playwright verification, durable research scheduling, and a structured completion report. Later runtime features must reuse these boundaries instead of creating parallel ones.

**Tech Stack:** Python standard library, existing Nova gateway/runtime modules, JSON/JSONL persistence, pytest, Node.js browser-contract tests, Playwright verification hooks, existing project/worktree and checkpoint machinery.

**Spec:** `docs/superpowers/specs/2026-08-28-nova-creature-runtime-integration-foundation-design.md`

## Global Constraints

- One run, one contract, one ledger.
- The model proposes; deterministic code disposes.
- Evidence beats generated text.
- All autonomous actions must be replayable from recorded inputs and hashes.
- Provenance is part of the data model, not an afterthought.
- Adapters are allowed; duplicate runtimes are not.
- Completion is a verified state transition, not a claim.
- The implementation should not wait until every piece is finished before any of it can run.

---

### Task 1: Define the canonical runtime contract and agent run state machine

**Files:**
- Create: `src/nova_runtime/__init__.py`
- Create: `src/nova_runtime/contracts.py`
- Create: `src/nova_runtime/agent_run.py`
- Create: `src/nova_runtime/interfaces.py`
- Create: `tests/test_nova_runtime_contracts.py`

**Interfaces:**
- Consumes: goal text, owner/project/workspace identifiers, allowed tools/resources, and budget values.
- Produces: `RunContract`, `AgentRun`, `AgentRunState`, `ToolDescriptor`, `ResourceDescriptor`, `canonical_json()`, `sha256_json()`, and `build_run_contract()`.

- [ ] **Step 1: Write the failing contract and state tests**

```python
def test_run_contract_is_immutable_and_hash_stable():
    contract = build_run_contract(
        run_id="run_001",
        goal="Edit the project and verify the result",
        owner_id="local-user",
        project_id="nova-creature",
        workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
        allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
        allowed_tools=["filesystem.read", "filesystem.write", "terminal.run"],
        allowed_resources=["filesystem://workspace", "terminal://local"],
        time_budget_seconds=900,
        tool_budget=20,
        cost_budget=0.0,
        memory_budget=8,
    )
    assert contract.contract_hash == sha256_json(contract.to_dict())
    with pytest.raises((AttributeError, TypeError)):
        contract.goal = "changed"


def test_agent_run_state_machine_allows_only_valid_transitions():
    run = AgentRun.create(
        contract=build_run_contract(
            run_id="run_001",
            goal="Edit the project and verify the result",
            owner_id="local-user",
            project_id="nova-creature",
            workspace_root="C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP",
            allowed_roots=["C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"],
            allowed_tools=["filesystem.read", "filesystem.write", "terminal.run"],
            allowed_resources=["filesystem://workspace", "terminal://local"],
            time_budget_seconds=900,
            tool_budget=20,
            cost_budget=0.0,
            memory_budget=8,
        )
    )
    assert run.state == AgentRunState.PLANNED
    run.transition(AgentRunState.AUTHORIZED, reason="approved")
    run.transition(AgentRunState.EXECUTING, reason="starting")
    run.transition(AgentRunState.VERIFYING, reason="tests complete")
    run.transition(AgentRunState.COMPLETED, reason="verified")
    assert run.state == AgentRunState.COMPLETED
```

- [ ] **Step 2: Run the tests and confirm they fail for missing runtime primitives**

Run: `pytest tests/test_nova_runtime_contracts.py -v`

Expected: fail because the `nova_runtime` package and the canonical data classes do not exist yet.

- [ ] **Step 3: Implement the minimal immutable contract and run state classes**

```python
@dataclass(frozen=True, slots=True)
class RunContract:
    run_id: str
    goal: str
    goal_hash: str
    goal_summary: str
    owner_id: str
    project_id: str
    workspace_root: str
    allowed_roots: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    allowed_resources: tuple[str, ...]
    time_budget_seconds: int
    tool_budget: int
    cost_budget: float
    memory_budget: int
    created_at: str
    contract_hash: str


class AgentRunState(str, Enum):
    PLANNED = "planned"
    AUTHORIZED = "authorized"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
```

- [ ] **Step 4: Implement state validation, canonical JSON, and hash helpers**

```python
def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run the focused tests and verify the contract hash, immutability, and transition guards pass**

Run: `pytest tests/test_nova_runtime_contracts.py -v`

- [ ] **Step 6: Commit the contract layer**

```bash
git add src/nova_runtime/__init__.py src/nova_runtime/contracts.py src/nova_runtime/agent_run.py src/nova_runtime/interfaces.py tests/test_nova_runtime_contracts.py
git commit -m "feat: add canonical runtime contract and agent run state"
```

### Task 2: Build the universal tool/resource interface and adapters

**Files:**
- Create: `src/nova_runtime/adapters.py`
- Modify: `src/nova_gateway/tools.py`
- Modify: `src/nova_gateway/mcp.py`
- Modify: `src/nova_gateway/core.py`
- Create: `tests/test_nova_runtime_permissions.py`

**Interfaces:**
- Consumes: tool metadata, resource metadata, existing registry handlers, and the canonical contract.
- Produces: `ToolDescriptor`, `ResourceDescriptor`, `ToolInvocation`, `ToolResult`, `ResourceRead`, `ResourceWrite`, `McpToolSpec`, and adapter factories for filesystem, terminal, browser, GitHub, and research resources.

- [ ] **Step 1: Write failing adapter and descriptor tests**

```python
def test_tool_descriptor_maps_to_mcp_like_shape():
    descriptor = ToolDescriptor(
        tool_id="filesystem.read",
        name="Read File",
        category="filesystem",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        output_schema={"type": "object"},
        required_scopes=("files.read",),
        risk_level="safe",
        read_write_classification="read",
        confirmation_policy="never",
        timeout_seconds=30,
        supports_rollback=False,
        supports_dry_run=True,
        provider="nova-local",
        resource_dependencies=("filesystem://workspace",),
    )
    public = descriptor.to_public_dict()
    assert public["name"] == "Read File"
    assert public["required_scopes"] == ["files.read"]


def test_resource_descriptor_includes_hash_and_owner():
    resource = ResourceDescriptor(
        resource_id="filesystem://workspace",
        uri="file:///workspace",
        resource_type="filesystem",
        owner_id="local-user",
        scope="workspace",
        content_classification="project",
        read_only=False,
        hash="abc123",
        metadata={"root": "C:/Users/nova/Documents/NOVA LLM CREATURE DESKTOP"},
    )
    assert resource.to_public_dict()["hash"] == "abc123"
```

- [ ] **Step 2: Run the focused tests and confirm the adapter layer is missing**

Run: `pytest tests/test_nova_runtime_permissions.py -v`

- [ ] **Step 3: Implement the universal tool/resource dataclasses and MCP-compatible projection helpers**

```python
def build_mcp_tool_spec(descriptor: ToolDescriptor) -> dict[str, Any]:
    return {
        "name": descriptor.tool_id,
        "description": descriptor.name,
        "inputSchema": descriptor.input_schema,
        "outputSchema": descriptor.output_schema,
    }
```

- [ ] **Step 4: Add filesystem, terminal, browser, GitHub, and research adapters that wrap existing Nova capabilities**

```python
def filesystem_resource(path: Path, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_filesystem_path(path, owner_id=owner_id)


def terminal_resource(session_id: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_terminal_session(session_id, owner_id=owner_id)


def browser_resource(url: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_browser_url(url, owner_id=owner_id)


def github_resource(repo: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_github_repo(repo, owner_id=owner_id)


def research_resource(topic: str, *, owner_id: str) -> ResourceDescriptor:
    return ResourceDescriptor.from_research_topic(topic, owner_id=owner_id)
```

- [ ] **Step 5: Bridge the current tool registry into the new interface without changing existing handlers**

```python
def wrap_existing_tool_registry(registry: NovaToolRegistry) -> dict[str, ToolDescriptor]:
    return {
        item["name"]: ToolDescriptor.from_registered_tool(item)
        for item in registry.list()
    }
```

- [ ] **Step 6: Run the adapter and registry tests**

Run: `pytest tests/test_nova_runtime_permissions.py -v`

- [ ] **Step 7: Commit the adapter layer**

```bash
git add src/nova_runtime/adapters.py src/nova_gateway/tools.py src/nova_gateway/mcp.py src/nova_gateway/core.py tests/test_nova_runtime_permissions.py
git commit -m "feat: add universal tool and resource adapters"
```

### Task 3: Add PermissionGateway enforcement and the append-only evidence ledger

**Files:**
- Create: `src/nova_runtime/permissions.py`
- Create: `src/nova_runtime/ledger.py`
- Modify: `src/nova_gateway/core.py`
- Modify: `src/nova_gateway/http.py`
- Modify: `src/nova_agent_loop.py`
- Create: `tests/test_nova_runtime_ledger.py`

**Interfaces:**
- Consumes: `RunContract`, action signatures, tool/resource descriptors, and verification outcomes.
- Produces: `PermissionGateway`, `LedgerEntry`, `EvidenceLedger`, `ActionSignature`, `RollbackAnchor`, and deterministic allow/block decisions.

- [ ] **Step 1: Write the failing permission and ledger tests**

```python
def test_permission_gateway_rejects_workspace_escape():
    gateway = PermissionGateway(contract=contract_with_root("C:/workspace"))
    decision = gateway.authorize_tool(
        tool_id="filesystem.write",
        arguments={"path": "C:/Users/nova/Documents/secrets.txt"},
        action_signature={"tool_id": "filesystem.write", "path": "C:/Users/nova/Documents/secrets.txt"},
    )
    assert decision.disposition == "BLOCK"
    assert decision.rule_id == "WORKSPACE_ESCAPE"


def test_evidence_ledger_is_append_only_and_hash_chained(tmp_path):
    ledger = EvidenceLedger(tmp_path / "ledger.jsonl")
    first = ledger.append(event_type="planned", payload={"goal_hash": "g1"})
    second = ledger.append(event_type="authorized", payload={"goal_hash": "g1"})
    assert first.entry_hash != second.entry_hash
    assert second.previous_hash == first.entry_hash
```

- [ ] **Step 2: Run the tests and confirm the enforcement layer is missing**

Run: `pytest tests/test_nova_runtime_ledger.py -v`

- [ ] **Step 3: Implement deterministic action signatures and contract-bound authorization**

```python
@dataclass(frozen=True, slots=True)
class ActionSignature:
    tool_id: str
    arguments_hash: str
    resource_hash: str
    contract_hash: str
```

- [ ] **Step 4: Implement the append-only ledger with hash chaining and redacted payloads**

```python
@dataclass(frozen=True, slots=True)
class LedgerEntry:
    sequence: int
    event_type: str
    timestamp: str
    payload_hash: str
    previous_hash: str
    entry_hash: str
```

- [ ] **Step 5: Wire the gateway into the current agent loop and HTTP surface so unauthorized actions fail before execution**

```python
def authorize_action(self, contract: RunContract, action: ActionSignature) -> PermissionDecision:
    return PermissionDecision(
        disposition="ALLOW",
        rule_id="ALLOW_EXACT_SIGNATURE",
        message="Action matches the frozen contract.",
        can_continue=True,
        rollback_available=False,
        evidence_refs=(),
    )


def record_ledger_event(self, entry: LedgerEntry) -> None:
    self._append_jsonl(self.ledger_path, entry.to_dict())
```

- [ ] **Step 6: Run the permission and ledger tests**

Run: `pytest tests/test_nova_runtime_ledger.py tests/test_nova_gateway_core.py -v`

- [ ] **Step 7: Commit the enforcement layer**

```bash
git add src/nova_runtime/permissions.py src/nova_runtime/ledger.py src/nova_gateway/core.py src/nova_gateway/http.py src/nova_agent_loop.py tests/test_nova_runtime_ledger.py
git commit -m "feat: add permission gateway and evidence ledger"
```

### Task 4: Add provenance-aware memory writes and rollback references

**Files:**
- Create: `src/nova_runtime/memory_provenance.py`
- Modify: `src/nova_gateway/memory.py`
- Modify: `src/nova_gateway/core.py`
- Create: `tests/test_nova_runtime_memory.py`

**Interfaces:**
- Consumes: memory content, owner, source, write reason, previous version hash, and rollback anchors.
- Produces: `ProvenanceMemoryRecord`, `ProvenanceMemoryStore`, `MemoryWriteResult`, and migration helpers for the existing store.

- [ ] **Step 1: Write the failing provenance memory tests**

```python
def test_provenance_memory_record_contains_lineage():
    record = ProvenanceMemoryRecord(
        memory_id="mem_1",
        owner_id="local-user",
        source="agent_run",
        timestamp="2026-08-28T13:00:00Z",
        confidence=0.92,
        write_reason="verified project lesson",
        content_hash="abc",
        previous_version_hash="prev",
        rollback_point="ledger:42",
    )
    assert record.to_dict()["rollback_point"] == "ledger:42"


def test_memory_write_rejects_missing_provenance():
    store = ProvenanceMemoryStore(
        ledger_path=tmp_path / "memory-ledger.jsonl",
        owner_id="local-user",
        mode="automatic_safe_write",
    )
    with pytest.raises(ValueError):
        store.write(content="lesson", owner_id="local-user", source="", write_reason="", confidence=1.0)
```

- [ ] **Step 2: Run the tests and confirm the provenance wrapper is missing**

Run: `pytest tests/test_nova_runtime_memory.py -v`

- [ ] **Step 3: Implement provenance-aware memory records and write validation**

```python
@dataclass(frozen=True, slots=True)
class ProvenanceMemoryRecord:
    memory_id: str
    owner_id: str
    source: str
    timestamp: str
    confidence: float
    write_reason: str
    content_hash: str
    previous_version_hash: str | None
    rollback_point: str | None
    ledger_entry_hash: str | None
```

- [ ] **Step 4: Wrap the existing long-term memory store so autonomous writes go through the provenance layer first**

```python
def write_provenance_memory(store: ExistingNovaMemoryStore, record: ProvenanceMemoryRecord) -> dict[str, Any]:
    return store.write(
        content=record.content,
        owner_id=record.owner_id,
        source=record.source,
        write_reason=record.write_reason,
        confidence=record.confidence,
        previous_version_hash=record.previous_version_hash,
        rollback_point=record.rollback_point,
        ledger_entry_hash=record.ledger_entry_hash,
    )
```

- [ ] **Step 5: Persist rollback references and content hashes in the runtime ledger**

- [ ] **Step 6: Run the memory tests and a focused gateway test that exercises a provenance write**

Run: `pytest tests/test_nova_runtime_memory.py tests/test_nova_gateway_core.py -v`

- [ ] **Step 7: Commit the memory layer**

```bash
git add src/nova_runtime/memory_provenance.py src/nova_gateway/memory.py src/nova_gateway/core.py tests/test_nova_runtime_memory.py
git commit -m "feat: add provenance-aware memory writes"
```

### Task 5: Make Playwright verification first-class and evidence-backed

**Files:**
- Create: `src/nova_runtime/verification_playwright.py`
- Modify: `src/nova_quality_gate_agent.py`
- Modify: `src/nova_gateway/http.py`
- Create: `tests/test_nova_runtime_verification_playwright.py`
- Create: `tests/js/test_nova_runtime_verification_playwright.js`

**Interfaces:**
- Consumes: a target URL, optional assertions, and the current verification contract.
- Produces: `PlaywrightVerificationResult`, screenshot artifact paths, DOM assertion summaries, console/network summaries, and failure trace hashes.

- [ ] **Step 1: Write failing verification tests for screenshot, DOM, console, and network capture**

```python
def test_playwright_verification_result_has_artifacts():
    result = verify_playwright_page(
        url="http://127.0.0.1:3000/",
        assertions=[{"type": "text", "selector": "body", "contains": "Nova"}],
    )
    assert "screenshot_hash" in result
    assert "console_summary" in result
    assert "network_summary" in result
```

- [ ] **Step 2: Run the tests and confirm the runtime verifier is missing**

Run: `pytest tests/test_nova_runtime_verification_playwright.py -v`

- [ ] **Step 3: Implement the verifier as a first-class runtime service**

```python
def verify_playwright_page(url: str, assertions: list[dict[str, Any]], *, timeout_seconds: int = 30) -> dict[str, Any]:
    verifier = PlaywrightVerifier(timeout_seconds=timeout_seconds)
    result = verifier.verify(url=url, assertions=assertions)
    return result.to_dict()
```

- [ ] **Step 4: Add a Node browser-contract test that checks the JS-facing report shape and failure trace contract**

```javascript
test("Playwright verification report includes screenshot and failure trace fields", async () => {
  const report = await verifyUrl("http://127.0.0.1:3000/");
  expect(report).toHaveProperty("screenshot_hash");
  expect(report).toHaveProperty("dom_hash");
  expect(report).toHaveProperty("console_summary");
});
```

- [ ] **Step 5: Wire the verifier into the quality-gate and HTTP surfaces so browser evidence can be requested and exported**

- [ ] **Step 6: Run the Python and Node verification tests**

Run: `pytest tests/test_nova_runtime_verification_playwright.py -v && node --test tests/js/test_nova_runtime_verification_playwright.js`

- [ ] **Step 7: Commit the verification layer**

```bash
git add src/nova_runtime/verification_playwright.py src/nova_quality_gate_agent.py src/nova_gateway/http.py tests/test_nova_runtime_verification_playwright.py tests/js/test_nova_runtime_verification_playwright.js
git commit -m "feat: add first-class Playwright verification"
```

### Task 6: Turn research into durable task records with restart-safe budgets

**Files:**
- Create: `src/nova_runtime/research_scheduler.py`
- Modify: `src/v404_research_scheduler.py`
- Modify: `src/v405_research_priority_ranker.py`
- Modify: `src/v406_research_safety_gate.py`
- Modify: `src/v498_research_audit_log.py`
- Create: `tests/test_nova_runtime_scheduler.py`

**Interfaces:**
- Consumes: objective text, tool budget, time budget, cost budget, restart state, and heartbeat state.
- Produces: `ResearchTaskRecord`, `ResearchScheduler`, `ResearchResumeState`, and durable JSONL task updates.

- [ ] **Step 1: Write failing scheduler tests for restart, heartbeat, and budget enforcement**

```python
def test_scheduler_resumes_pending_task_after_restart(tmp_path):
    scheduler = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    task = scheduler.create_task(objective="collect evidence", tool_budget=3, time_budget_seconds=120, cost_budget=0.0)
    scheduler.mark_running(task.task_id)
    scheduler2 = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    resumed = scheduler2.recover_pending_tasks()
    assert resumed[0].task_id == task.task_id


def test_scheduler_blocks_budget_overrun(tmp_path):
    scheduler = ResearchScheduler(store_path=tmp_path / "research_tasks.jsonl")
    task = scheduler.create_task(objective="collect evidence", tool_budget=1, time_budget_seconds=10, cost_budget=0.0)
    with pytest.raises(BudgetExceededError):
        scheduler.record_tool_use(task.task_id, tool_name="web_search")
        scheduler.record_tool_use(task.task_id, tool_name="web_search")
```

- [ ] **Step 2: Run the tests and confirm durable records are missing**

Run: `pytest tests/test_nova_runtime_scheduler.py -v`

- [ ] **Step 3: Implement durable task records with explicit status, retry, and heartbeat fields**

```python
@dataclass(frozen=True, slots=True)
class ResearchTaskRecord:
    task_id: str
    run_id: str
    objective: str
    status: str
    attempt_count: int
    tool_budget: int
    time_budget_seconds: int
    cost_budget: float
    created_at: str
    updated_at: str
    next_retry_at: str | None
    last_heartbeat_at: str | None
```

- [ ] **Step 4: Reuse the existing research ranker and safety gate as pluggable decision inputs instead of a timer**

- [ ] **Step 5: Persist every scheduler transition so restart recovery is deterministic**

- [ ] **Step 6: Run the scheduler tests**

Run: `pytest tests/test_nova_runtime_scheduler.py tests/test_nova_gateway_core.py -v`

- [ ] **Step 7: Commit the scheduler layer**

```bash
git add src/nova_runtime/research_scheduler.py src/v404_research_scheduler.py src/v405_research_priority_ranker.py src/v406_research_safety_gate.py src/v498_research_audit_log.py tests/test_nova_runtime_scheduler.py
git commit -m "feat: add durable research scheduler"
```

### Task 7: Build the behavioral eval bank and runner for Nova Creature

**Files:**
- Create: `src/nova_runtime/eval_bank.py`
- Create: `tests/fixtures/nova_creature_behavior_eval_bank.json`
- Create: `tests/test_nova_runtime_eval_bank.py`
- Modify: `src/nova_capability_eval.py`
- Modify: `tests/evals/harness.py`

**Interfaces:**
- Consumes: stable prompts, expected behaviors, and evidence requirements.
- Produces: `BehaviorEvalCase`, `BehaviorEvalBank`, `BehaviorEvalResult`, and bank loading/scoring helpers.

- [ ] **Step 1: Write failing eval-bank tests for coverage and loading**

```python
def test_behavior_eval_bank_covers_required_categories():
    bank = load_behavior_eval_bank("tests/fixtures/nova_creature_behavior_eval_bank.json")
    categories = {case.category for case in bank.cases}
    assert {"conversation_quality", "memory_recall", "planning", "tool_choice", "tool_refusal", "self_correction", "research_accuracy", "multi_step_completion"} <= categories
```

- [ ] **Step 2: Run the tests and confirm the bank does not exist yet**

Run: `pytest tests/test_nova_runtime_eval_bank.py -v`

- [ ] **Step 3: Create the eval bank JSON and loader with explicit pass/fail criteria**

```python
@dataclass(frozen=True, slots=True)
class BehaviorEvalCase:
    case_id: str
    category: str
    prompt: str
    expected_behavior: str
    required_evidence: tuple[str, ...]
    pass_criteria: str
```

- [ ] **Step 4: Add a runner that can score the bank against the runtime without leaking private content**

- [ ] **Step 5: Wire the bank into the existing capability-eval flow so it can be executed repeatedly**

- [ ] **Step 6: Run the eval-bank tests**

Run: `pytest tests/test_nova_runtime_eval_bank.py tests/test_nova_capability_eval.py -v`

- [ ] **Step 7: Commit the eval bank**

```bash
git add src/nova_runtime/eval_bank.py tests/fixtures/nova_creature_behavior_eval_bank.json tests/test_nova_runtime_eval_bank.py src/nova_capability_eval.py tests/evals/harness.py
git commit -m "feat: add Nova Creature behavioral eval bank"
```

### Task 8: Add the structured agent report and the first end-to-end proof job

**Files:**
- Create: `src/nova_runtime/agent_report.py`
- Create: `src/nova_runtime/orchestrator.py`
- Modify: `src/nova_gateway/core.py`
- Modify: `src/nova_gateway/http.py`
- Modify: `nova_enhanced_server.py`
- Create: `scripts/run_nova_creature_proof_job.py`
- Create: `tests/test_nova_runtime_agent_report.py`
- Create: `tests/test_nova_runtime_end_to_end.py`

**Interfaces:**
- Consumes: `RunContract`, `AgentRun`, permission decisions, ledger entries, verification results, and provenance memory writes.
- Produces: `StructuredAgentReport`, `StructuredAgentReportSection`, `OrchestratedRunResult`, and API responses for run status/report retrieval.

- [ ] **Step 1: Write the failing structured-report and end-to-end tests**

```python
def test_agent_report_includes_required_sections():
    report = StructuredAgentReport(
        goal="update one project file and verify it",
        plan=["read", "edit", "test", "verify"],
        tools_used=["filesystem.read", "filesystem.write", "terminal.run", "playwright.verify"],
        files_changed=["src/example.py"],
        tests_executed=["pytest tests/test_example.py -q"],
        browser_evidence={"screenshot_hash": "abc"},
        failures_and_retries=[],
        final_verification={"passed": True},
        unresolved_blockers=[],
        rollback_information={"available": True},
    )
    public = report.to_dict()
    assert public["goal"] == "update one project file and verify it"
    assert "tests_executed" in public


def test_end_to_end_proof_job_produces_verified_report(tmp_path):
    result = run_proof_job(project_root=tmp_path)
    assert result.report.final_verification["passed"] is True
    assert result.run.state == "completed"
```

- [ ] **Step 2: Run the tests and confirm the orchestrator/report do not exist yet**

Run: `pytest tests/test_nova_runtime_agent_report.py tests/test_nova_runtime_end_to_end.py -v`

- [ ] **Step 3: Implement the structured report and runtime orchestrator**

```python
@dataclass(frozen=True, slots=True)
class StructuredAgentReport:
    goal: str
    plan: list[str]
    tools_used: list[str]
    files_changed: list[str]
    tests_executed: list[str]
    browser_evidence: dict[str, Any]
    failures_and_retries: list[dict[str, Any]]
    final_verification: dict[str, Any]
    unresolved_blockers: list[str]
    rollback_information: dict[str, Any]
```

- [ ] **Step 4: Expose run creation/status/report endpoints through the gateway**

Suggested routes:

- `POST /nova/v1/agent-runs`
- `GET /nova/v1/agent-runs/<run_id>`
- `GET /nova/v1/agent-runs/<run_id>/report`
- `POST /nova/v1/agent-runs/<run_id>/rollback`

- [ ] **Step 5: Implement the first proof job script to read a project, modify one file in an isolated workspace, run tests, verify with Playwright, write provenance memory, and print the structured report path**

- [ ] **Step 6: Run the focused report/end-to-end tests and the proof job against a disposable local fixture**

Run:

```bash
pytest tests/test_nova_runtime_agent_report.py tests/test_nova_runtime_end_to_end.py -v
python scripts/run_nova_creature_proof_job.py
```

- [ ] **Step 7: Commit the orchestrator and report layer**

```bash
git add src/nova_runtime/agent_report.py src/nova_runtime/orchestrator.py src/nova_gateway/core.py src/nova_gateway/http.py nova_enhanced_server.py scripts/run_nova_creature_proof_job.py tests/test_nova_runtime_agent_report.py tests/test_nova_runtime_end_to_end.py
git commit -m "feat: add structured agent report and proof job"
```

## Final verification

- [ ] Run the focused Python tests for all runtime foundation modules.
- [ ] Run the Node Playwright-contract test.
- [ ] Run `py_compile` on the new runtime modules and `git diff --check`.
- [ ] Run the first end-to-end proof job and archive the report, ledger, screenshot, and test outputs.
- [ ] Confirm the proof job completes without leaking secrets, raw prompts, or hidden reasoning.
