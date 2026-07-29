# Nova Companion Release Audit

Status: **PARTIAL — COMPANION AVAILABLE AT `/companion`**

This document separates automated evidence from measured browser/device
evidence. Unavailable native-device checks remain explicitly limited rather
than estimated.

## Exact Task 11 files

- `tools/run_nova_companion_acceptance.py`
- `tests/test_run_nova_companion_acceptance.py`
- `assets/nova_companion/companion-shell.css`
- `tests/test_nova_companion_source.py`
- `tests/test_nova_companion_evaluation_only.py`
- `src/nova_evaluation_policy.py`
- `src/nova_answer_firewall.py`
- `src/nova_gateway/adapters.py`
- `src/nova_gateway/http.py`
- `src/nova_gateway/providers.py`
- `src/nova_gateway/core.py`
- `nova_enhanced_server.py`
- `reports/NOVA_COMPANION_RELEASE_AUDIT.md`
- `reports/nova_companion_acceptance.json` — completed measured live run

## Routes and feature flags

Source/configuration inspection:

- `/companion`: live PASS
- `/classic`: live PASS by direct click/navigation
- `/`: live PASS and byte-for-byte matched `/classic`
- `/health`: live PASS
- `/healthz`: live PASS
- `/nova/v1/health`: live PASS
- `/v1/models`: live PASS
- `/nova/v1/providers`: live PASS
- `/nova/v1/capabilities`: live PASS
- `/nova/v1/tools`: live PASS
- `/nova/v1/chat`: live PARTIAL — 17 of 25 cases passed
- `NOVA_COMPANION_ENABLED=true`
- `NOVA_COMPANION_DEFAULT=false`

Nova Classic remains the configured default while release acceptance is
incomplete.

## Automated acceptance

The acceptance runner:

- checks the five required shell/health/capability routes;
- sends exactly 25 Nova-native, evaluation-only turns;
- validates `evaluation_only` as a top-level Boolean and carries it through
  the provider-neutral request into Nova's existing cognitive path;
- restricts evaluation mode to trusted local Nova-native requests, forces
  `local_only`, and rejects any routed provider that is not both local and
  free before generation or streaming begins;
- strips Nova-reserved evaluation metadata from both OpenAI Chat Completions
  and Responses adapters so external clients cannot suppress accounting;
- uses one generated client identity, one stable conversation ID, and one
  stable session ID;
- carries only the most recent eight user/assistant messages in process memory
  so follow-up, interruption, and reconnect checks are contextual;
- covers greeting, affection, day check-in, follow-up, correction,
  relationship support, memory recall, current-fact honesty, uncertainty,
  interruption, and reconnect;
- rejects generic/off-topic recovery text through the shared canonical Nova
  answer-firewall predicate;
- records only case ID, pass/fail, HTTP status, latency, intent, memory-used
  state, safety state, and response length;
- never writes prompt or response content to its JSON report;
- forces evaluation requests to be non-retained: no conversation-summary or
  session-log write, no world-model event/checkpoint, no Dream Lab simulation,
  no continuity record, and no cost/request ledger entry;
- blocks training, explicit memory mutation, tools, filesystem/application
  mutation, and dangerous commands before the provider or Classic mutation
  branches can run;
- hashes `conversation_training_data.jsonl` before and after and fails the gate
  if the hash changes.

Deterministic runner result: **PASS — 22 tests**. The additional contract
proves all 25 acceptance prompts remain benign under the same fail-closed
classifier used by production evaluation requests.

Evaluation-only propagation and non-retention result:
**PASS — 180 tests**. The tests exercise both OpenAI adapters, the native HTTP
adapter, provider context, gateway core, and existing `/api/chat` brain route.
Invalid non-Boolean values and remote evaluation clients are rejected; nested
metadata cannot forge the flag; remote/free and local/paid providers are not
called; normal paid requests remain accounted for in both generated and
streamed responses; mutation commands do not invoke memory, training, adapter
runtime control, tool, privacy, emergency, camera, microphone, speaker, or
permission actions; normal turns still retain state; and training data remains
unchanged.

The 25 allowed evaluation cases live in one shared immutable registry. The
runner sends each case ID and Nova Core accepts it only when both the ID and
current prompt exactly match that registry. Missing, unknown, mismatched, or
client-metadata-forged cases are rejected before provider entry. Conversation
history remains process-memory-only and prompt/response content remains absent
from the report.

The mutation boundary also retains a formal registry of every current exact
legacy command alias plus every write/action prefix. At the Classic boundary,
Nova runs the real non-mutating entity, relationship, pet, contextual
relationship, and user-identity parsers before any corresponding save route.
Tests cover every entity alias and every slot alias from `nova_entity_memory`,
plus relationship, pet, contextual, and user-name forms. Nested mock-voice
routing preserves its evaluation context. All adapter selector and path aliases
used by the raw-adapter override are blocked. Tests prove that memory,
permissions, privacy, training state, all five legacy `_LAST_*` fields,
long-term-memory handlers, adapter calls, and disk-save handlers remain
unchanged.

Paid streaming reserves estimated cost atomically before provider stream
execution. The reservation remains charged if the provider raises before a
terminal event or the client closes the generator after a partial delta. A
provider-reported terminal actual cost is reconciled separately without adding
the estimate twice; if actual cost is absent, the ledger honestly remains
estimate-only. Success and error terminals are covered, duplicate terminal
events cannot double-account, and a first stream's reservation advances the
monthly budget before a repeated request can reach the provider. Evaluation
streams are still rejected before any paid or remote provider call.

Legacy turn-state concurrency uses one explicit re-entrant lock around the
complete Classic/gateway turn. This serializes simultaneous model turns and
may add queue latency under concurrent load, but prevents evaluation state
from being observed by or restored over an ordinary turn. The lock is a
bounded compatibility measure until all five legacy `_LAST_*` fields move to
session-scoped state.

Live 25-turn result: **PARTIAL — 17/25 cases passed; 5/5 route checks
passed**. The monitored run took 320,031 ms. Failed case IDs were
`affection_02`, `follow_up_02`, `correction_01`, `uncertainty_02`,
`interruption_01`, `reconnect_01`, `reconnect_02`, and `reconnect_03`.
All failures returned safe HTTP responses; they did not mutate training data.
The failing outputs were not copied into this privacy-safe report.

Reproduction command:

```powershell
py -3.11 tools/run_nova_companion_acceptance.py --base-url http://127.0.0.1:8765 --output reports/nova_companion_acceptance.json
```

## Phone and desktop viewport results

The previously measured `390x844` failure was traced to a single unwrapped
flex composer containing the textarea, Talk, voice-output toggle, Stop, and
Send controls. Their minimum-content widths exceeded the shell.

The bounded repair uses a phone-only grid with three `minmax(0, 1fr)` voice
tracks and one 44px Send track. The textarea spans the complete first row.
The Trust label is also bounded and ellipsized instead of expanding the
topbar. Existing 44px touch targets, safe-area padding, reduced-motion rules,
Adaptive Presence behavior, and voice/composer semantics are preserved.

Required controller measurements:

| Viewport | Body overflow | Composer/focus | Spark/focus trap | Safe area | Classic | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `390x844` | PASS | PASS | PASS | PASS | PASS | PASS |
| `430x932` | PASS | PASS | PASS | PASS | PASS | PASS |
| desktop `1280x800` | PASS | PASS | PASS | PASS | PASS by click | PASS |

The repaired composer remained within the viewport at both phone sizes, focus
kept the composer visible, Spark trapped focus and restored it after Escape,
and the browser console remained clean. Screenshots and detailed limitations
are recorded in the Task 11 live report. Classic was proven by direct
click/navigation; the automation harness did not activate the real link from a
synthetic Enter key, so keyboard-link activation is not separately claimed.

## Accessibility and privacy

Automated source contracts cover:

- every fixed sheet opener has `aria-controls`;
- Nova Spark has accessible text;
- camera and microphone controls are real `button` elements;
- browser zoom is not disabled;
- touch controls remain at least 44px;
- the Classic fallback link is rendered as a real centered 44px touch target;
- safe-area and reduced-motion rules remain present;
- Companion storage keys cannot contain message, history, prompt, image,
  audio, memory, or token;
- Companion modules do not log through the browser console.

Task 11 automated results:

- Companion source/loader/PWA/acceptance-runner pytest matrix:
  **PASS — 228 passed**
- Gateway core/adapter/firewall regression matrix:
  **PASS — 64 passed**
- Gateway HTTP/security/portability/foundation regression matrix:
  **PASS — 46 passed**
- Full enhanced-server regression matrix:
  **PASS — 354 passed**
- Final evaluation/training/gateway/server-summary recheck:
  **PASS — 23 passed, 331 deselected**
- Complete Companion JavaScript matrix: **PASS — 111 passed, 0 failed**

Task 12 final regression results:

- Complete JavaScript matrix: **PASS — 111 passed, 0 failed, 0 skipped,
  3,533.3842 ms**
- Exact Companion/HTTP focused pytest matrix: **PASS — 61 passed, 0 failed,
  61.01 s**
- Entire existing and new pytest suite: **PASS — 1,560 passed, 10 skipped,
  0 failed, 831.61 s**
- Conversation evaluation: **PASS — 560/560**, evaluation-only mode,
  `training_writes=0`, `content_logged=false`,
  `memory_writes_allowed=false`, and `training_allowed=false`

Post-regression final fix wave:

- Companion JavaScript parent suite: **PASS — 115 passed, 0 failed**
- Gateway core/HTTP/security plus Companion source/routes:
  **PASS — 67 passed, 0 failed**
- Python compilation and scoped diff validation: **PASS**
- Independent targeted re-review: **CLEAN — 5/5 JavaScript and 2/2
  cancellation-ownership checks passed**
- Exact current-tree full pytest suite: **PASS — 1,562 passed, 10 skipped,
  0 failed, 697.74 s**
- Closed four cross-feature findings: bounded RAM-only canonical conversation
  history, authenticated per-client cancellation, fail-closed remote Trust,
  and an executable capability-gated Spark Voice action.

The earlier 1,560-case full pytest run and the 560-case conversation
evaluation preceded this bounded plumbing/security fix wave. The current-tree
1,562-case full suite above supersedes the earlier pytest result. The
560-case evaluation was not repeated after the wave.

Keyboard focus into the composer and Spark focus restoration: **PASS**.
Screen-reader announcement behavior was not available in the browser harness
and is not claimed.

## Performance

- Five measured warm shell-ready runs: 6,292 ms, 2,074 ms, 4,685 ms,
  2,407 ms, and 4,868 ms.
- Median warm shell-ready time: **4,685 ms**
- Presence-motion frame stability: **NOT MEASURED**; the browser harness does
  not expose trustworthy frame-timing telemetry.
- Device/browser limitations: native software-keyboard resize,
  screen-reader output, and reduced-motion emulation were unavailable.

No frame-rate or shell-timing estimate is substituted for a measurement.

## Vision and voice

Prior task evidence:

- Selected-picture vision at `390x844`: PASS. The supplied Nova screenshot was
  identified, OCR exposed visible text, image persistence remained false,
  browser camera tracks remained off, and no physical movement was authorized.
- Voice output at `390x844`: PASS after explicit speaker permission. Speaking
  was shown only after audio playback began, and Stop ended playback.
- Automated control covers a stalled recognition engine without falsely
  reporting listening.

Task 11 cross-viewport recheck: controls and availability labels remained
truthful. On this isolated run the current server reported vision and voice
input unavailable; no false-ready state was shown. The prior selected-picture
vision and voice-output evidence remains valid for the configured services
used in those task-specific live runs.

Manual human microphone transcript and native permission-denial outcome remain
device-dependent limitations; earlier automation did not fabricate them.

## Training hash

Deterministic mutation detection: **PASS**.

Live before/after SHA-256: **PASS — unchanged**.
Both hashes were
`423c83035f850183950cb9d22ee322a5526ba4a33cec48b39bd99552a3541e85`.
The acceptance report records `evaluation_only=true` and
`content_logged=false`.

## Classic rollback

Nova Classic remains linked at `/classic`, and
`NOVA_COMPANION_DEFAULT=false` currently keeps it as the root fallback.

Task 12 repeated the proof on an isolated current-build server without touching
the user's services. All ten required routes returned HTTP 200: `/`,
`/companion`, `/classic`, `/health`, `/healthz`, `/nova/v1/health`,
`/v1/models`, `/nova/v1/providers`, `/nova/v1/capabilities`, and
`/nova/v1/tools`.

Content hashes proved the configured root was exactly Classic:

- root: `522a15ebfd9634ed76e1775b626794d43b9f509fdfbede9389d7751d0c0b0f40`
- Classic: `522a15ebfd9634ed76e1775b626794d43b9f509fdfbede9389d7751d0c0b0f40`
- Companion: `8fac33825c9ff5a0d256150876b46371a1dd5ace60f00d407c6ae18254dea3fa`
- `root_equals_classic=true`
- `root_equals_companion=false`

Exact one-flag rollback is `NOVA_COMPANION_DEFAULT=false` followed by a normal
Nova restart. `NOVA_COMPANION_ENABLED=true` may remain set so `/companion`
continues to be available without becoming the default.

## Known limitations

- Native PWA installation and browser-forced offline transitions cannot be
  claimed from the current in-app browser sandbox; cache boundaries are
  covered by executable service-worker tests.
- Automated browser control cannot provide human microphone speech or choose
  the operating system's native microphone permission response.
- Live model latency and answer quality depend on the selected local provider
  and must be measured on the running system.
- Serializing legacy `_LAST_*` state protects correctness but reduces parallel
  turn throughput until those fields become session-local.
- Task 11 does not change Nova cognition, model weights, trained adapters,
  checkpoints, identity, memory contents, tools, or existing response
  contracts. It tightens only the reserved evaluation-control boundary.
- The 25-turn conversational gate failed eight contextual/relationship cases.
  The Companion default must remain disabled until those cognitive failures
  are fixed outside this visual acceptance task and the complete gate passes.
- The 4,685 ms measured median shell-ready time is functional but not yet a
  high-performance release result.
- A 25-turn visual timeline was not replayed into the UI because the
  evaluation-only HTTP run intentionally avoids persistence. The shell was
  exercised directly at all required viewports.
- The recorded 17/25 live conversational score predates the final bounded
  continuity/cancellation/Trust/Voice fix wave. It remains the latest measured
  live score; the 25-turn live runner was not repeated afterward. Default
  promotion therefore remains blocked until a fresh current-build run passes.
- The 560-case evaluation was completed before the final fix wave and was not
  repeated afterward. The exact current post-wave tree was covered by the
  1,562-case full pytest run plus the affected 115 JavaScript and 67 Python
  focused suites.

## Default readiness

**PARTIAL — COMPANION AVAILABLE AT `/companion`.**

Companion is available at `/companion`, while Nova Classic remains the
configured default. Required viewport, cancellation, route, and training
isolation checks passed, the current-tree 1,562-case full regression passed,
the pre-wave 560-case evaluation passed, post-wave focused suites passed, and
the one-flag rollback was proved. Default promotion remains blocked until the
current build passes a fresh 25-turn live quality gate. Configuration remains
`NOVA_COMPANION_ENABLED=true` and `NOVA_COMPANION_DEFAULT=false`.
