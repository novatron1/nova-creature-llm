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
- uses one generated client identity, one stable conversation ID, and one
  stable session ID;
- covers greeting, affection, day check-in, follow-up, correction,
  relationship support, memory recall, current-fact honesty, uncertainty,
  interruption, and reconnect;
- rejects known generic/off-topic recovery text;
- records only case ID, pass/fail, HTTP status, latency, intent, memory-used
  state, safety state, and response length;
- never writes prompt or response content to its JSON report;
- hashes `conversation_training_data.jsonl` before and after and fails the gate
  if the hash changes.

Deterministic runner/unit result: **PASS — 3 tests**.

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
- safe-area and reduced-motion rules remain present;
- Companion storage keys cannot contain message, history, prompt, image,
  audio, memory, or token;
- Companion modules do not log through the browser console.

Task 11 automated results:

- Companion source/loader/PWA/acceptance-runner pytest matrix:
  **PASS — 28 passed**
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
- Task 11 does not change Nova cognition, model weights, adapters, checkpoints,
  identity, memory, tools, or API behavior.

## Default readiness

**PENDING — DO NOT ENABLE AS DEFAULT YET.**

Companion is available at `/companion`, while Nova Classic remains the
configured default. The release can be considered for default only after the
controller completes all live viewports, the 25-turn no-training run,
performance measurements, full regression, and rollback proof with no failed
gate.
