# Nova GPU Hub and Vast.ai Design

## Goal

Add a standalone GPU Hub that lets the user explicitly choose CPU-only,
local-GPU, automatic, or Vast.ai remote-GPU execution without changing Nova's
normal chat routing behind the user's back. The feature must work from the
desktop and paired phone UI, detect local GPU capability, expose a safe Vast.ai
control path, and remain usable when no GPU is available.

## Scope

The first release contains four independently testable pieces:

1. A compute-mode state machine with `auto`, `cpu`, `local_gpu`, and `vast_gpu`.
2. Local GPU discovery that reports capability, name, memory when available,
   driver/runtime evidence, and a truthful reason when CPU is required.
3. A Vast.ai client/control plane that can authenticate, list instances, show
   instance state, and start/stop only after explicit user confirmation. The
   client never prints or returns the API key.
4. A responsive GPU Hub panel and a small Windows installer/check script. The
   panel shows the active compute mode, local scan result, Vast connection
   status, instance controls, and the remote OpenAI-compatible endpoint used by
   Nova's existing provider layer.

The first release does not grant an AI model unrestricted shell or desktop
control. It does not silently rent a Vast instance, silently switch providers,
or expose Ollama/vLLM directly to the public internet.

## User experience

The GPU Hub is a separate top-level surface, not a chat-model selector. The
user chooses one compute mode:

- **Auto**: use a verified local GPU when available; otherwise use CPU.
- **CPU only**: never use local or remote GPU.
- **Local GPU**: require a verified local GPU and fail clearly if unavailable.
- **Vast.ai GPU**: use the configured Vast instance/endpoint only after the
  user connects and confirms a paid start operation.

The selected mode persists in Nova's local runtime state and can be changed at
any time. A selected-but-unavailable GPU is reported as unavailable; Nova does
not silently fall back. Auto is the only mode allowed to fall back to CPU.

The panel includes `Scan local GPU`, `Connect Vast.ai`, `Refresh instances`,
`Start`, `Stop/release`, and `Test remote model` actions. Start and release
buttons display the target instance and require a second confirmation. Costs
are shown when Vast returns them; if cost data is unavailable, the action is
blocked until the user confirms that limitation.

## Architecture

Nova remains the control plane. A new focused module,
`src/nova_gpu_hub.py`, owns compute-mode validation, local discovery, and the
Vast.ai REST client. The existing provider layer remains responsible for model
inference; the hub only supplies a selected provider endpoint and health
metadata. The existing chat pipeline therefore keeps identity, memory, raw
memory mode, tools, permissions, and verification intact.

All hub routes are served by the existing Nova HTTP server under
`/api/gpu-hub/*`. The browser never receives the Vast API key. The key is read
from `NOVA_VAST_API_KEY` (with an optional local-only environment-file entry),
and only redacted connection state is returned. Remote model endpoints are
validated as private/Tailscale or explicitly approved remote endpoints before
they can be selected.

For Vast.ai, Nova uses Vast's documented REST API for instance discovery and
lifecycle control and an SSH/proxy tunnel or an explicitly configured
OpenAI-compatible endpoint for inference. The hub does not assume a particular
model image; the installer provides a worker bootstrap that can launch vLLM,
SGLang, or Ollama on the rented machine. This keeps the control plane
independent from model choice.

## State and failure handling

Runtime state is stored in an ignored local JSON file with atomic replacement.
It contains the selected mode, non-secret endpoint metadata, and the selected
instance id; it never contains API keys or prompts. State writes are serialized
and recover from a truncated file by returning to `auto`.

Every remote operation has a bounded timeout, a structured error code, and an
audit event without credentials. A missing API key, expired key, stopped
instance, unmapped port, or unhealthy model is shown directly in the Hub. A
failed Vast request never changes Nova's active chat provider. CPU-only mode
continues to work even when all GPU code is unavailable.

## Security and cost boundaries

- Vast API keys remain server-side and are never placed in browser storage,
  HTML, logs, traces, or chat metadata.
- Start/stop/release are explicit, auditable actions; no automatic spending.
- Only the documented Vast API host and the configured model endpoint are
  contacted.
- The remote worker is an inference/training endpoint, not an unrestricted
  command-execution bridge. Any future computer-control capability must use
  Nova's existing scoped tool/approval policy.
- The Windows installer performs local checks and writes no secrets.

## Verification

Automated tests cover mode transitions, CPU fallback, local GPU detection with
mocked `nvidia-smi`, Vast request parsing/redaction, start/stop confirmation,
state persistence, route contracts, and responsive UI controls. Live checks
cover local health, local GPU scan, unauthenticated Vast rejection without
leaking data, and a configured Vast instance/model health check when the user
has set `NOVA_VAST_API_KEY` and supplied an instance. No paid instance is
created automatically during tests.

## Rollback

Setting `NOVA_GPU_HUB_ENABLED=false` disables the UI and routes. Existing
provider/chat behavior remains unchanged. Removing the ignored runtime state
file resets the hub to Auto without touching memory, models, or training data.
