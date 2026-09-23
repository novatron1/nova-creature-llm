# Industrial runtime hardening evidence

Date: 2026-09-04

## Implemented

- PermissionGateway compares the supplied arguments against the signed arguments hash before allowing execution. Recognized path fields are checked across all supplied fields, nested operations, and path lists; a permitted first path no longer masks a later escaping path.
- Proof app code runs in a separate Python child with a 20-second timeout. Pytest has a 120-second timeout. Timeout returns code 124 and failed verification triggers rollback. A real sleeping-child test validates the timeout, alongside an injected pytest timeout test.
- Before editing app.py, the orchestrator records exact original bytes in rollback/app.py.original. Failed app execution, tests, or browser verification restore those bytes. Unexpected execution/verification exceptions restore app.py before propagating. No new provenance memory is written for failed verification.
- Reports identify the snapshot path, original byte SHA256, whether restoration occurred, and rollback scope. Snapshot availability checks its bytes against the in-memory original, not merely file existence.
- contract.metadata.isolation and report.final_verification.isolation identify copied_workspace and os_sandbox=false, with unrestricted host filesystem/network and subprocess timeout values. Supplied browser/page factories are explicitly labeled fixture in report.browser_evidence.verification_backend.

## Validation

Observed initial regression run: 6 failed, 5 passed. Failures demonstrated argument mutation acceptance, secondary/nested escape acceptance, missing rollback after test/browser failure, and absent pytest timeout. An additional verification exception regression failed before its restoration handler was added.

Final command:

```text
python -m pytest tests/test_nova_runtime_permissions.py tests/test_nova_runtime_end_to_end.py tests/test_nova_runtime_contracts.py tests/test_nova_runtime_agent_report.py tests/test_nova_runtime_memory.py tests/test_nova_runtime_ledger.py tests/test_nova_runtime_scheduler.py tests/test_nova_runtime_verification_playwright.py tests/test_nova_runtime_eval_bank.py -q -p no:cacheprovider
```

Result: initial pass 34 passed in 30.76 seconds, exit 0. Follow-up validation includes relative-path and rollback-state regressions (see update below).

## Remaining industrial limitations

This is a trusted-project proof workflow, not a production terminal sandbox. A copied directory and bounded child process do not restrict filesystem, network, credentials, process descendants, or resource consumption. Timeouts bound the directly launched child, not arbitrary descendant process trees. Arbitrary subprocess side effects outside app.py are not rolled back. Browser fixture tests do not establish real-browser readiness.

Caller invocation remains the proof-job authorization boundary; it is not an independent human approval or enforced OS capability boundary. Contract budgets are descriptive here. PermissionGateway validates recognized path fields, not paths embedded in arbitrary command strings; resource URI binding is not newly implemented because authorize_tool receives no actual resource URI. No claim of full Industrial Gate readiness follows from these tests.


## Follow-up integration fixes

Relative permission paths resolve against contract.workspace_root. Exact-byte restoration now transitions the returned run to rolled_back while final_verification.passed remains false. These were demonstrated by four failing regressions before the fixes (three failure-phase state cases plus relative-path acceptance).

Unexpected execution/verification exceptions restore app.py and propagate to the caller; this error path does not produce a structured agent report or register the run. This remains an observability gap rather than a successful proof. The normal failed-verification path produces its structured report with a failed verdict and rolled_back run state.

Final follow-up validation: the same nine-file runtime command above passed 36 tests in 12.02 seconds, exit 0. Scoped git diff --check passed.
