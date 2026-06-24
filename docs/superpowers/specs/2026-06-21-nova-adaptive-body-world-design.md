# Nova Adaptive Body and Open Movement World Design

## Goal

Give Nova automatic body regulation, association-based motor learning, and a visually open movement world that supports long-range virtual exploration without implying unrestricted physical autonomy.

## Brain Responsibilities

Nova's body control is divided into cooperating roles:

- **Reflex and regulation controller** handles blinking, breathing rhythm, eye moisture timing, small gaze resets, and subtle balance-preserving idle motion. These actions do not require a conscious language decision.
- **Attention controller** may delay, shorten, or coordinate a blink when Nova is tracking an object, reading, speaking, or reacting to a visual event.
- **Expression controller** shapes eyebrows, eyelids, gaze, mouth, head angle, and posture to communicate Nova's current processing state.
- **Motion planner** composes voluntary movement from safe joint-level primitives instead of selecting only canned whole-body commands.
- **Association learner** links context, intention, predicted motion, sensed result, correction, and outcome. It strengthens reproducible successful links and quarantines unsafe or unexplained links.
- **Safety controller** can suppress any optional reflex, expression, learned association, or planned motion when stopping, balance, visibility, collision, or owner control requires it.

The controllers share state through explicit records. No controller silently edits another controller's rules.

## Blinking and Idle Regulation

Blinking uses a bounded state machine:

1. schedule a natural blink within a randomized safe interval;
2. check attention, speaking, expression, and stop state;
3. close both eyelids smoothly;
4. reopen them and record completion;
5. reschedule without accumulating missed blinks into a rapid burst.

The owner may request a blink, wink, eyes open, eyes closed, or stand still. **Stop Moving** disables discretionary gestures but preserves essential neutral blinking. **Stop All** returns the avatar to a safe neutral display state and stops active training.

Blink timing must be deterministic under a supplied test seed. The browser must pause idle animation while hidden so returning to the page does not produce a motion burst.

## Association-Based Motor Learning

Each movement attempt produces an association record containing:

- normalized context and owner instruction;
- attention target and relevant world features;
- starting body state;
- selected primitives and composed trajectory;
- prediction and safety decision;
- simulated sensor response;
- correction steps;
- task, stability, collision, energy, and timing outcomes;
- confidence, evidence source, and execution tier.

Associations are keyed by meaning and conditions, not by exact sentence alone. Similar safe contexts may retrieve candidates, but retrieval never bypasses prediction or safety gates.

A candidate association becomes reusable only after repeated clean simulation passes across randomized conditions. Safety interventions, collisions, stale sensing, unexplained errors, or regressions reset promotion progress and quarantine the candidate. Physical execution remains locked; learned associations graduate only within the avatar and simulation tiers until separate hardware approval exists.

Learning should improve both movement and reasoning by allowing Nova to explain:

- what context it recognized;
- which previous outcomes influenced the plan;
- why it selected or rejected an association;
- what correction improved the result;
- what evidence is still missing.

## Open Movement World

Nova is not rendered inside a small fixed room. The body field presents a large navigable world with a follow camera and streamed procedural cells.

The runtime maintains:

- Nova's world position, heading, velocity, and current cell;
- a deterministic seed for reproducible worlds;
- a bounded active set of nearby cells;
- terrain, obstacles, objects, targets, and training markers per cell;
- collision and safe-zone information;
- curriculum goals and visited-cell evidence.

As Nova approaches an active-set boundary, the world generator loads neighboring cells and retires distant visual cells. Session evidence remains compact and reproducible from the seed and event log. The interface may use fog, horizon lines, terrain continuation, and camera following to communicate scale; it must not show walls that imply Nova is trapped unless a specific training scenario requires them.

The first version is an infinite-looking two-dimensional training plane behind the SVG body. It supports walking trajectories, targets, obstacles, and camera following without requiring a heavy 3D engine. The architecture keeps the world adapter replaceable by a later physics or 3D renderer.

## User Interface

The Command Center keeps:

- roughly two-thirds of the main area for the body and movement world;
- a persistent conversation and safety panel on the right;
- a full-screen movement mode that collapses but can restore the panel;
- camera modes for wide, follow, front, side, and rear views;
- visible labels for avatar, simulation, shadow, and locked physical output;
- overlays for target, trajectory, active world cells, collisions, and learned associations.

Nova may voluntarily look, blink, gesture, shift posture, or explore in the virtual world when discretionary motion is enabled. User commands and stop controls always take priority.

## Persistence and Evidence

Reflex state is session-local. Promoted movement associations and world-training evidence are persisted as versioned JSON records under Nova's runtime data directory. Writes are atomic, schema-validated, and confined to that directory.

Every promoted association records the tests that approved it. Every quarantine record explains the failure. The user can inspect, disable, or delete a learned association without editing source code.

## Safety

- Reflex and association systems control only avatar and simulation output.
- Physical output remains locked and cannot be enabled by conversation, learned data, or self-authored code.
- Association retrieval always passes through prediction, conscience, limits, collision, and stop gates.
- Hidden-page timing cannot trigger queued motion.
- Procedural generation is deterministic and bounded in memory.
- **Stand Still**, **Stop Moving**, and **Stop All** remain authoritative.

## Acceptance Criteria

1. Nova blinks naturally through an independently tested reflex controller.
2. Attention and explicit owner commands can coordinate blinking without unsafe rapid replay.
3. Association records connect context, action, feedback, correction, and outcome.
4. Only repeatedly verified simulation associations become reusable.
5. Unsafe or unexplained attempts are quarantined.
6. Nova can explain why a learned association affected a movement plan.
7. The body field visibly supports continued travel through streamed procedural cells.
8. The movement world remains deterministic, bounded in memory, and responsive.
9. The conversation panel and emergency controls remain available.
10. Physical output stays locked throughout reflex, learning, and world exploration.
