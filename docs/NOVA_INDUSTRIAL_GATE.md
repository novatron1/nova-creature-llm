# Nova Industrial Gate v1

Run the audit from the repository root:

```powershell
python tools/run_nova_industrial_gate.py --output reports/industrial-gate/<new-run-name> --timeout 600
```

Each output directory must be new. Exit 0 means all required evidence passed; exit 1 means the report contains blocking failures or missing evidence; exit 2 means the CLI could not initialize or write the audit. `--scope focused` omits the full unit suite and is always insufficient for a release. `--timeout` is a deadline per subprocess. The existing release runner supervises descendant processes and sanitizes the environment; it is not an OS filesystem/network sandbox.

The command records Git HEAD, branch, dirty status, a per-file SHA-256 source/input manifest before and after execution, Python version, exact commands, JUnit counts, bounded sanitized output tails, and a StructuredAgentReport. Generated reports, runtime memories, and model files are outside the source manifest; this is source evidence, not a model-weight release attestation. Dirty source is never described as a tested clean commit. Source changes during the run invalidate the verdict. Missing, empty, failed, errored, or skipped required test evidence blocks it. Partial browser evidence is retained if the proof fails.

Required phases include server/synthesizer regression, runtime contracts/permissions/ledger/scheduler/memory/reporting, memory and conversation tests, release rollback tests, the full unit suite, a real Playwright fixture, and an intentional failing fixture with exact-byte rollback and no success-memory write. The real proof makes a known small edit only in its copied fixture; it does not edit the user's application. Its screenshot bytes are checked against the recorded hash. Fake browser tests are labeled unit evidence and cannot stand in for the real-browser phase.

The release lock now requires this audit in its default gate list. The audit itself never merges, promotes, or rolls back the user's branch. NOVA_AGENT_ALLOW_SHELL is forced false in the release runner's sanitized environment.

## Additional executed proof phases

- **Sandboxed terminal:** `tools/nova_sandbox_proof.py` launches an actual Windows Sandbox guest with network and clipboard disabled, a read-only fixture input, and a dedicated output mount. The verifier checks nonce, run ID, original and edited hashes, and terminal output. Missing guest evidence fails closed. This is a deterministic fixture proof, not a sandboxed full application suite.
- **Behavioral baseline:** `tools/nova_behavior_proof.py` executes the configured local Ollama model through Nova's prompt builder against eight isolated scenarios. Responses, tool traces, model digest, category scores, and a strict 1.0 threshold are recorded. Protocol errors are distinguished from behavioral assertions. Fixture tools and memory do not establish complete production-agent quality.
- **Identity across restart:** `tools/nova_identity_proof.py` runs actual managed chat turns in separate processes against an isolated SQLite identity store. User names and assistant aliases are scoped by owner; private and gateway permissions are checked.

The audit invokes these verifiers itself and retains partial outputs. Both a successful subprocess and an explicit successful report are required. There is no external success-file override. Failed tests, unresolved skips and dirty source block release.

This gate targets the Windows desktop. Eleven exact Linux/POSIX-only checks are reported as not applicable on Windows, retaining their original JUnit skip counts; this does not certify Linux. Unknown skips remain blocking. The host directory-symlink permission skip can be covered only by a successful separate Windows Sandbox proof that runs Nova's actual snapshot policy against a real symbolic link. `tools/run_nova_linux_platform_proofs.py` remains available for a separate Linux proof run.

The release lock commits its private source snapshot before gates, then commits the release manifest and repeats gates against that final commit. It records the tested commit and rejects source, manifest, HEAD or cleanliness changes after verification. A failed private commit is never marked promotable.

Proof rollback currently restores app.py only. Exceptional proof runs restore it but do not yet persist the same complete structured report as normal failed verification; the outer audit retains available artifacts and reports the subprocess failure. General arbitrary-project rollback, independently authorized execution, and durable AgentRun recovery remain outside this v1 audit.
