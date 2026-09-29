# Dream Studio: durable local video/audio handoff

Status: written design awaiting user review. No implementation claimed.

## Intent and scope

Keep Nova's existing Dream Studio interface and local engines. Let the user
select a preserved character photo, describe motion, supply a recording or stock
spoken preview, and receive a durable MP4. Run memory-heavy stages sequentially
and release resources between them without closing unrelated applications.

This is the media milestone under the September 26 completion design, not a
replacement for authorization repairs or a declaration that the app is finished.
No paid APIs, new frontend, training, driver changes, or global policy changes.
InfiniteTalk remains a separately validated extension, not a prerequisite for
the honestly labeled audio-overlay path.

## Current evidence

The gateway already has ComfyUI launch/release methods and job polling, but
image_to_video is unsupported. Browser polling currently initiates release.
ComfyUI release requests model unloading, not proven process/RAM reclamation.
The Wan studio uses port 8190, while the existing image service uses 8188.
Existing worker history and downloads must remain accessible.

Prior measurements identify 16 GB system RAM and an 8 GB RTX 3050. These are
planning inputs; admission must use fresh availability measurements. A previous
short Wan render produced motion with artifacts, not accepted final quality.

## Components and responsibilities

1. A backend media coordinator owns admission, FIFO scheduling, cancellation,
   stage transitions and cleanup. Closing a browser cannot abandon cleanup.
   A single resource lease serializes Nova-controlled heavy media stages. It
   cannot prevent unrelated programs or externally submitted ComfyUI jobs.
2. A small SQLite job/asset store records owner, immutable settings, stage,
   backend identity, external prompt ID, timestamps, output manifests and errors.
   Transactions protect transitions; unique request keys prevent duplicate
   submission from repeated clicks. No second queue framework is needed.
3. An asset adapter imports bounded copies into the existing underscore-named
   studio inputs tree. Original photos and audio remain untouched. APIs use
   opaque asset IDs, never caller-selected filesystem destinations. Validate
   media signatures, decoded dimensions/duration, size and path containment.
   Default upload limits: 25 MiB image, 250 MiB audio; clips initially at most
   5 seconds. Reject oversized input before fully buffering it.
4. Engine adapters map supported saved upstream workflows to explicit inputs.
   Keep image ComfyUI 8188 and Wan studio 8190 distinct. Never silently replace
   the configured image endpoint, migrate its history, or adopt its process.
5. A finalizer copies verified outputs into job-specific studio output folders,
   writes a hash/settings manifest and atomically publishes the result. Downloads
   are served by Nova from those artifacts, independent of the worker lifetime.

Prefer focused modules beside existing gateway engines; keep HTTP handling and
Dream Studio JavaScript thin. Preserve existing APIs and engine history routes;
add coordinator-backed jobs without rewriting historical records.

## Job flow and recovery

Persisted stages: queued, preparing, generating_video, saving_video,
releasing_video, preparing_audio, exporting, verifying, completed. Terminal
alternatives: failed, cancelled, interrupted. Waiting for available memory is
an explicit queued reason, not fabricated generation progress.

Persist the request before submission and the external job ID immediately after
acceptance. If a crash leaves acceptance uncertain, mark interrupted; never
automatically resubmit and generate a duplicate. After restart, reconcile jobs
with their exact backend and prompt ID. Resume polling or finalization only when
identity is established; otherwise preserve inputs and ask for an explicit retry.

Cancellation affects only the owned job. Do not invoke a global worker interrupt
when foreign work may be active. Failed or cancelled stages still attempt safe
cleanup and retain diagnostic state; cleanup errors must not mask the original
failure. Completed intermediate video remains available if audio/export fails.

## Resource ownership and release

Measure free system memory, GPU availability and disk space before admission and
between stages. Record actual before/after measurements separately from requested
unloading. No fixed promise that unloading makes a 16 GB machine fit every model.
Keep at least 10 GiB disk headroom in addition to estimated job temporary/output
space; insufficient space blocks admission without deleting existing media.

First save and validate artifacts. Then request unloading on the owned idle
worker using the existing verified-connection checks. A coordinator-launched
worker may be stopped only with live process identity, executable/start-time
checks and proof no foreign jobs would be interrupted. Lost ownership after a
Nova restart does not authorize adoption or killing by PID/port alone. Report
manual intervention if custody cannot be proven. Never stop the external 8188
service, browsers, other AI tools or user processes to make memory available.

Release job ownership of the lease in a finally path, but persist a resource
quarantine when cleanup is uncertain; quarantine blocks all new heavy admission
until reconciliation proves safety. Do not start the next heavy stage until
cleanup has reached a known safe outcome and fresh resource checks pass. On
uncertain cleanup, pause the pipeline with a useful reason. Integrate existing
Nova-controlled model unload APIs only where ownership and idle state are proven.

## Video and audio behavior

Use the installed official Wan workflow and complete verified model set. Preserve
its required dimension/frame-count constraints; begin with the already tested
small preview settings rather than download a competing model. Save the exact
workflow/settings used. The masked character prompt emphasizes stable clothing,
scene and accessories, restrained performance motion and no invented mouth.

User audio is the default. Ask the UI to distinguish clean vocal from mixed
music; do not infer this from a filename. Keep optional beat separate until final
mix. Stock local TTS is a spoken preview, not rap or cloned voice. Do not launch
TTS at app startup; load only when selected, then release owned resources.

For the first supported pipeline, label the result "generated motion + audio
overlay — not audio-driven animation or verified lip-sync". Use an explicit
audio segment bounded to video duration. Never silently repeat a tiny motion
clip to suggest a longer generated performance. Expose the duration constraint.

FFmpeg export uses H.264, yuv420p and AAC when audio is supplied. Offer source
dimensions or a padded 720x1280 vertical export without stretching. Record native
generation size separately from export resizing. Use argument arrays, bounded
timeouts and server-owned output paths. Preserve an existing export on failure.

## Authorization and compatibility

Derive asset/job ownership from authenticated server context, never payload IDs.
Every submit, cancel, read and download checks ownership plus appropriate existing
scopes. Lifecycle operations require admin.models; paired-token validity alone
is insufficient. Add negative tests for paired/unprivileged callers. Do not
claim this media layer fixes legacy authorization routes or supplies OS isolation.

Keep localhost binding. Do not upload private media or include it in telemetry.
Do not reconcile or delete the two similarly named studio directories here.

## Acceptance criteria

- Regression tests prove browser-independent completion/cleanup, single-stage
  admission, duplicate-request handling, cancellation, failed finalization,
  ownership denial and safe restart reconciliation.
- Path traversal, malformed media, excessive uploads, insufficient disk/RAM and
  foreign/busy/replaced worker cases fail safely without deleting user files.
- Worker shutdown cannot remove access to a completed Nova-owned output.
- One real photo-to-motion generation finishes; sampled generated frames differ
  beyond an encoded still or export-only camera move. Inspect identity/artifacts.
- One real user-audio overlay export decodes, has expected video/audio streams,
  and has start/duration difference within one video frame plus codec padding.
  Review playback/audio when possible; explicitly document any inspection gap.
- Record real wall time, settings and measured peak GPU memory when available.
  Demonstrate the next stage starts after release, then test clean Nova restart.
- Existing chat, media history and lifecycle regression suites remain green.

## Review checklist and boundaries

Context and direction approved in chat. Written spec and implementation plan
remain separate review stages. Self-review: no placeholder behavior; ownership,
crash ambiguity, resource insufficiency and overlay labeling have explicit rules.
The next plan must preserve these boundaries and split implementation into
testable storage, coordinator, adapter and UI changes. Permission hardening,
InfiniteTalk feasibility and whole-app release acceptance remain visible in the
completion ledger and are not silently marked complete by this milestone.
