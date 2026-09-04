# Nova Award-Winning Companion Shell Design

Date: 2026-07-28  
Status: Approved design  
Target: Nova Creature phone-first progressive web application

## Product decision

Nova's first impression must be:

> It feels alive, and it understands me.

The new product experience is a phone-first AI companion named **Nova
Companion**. It uses the approved **Living Cosmos** visual direction,
**Adaptive Presence** conversation layout, **Nova Spark** capability launcher,
and an evolved version of Nova's existing two-eye-and-mouth identity.

The new interface is a presentation layer around the current Nova system. It
does not replace Nova's identity, natural conversation layer, memory, cognitive
routing, models, adapters, tools, permissions, training protections, or API
contracts.

## Goals

1. Make Nova feel like one coherent living intelligence rather than a
   collection of technical panels.
2. Make ordinary conversation, voice, camera, memory, and trust understandable
   on a phone without exposing developer complexity.
3. Preserve access to every existing advanced capability.
4. Keep Nova Classic available throughout development and after release.
5. Make UI state truthful: listening, thinking, acting, responding, completed,
   failed, and cancelled must reflect real system state.
6. Meet a WCAG AA accessibility baseline and explicit mobile performance
   budgets.
7. Roll out in tested slices and make rollback a configuration change rather
   than a data migration.

## Non-goals

- Replacing or rewriting `nova_enhanced_server.py`.
- Replacing the current cognitive pipeline or `/api/chat` response contract.
- Changing Nova's personality, model weights, adapters, checkpoints, training
  system, memory ownership, or tool permissions.
- Moving intelligence or memory into the browser.
- Adding a second source of truth for models, tools, clients, permissions, or
  conversations.
- Reorganizing every existing advanced panel during the first Companion
  release.
- Removing Nova Classic.
- Adding paid or remote providers.

## Approved design language

### Living Cosmos

The visual foundation is a near-black indigo environment with restrained
violet and cyan light. It should feel cinematic, intimate, calm, and premium.
The interface must avoid excessive neon, decorative HUD noise, and continuous
motion.

The palette must be tokenized and include:

- background and elevated-surface colors;
- primary and secondary text colors;
- violet presence/accent colors;
- local/private success colors;
- warning and destructive colors;
- focus-ring colors;
- high-contrast alternatives.

Typography should use a modern system-first sans-serif stack for fast loading.
Developer diagnostics may use a monospaced stack only inside Advanced views.

### Evolved Nova identity

Nova keeps the recognizable two eyes and mouth already present in the
application. The new version gives the mark expressive but bounded behavior:

- eye openness and gaze indicate attention;
- the mouth indicates speaking and broad emotional warmth;
- color and halo indicate real system state;
- scale changes create Adaptive Presence;
- the same mark works as the app icon, loading indicator, compact chat
  presence, voice state, and future robot expression.

The mark must not imply an emotion or action Nova is not actually producing.
Reduced-motion mode replaces animation with color, icon, and text state
changes.

## Product architecture

```text
Nova Companion PWA
  -> typed browser UI service
  -> existing Nova HTTP/API boundary
  -> existing Nova Cognitive Core
  -> identity + memory + routing + tools + permissions
  -> selected local model/provider

Nova Classic
  -> existing routes and interface, preserved as fallback
```

Nova Companion is a new static shell served by the existing server. It uses
existing endpoints and response metadata. It must not duplicate Nova's
cognitive decisions in JavaScript.

### Routes and release controls

The implementation will add:

- `GET /companion`: the new Companion Shell;
- `GET /classic`: an explicit stable route to the current interface;
- a configuration flag that enables the Companion route;
- a separate configuration flag that controls whether `/` opens Companion or
  Classic.

During development:

- Companion is enabled but not the default;
- `/` continues to open Nova Classic;
- `/companion` is used for implementation and live testing.

After all release gates pass, the default flag may point `/` to Companion.
`/classic` remains available. Switching the flag back restores Classic
immediately and requires no migration.

### Browser module boundaries

The shell should use focused browser modules rather than adding another large
inline script:

- `companion-app`: lifecycle, feature detection, and top-level coordination;
- `companion-api`: fetch, streaming, cancellation, reconnection, and safe error
  normalization;
- `companion-store`: a small deterministic UI state reducer;
- `companion-presence`: Nova face and truthful visual states;
- `companion-conversation`: messages, artifacts, status summaries, and
  scrolling;
- `companion-composer`: text, voice entry, attachments, and keyboard behavior;
- `companion-spark`: registered capability presentation and navigation;
- `companion-senses`: camera, voice, OCR, and vision presentation;
- `companion-trust`: local/remote status, memory use, permissions, and recent
  safe activity;
- `companion-accessibility`: focus management, live regions, reduced motion,
  and input modality.

No new frontend framework or build tool is required for the first release.
Standards-based HTML, CSS, and ES modules are sufficient and avoid adding a
second dependency ecosystem.

## Core experience

### 1. Arrival

The opening view is Nova, not a dashboard.

It contains:

- Evolved Nova in its full presence state;
- a personal greeting when the server supplies safe identity context;
- one concise continuity cue, such as the active project or last unresolved
  topic;
- a composer;
- a visible local/private status that can open the Trust view;
- the Nova Spark.

The UI must not fabricate a name, memory, relationship, or open task. If the
server provides no continuity context, the greeting remains warm and generic.

### 2. Adaptive Presence

Nova begins large and cinematic. As the user and Nova exchange messages, the
presence contracts into a compact identity near the conversation header. It
may expand again when:

- the conversation is cleared;
- the user explicitly returns home;
- voice-only mode begins;
- a meaningful state transition benefits from a larger presence.

The composer and latest message must not jump when the presence changes size.
The transition is layout-safe and has a nonanimated reduced-motion equivalent.

### 3. Conversation

The conversation surface prioritizes readable messages and relationship
continuity.

It supports:

- streaming without duplicated text;
- user, Nova, tool, artifact, and safe system-message presentation;
- stable request status;
- stop and retry;
- local draft preservation during reconnects;
- concise privacy-safe status chips;
- expandable technical detail rather than always-visible routing traces;
- anchored composer behavior with the mobile keyboard;
- explicit correction and Teach Better actions.

The natural response remains the output of Nova's existing server pipeline.
The browser does not rewrite or repair model answers.

### 4. Nova Spark

Nova Spark is the primary capability launcher. It is available through:

- tap;
- long press;
- keyboard activation;
- an accessible named button;
- supported voice phrases.

The first uses include a short, dismissible discovery hint. A persistent
accessible label and optional text caption prevent the control from becoming a
hidden mystery gesture.

Spark actions are contextual but must come from registered server capabilities
or a maintained UI navigation registry. The model cannot invent UI actions.

Initial groups are:

- See: camera, picture, OCR, and vision;
- Speak: microphone, voice mode, and voice selection;
- Create: Dream Studio, image, video, music, app, and game entry points;
- Remember: relevant memory, memory controls, and conversation continuity;
- Work: projects, files, research, agents, and tools;
- System: models, adapters, health, tests, logs, settings, and Nova Classic.

Capabilities not yet migrated open the existing working panel or Classic route
with a clear return path. This preserves power without delaying the Companion
launch.

### 5. Live Senses

Camera and voice are temporary, explicit modes rather than small permanent
buttons.

Each mode shows:

- whether the browser permission exists;
- whether capture is actually active;
- whether the local engine is available;
- whether content is being persisted;
- whether processing stays local;
- how to stop immediately.

Camera, OCR, or vision output is shown only after the corresponding engine or
deterministic inspection returns. Nova must never appear to see or hear based
only on a button press.

### 6. Trust

Trust is a first-class product surface, not a log page. It summarizes:

- local versus remote execution;
- current model/provider;
- memory used in the current exchange;
- whether the camera and microphone are active;
- whether image persistence is enabled;
- pending permissions or confirmations;
- recent tools and their completed/failed/cancelled result;
- estimated or actual remote cost when applicable.

It shows safe metadata only. It must not display API keys, hidden reasoning,
private memory content, authorization headers, raw prompts, or sensitive file
content.

## UI state model

The browser reducer owns presentation state only. At minimum it distinguishes:

- `booting`;
- `present`;
- `listening`;
- `submitting`;
- `thinking`;
- `acting`;
- `responding`;
- `completed`;
- `offline`;
- `failed`;
- `cancelled`.

`acting` also carries the safe tool name and authorization state. `responding`
begins only when actual content or speech output starts. `completed` requires
an observed successful response, not merely an attempted request.

The reducer must reject impossible or stale transitions, such as a late
response from a cancelled request overwriting a newer conversation turn.

## Data flow

### Chat turn

1. The composer creates one client request identifier.
2. The message is rendered as pending and the draft is retained until the
   server accepts it.
3. `companion-api` submits to the existing Nova route.
4. Server metadata updates truthful presence and safe status UI.
5. Streaming deltas append once to the matching response identifier.
6. Tool or permission states are displayed without claiming completion.
7. The final response replaces the pending state.
8. The server remains responsible for memory and continuity updates.
9. The browser stores only minimal UI preferences and recoverable drafts.

### Reconnection

1. The UI enters `offline` without deleting the draft or visible thread.
2. A bounded reconnect policy checks server health.
3. An accepted request is not resent automatically when acceptance is
   uncertain.
4. The user receives a clear Retry option tied to the original request.
5. Response identifiers prevent duplicates after reconnection.

### Capability launch

1. The user opens Nova Spark.
2. The UI reads known availability and permission state.
3. Selecting a capability either opens a native Companion sheet or a preserved
   working Classic panel.
4. Risky operations continue through the existing permission and confirmation
   system.
5. Spark closes only after a destination or request is accepted.

## Error and recovery design

### Slow local model

The UI retains partial output, shows the active local model when safe, and
offers Stop or Continue Waiting. It does not replace a slow answer with a
generic success or recovery message.

### Interrupted connection

The current draft and thread remain stable. Reconnect and resend are separate
actions to prevent duplicate model calls.

### Camera or voice failure

The UI identifies whether the failure is:

- browser permission denied;
- capture device unavailable;
- local engine unavailable;
- processing timeout;
- unsupported browser behavior.

Text chat remains usable in every case.

### Model uncertainty

The UI preserves Nova's honest limitation and server-provided escalation
options. It may offer a larger healthy local model or authorized source check.
It must not turn ordinary emotional conversation into a factual-sourcing
error.

### Tool failure

Proposed, authorized, attempted, observed, verified, failed, and cancelled are
distinct states. A tool card displays the observed result and safe recovery
action.

## Accessibility

The release baseline is WCAG AA for the new shell.

Requirements include:

- at least 44 by 44 CSS pixel primary touch targets;
- visible keyboard focus;
- semantic button, dialog, navigation, status, and message roles;
- live regions that do not read partial streaming content excessively;
- reduced-motion support;
- no information communicated by color alone;
- high-contrast text and state labels;
- safe behavior at 200 percent text zoom;
- keyboard access to Nova Spark and every sheet;
- focus restoration when sheets close;
- captions or text equivalents for voice states;
- no forced orientation.

## Performance budgets

Targets for a normal supported phone are:

- Companion shell interactive in under 1.5 seconds on a warm local-network
  load, excluding model generation;
- no horizontal body overflow at supported phone widths;
- no cumulative layout shift from message status or Adaptive Presence;
- 60 frames per second for presence motion on capable devices;
- reduced visual effects on low-power or reduced-motion devices;
- no image, camera frame, model file, or conversation response in the service
  worker cache;
- bounded message DOM through safe conversation-window virtualization or
  compaction when necessary.

These are release targets, not claims, until measured in live tests.

## Build and rollout

### Phase 1: Shell foundation

- Add the Companion and Classic routes.
- Add enable/default feature flags.
- Create design tokens, safe-area layout, API service, reducer, and offline
  shell.
- Prove the new route can fail without affecting Classic.

Gate: both routes load independently and all existing tests remain green.

### Phase 2: Presence and chat

- Implement Evolved Nova and Adaptive Presence.
- Implement conversation, composer, streaming, cancellation, draft recovery,
  and reconnect behavior.
- Add reduced-motion behavior.

Gate: a 25-turn live relationship and continuity test passes without duplicate
messages, broken scrolling, irrelevant safety fallbacks, or lost drafts.

### Phase 3: Nova Spark

- Implement accessible Spark activation and discovery.
- Add capability groups and availability state.
- Link nonmigrated capabilities to working Classic panels.

Gate: every displayed action resolves to a real capability, unavailable state,
or honest explanation.

### Phase 4: Senses and Trust

- Implement camera, voice, OCR/vision status, local/remote indicators, memory
  usage, and safe activity.
- Verify persistence and permission language against real server behavior.

Gate: live phone tests prove sensor truth, privacy state, and error recovery.

### Phase 5: Polish and default

- Tune animation, responsive desktop behavior, accessibility, and performance.
- Run visual, integration, and full regression testing.
- Audit secrets, logging, service-worker caching, and remote behavior.

Gate: all acceptance criteria pass before Companion becomes the default.

## Test strategy

### Unit tests

- UI reducer state transitions and stale-response rejection;
- API error normalization and cancellation;
- streaming reconstruction without duplication;
- capability filtering and unavailable states;
- privacy-safe status formatting;
- reduced-motion and preference behavior.

### Integration tests

- existing chat contract through Companion;
- memory and continuity metadata presentation;
- reconnect and retry without double submission;
- Spark navigation;
- camera and voice permission outcomes;
- Classic deep links and return navigation;
- service-worker cache exclusions.

### Browser and visual tests

Required phone viewports include 390 by 844 and 430 by 932 CSS pixels. Desktop
coverage begins at 1024 CSS pixels.

Tests cover:

- keyboard-open composer layout;
- bottom safe-area behavior;
- long conversations;
- 200 percent text zoom;
- reduced motion;
- screen-reader names and focus order;
- no horizontal body overflow;
- Adaptive Presence transitions;
- Spark, sheets, and return navigation.

### Live acceptance tests

- 25-turn relationship, memory, follow-up, interruption, and reconnect
  conversation;
- 10 capability journeys across voice, camera, image, memory, creation, tools,
  models, privacy, settings, and Classic;
- current-fact and uncertainty behavior;
- real local small-model response and one allowed escalation;
- raw adapter controls remain unintercepted;
- camera/vision reports no false result;
- Stop cancels the active request without poisoning the next turn.

### Regression gate

The existing baseline at design time is:

- 1,323 passed;
- 10 skipped;
- 0 failed.

No existing test may be deleted, weakened, or skipped to release Companion.
New Companion tests must pass in addition to that baseline.

## Release acceptance criteria

Companion may become the default only when:

1. Nova Classic remains directly accessible.
2. Existing server, identity, memory, routing, model, adapter, training, and
   tool behavior is unchanged.
3. All existing tests and new Companion tests pass.
4. The 25-turn relationship test and 10 capability journeys pass.
5. Streaming reconstructs exactly once.
6. Reconnect does not duplicate requests or messages.
7. Camera, voice, tool, and model states remain truthful.
8. No prompt, key, memory content, image, or hidden reasoning is logged or
   cached by the new shell.
9. The two required phone viewports have no body overflow or unreachable
   controls.
10. The accessibility baseline passes.
11. Performance targets are measured and documented.
12. Switching the default flag back to Classic is verified.

## Rollback

Rollback sets the default-experience configuration to Classic and restarts or
reloads the existing server as required by its current configuration behavior.
No database, memory, model, adapter, or conversation migration is needed.
Companion remains available at its direct route for diagnosis unless the
enable flag is also disabled.

## Award-level differentiators

The design is intended to stand apart through:

- a recognizable living identity that already belongs to Nova;
- adaptive presence rather than a static chatbot header;
- the Nova Spark as a characterful, contextual capability interface;
- relationship continuity surfaced without exposing private memory;
- truthful system animation tied to real cognitive and tool state;
- first-class local privacy and trust;
- deep capability without a crowded first screen;
- graceful coexistence with the proven Nova Classic system.

