# Nova Companion Release Audit

Status: **PENDING CONTROLLER LIVE ACCEPTANCE**

This document separates automated evidence from browser/device measurements.
Any result that requires the running Nova server or the in-app browser remains
marked **PENDING** until the controller records it. No estimated live result is
presented as measured.

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
- `reports/nova_companion_acceptance.json` — PENDING controller live run

## Routes and feature flags

Source/configuration inspection:

- `/companion`: implemented; live HTTP recheck PENDING
- `/classic`: implemented; live HTTP recheck PENDING
- `/healthz`: implemented; live HTTP recheck PENDING
- `/nova/v1/capabilities`: implemented; live HTTP recheck PENDING
- `/nova/v1/tools`: implemented; live HTTP recheck PENDING
- `/nova/v1/chat`: implemented; 25-turn live gate PENDING
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
**PASS — 80 tests**. The tests exercise both OpenAI adapters, the native HTTP
adapter, provider context, gateway core, and existing `/api/chat` brain route.
Invalid non-Boolean values and remote evaluation clients are rejected; nested
metadata cannot forge the flag; remote/free and local/paid providers are not
called; normal paid requests remain accounted for in both generated and
streamed responses; mutation commands do not invoke memory, training, adapter
runtime control, tool, privacy, emergency, camera, microphone, speaker, or
permission actions; normal turns still retain state; and training data remains
unchanged.

The mutation boundary is backed by a formal registry of every current exact
legacy command alias plus every write/action prefix. Nested mock-voice routing
preserves its evaluation context. Tests exercise the aliases against live
Classic routing with sentinels and prove that memory, permissions, privacy,
training state, all five legacy `_LAST_*` fields, and long-term-memory handlers
remain unchanged.

Paid streaming cost accounting is recorded exactly once at the first terminal
event. Provider-reported actual cost is preferred; if absent, the routing
estimate is used as a conservative actual-cost fallback. Success and error
terminals are covered, duplicate terminal events reuse the same cost record,
and a completed first stream advances the monthly budget before a repeated
request can reach the provider. Evaluation streams are still rejected before
any paid or remote provider call.

Legacy turn-state concurrency uses one explicit re-entrant lock around the
complete Classic/gateway turn. This serializes simultaneous model turns and
may add queue latency under concurrent load, but prevents evaluation state
from being observed by or restored over an ordinary turn. The lock is a
bounded compatibility measure until all five legacy `_LAST_*` fields move to
session-scoped state.

Live 25-turn result: **PENDING**. The controller must run:

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
| `390x844` | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| `430x932` | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| desktop `>=1024px` | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

The controller must record computed widths, scroll positions, screenshots, and
keyboard-only desktop results here.

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
  **PASS — 128 passed**
- Gateway core/adapter/firewall regression matrix:
  **PASS — 64 passed**
- Gateway HTTP/security/portability/foundation regression matrix:
  **PASS — 46 passed**
- Full enhanced-server regression matrix:
  **PASS — 354 passed**
- Final evaluation/training/gateway/server-summary recheck:
  **PASS — 23 passed, 331 deselected**
- Complete Companion JavaScript matrix: **PASS — 111 passed, 0 failed**

Keyboard focus order, focus restoration, and screen-reader behavior on the
live browser/device: **PENDING**.

## Performance

- Navigation start to `data-companion-ready="true"`, five warm local runs:
  **PENDING**
- Median warm shell-ready time: **PENDING**
- Presence-motion frame stability: **PENDING**
- Device/browser limitation notes: **PENDING**

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

Task 11 cross-viewport recheck: **PENDING**.

Manual human microphone transcript and native permission-denial outcome remain
device-dependent limitations; earlier automation did not fabricate them.

## Training hash

Deterministic mutation detection: **PASS**.

Live before/after SHA-256 and unchanged state: **PENDING** in
`reports/nova_companion_acceptance.json`.

## Classic rollback

Nova Classic remains linked at `/classic`, and
`NOVA_COMPANION_DEFAULT=false` currently keeps it as the root fallback.

Controller live proof that Classic opens and remains functional: **PENDING**.
Task 12 must repeat the one-flag rollback proof before any default change.

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

## Default readiness

**PENDING — DO NOT ENABLE AS DEFAULT YET.**

Companion is available at `/companion`, while Nova Classic remains the
configured default. The release can be considered for default only after the
controller completes all live viewports, the 25-turn no-training run,
performance measurements, full regression, and rollback proof with no failed
gate.
