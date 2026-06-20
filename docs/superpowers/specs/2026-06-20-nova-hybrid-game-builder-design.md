# Nova Hybrid Game Builder Design

**Date:** June 20, 2026  
**Status:** Approved design  
**Default target:** Playable 2D browser games  

## Purpose

Nova must recognize game-building requests as creation tasks instead of answering with loosely related memory. It will research the user's idea, improve it, present an editable plan, wait for the explicit command `GO`, build a playable game, test it in a real browser, repair failures, save the project, show its source, and provide an Open Game link.

The first release prioritizes reliable browser games that run locally without a paid service. It uses modular, tested game systems and may use optional external AI providers later, but core operation must not require an API key.

## User Experience

### New game flow

1. The user describes a game idea in ordinary language.
2. Nova identifies the request before dictionary or fuzzy-memory lookup.
3. Nova researches relevant mechanics, accessibility patterns, implementation techniques, and comparable genres using public internet sources and local knowledge.
4. Nova produces an enhanced proposal containing:
   - interpreted concept and player fantasy;
   - core gameplay loop;
   - controls;
   - progression and scoring;
   - visual and audio direction;
   - accessibility and mobile considerations;
   - planned files and technical approach;
   - research sources and what was learned from each;
   - optional features separated from the recommended first build.
5. Nova enters `WAITING_FOR_GO`. It must not create the game before approval.
6. The user may say `GO`, add features, remove features, revise the concept, or cancel.
7. After `GO`, Nova builds, launches, playtests, diagnoses, repairs, and repeats until the required gates pass.
8. Nova returns:
   - an **Open Game** link;
   - the saved project location;
   - a source-code view in chat;
   - a concise test and repair report;
   - modification instructions.

### Modification flow

- Small changes, such as colors, speed, jump height, text, controls, obstacle frequency, or a sound toggle, are applied immediately and sent through the full test loop.
- Major changes, such as a new genre, multiplayer, a new level system, a different rendering engine, persistent accounts, or a structural redesign, produce an impact plan and return to `WAITING_FOR_GO`.
- The user may explicitly request planning for any change, even if Nova classifies it as small.

## Conversation Commands

- `GO` — approve the current plan and begin building.
- `CHANGE ...` / `ADD ...` / `REMOVE ...` — revise the pending plan.
- `CANCEL` — abandon the pending build without creating files.
- `OPEN GAME` — reopen the most recent successful build.
- `SHOW CODE` — show the generated source files in chat.
- `MOD ...` — modify the active project using the small/major change policy.
- `GAME STATUS` — show the active state, last test result, project path, and blocker if any.

`GO` applies only to the most recent pending plan in the current game-builder session. A stale or ambiguous `GO` must not build an unrelated project.

## State Model

```text
IDLE
  -> RESEARCHING
  -> PLAN_READY
  -> WAITING_FOR_GO
  -> BUILDING
  -> TESTING
  -> REPAIRING -> TESTING
  -> READY

Any active state -> CANCELLED
RESEARCHING / BUILDING / TESTING / REPAIRING -> BLOCKED
READY + major modification -> WAITING_FOR_GO
READY + small modification -> BUILDING
```

State is persisted as JSON so restarting Nova does not silently lose a pending plan or active project.

## Architecture

### 1. Game intent router

A focused intent detector runs before dictionary lookup and fuzzy memory search. It recognizes direct and conversational creation phrases such as:

- “make me a block jumping runner”;
- “build a game”;
- “can you turn this idea into a game?”;
- “add double jump to my game”;
- “show the game code.”

It distinguishes:

- capability questions: “Can you make games?”;
- creation requests: “Make me a runner”;
- approval commands: `GO`;
- project commands: open, show code, status, cancel;
- modifications to the active project.

This ordering fixes the current failure in which generic memory matches capture game-building requests before the coding handler can act.

### 2. Game builder orchestrator

The orchestrator owns the state machine and coordinates research, planning, approval, generation, tests, repairs, and chat responses. Each stage returns structured data rather than free-form text so progress can be resumed and audited.

### 3. Research service

Research is provider-based so one unavailable website does not stop the workflow.

Built-in providers:

- authenticated GitHub search through the installed `gh` session when available, with public REST fallback;
- MediaWiki search for concepts, terminology, and background;
- direct official-document retrieval for browser APIs and deployment requirements;
- best-effort public web search for broader inspiration;
- Nova's local game-builder knowledge, prior approved projects, and test history.

Every research result stores its title, URL, provider, retrieval time, short summary, and the concrete design signal extracted from it. Nova must distinguish sourced facts from its own design inference. It must not copy another game's code, branding, characters, art, music, level layouts, or protected identity. Research informs patterns and improvements; it does not produce clones.

If general search is unavailable, Nova continues with reachable public sources and local knowledge, clearly reporting the reduced research coverage before requesting `GO`.

### 4. Concept enhancer

The enhancer converts the raw idea and research signals into a buildable proposal. It favors a small polished game over an oversized incomplete one.

The initial browser-game catalog supports:

- endless runner and platformer;
- top-down collector or arena dodger;
- simple puzzle and clicker games.

Unsupported ideas are mapped to the nearest reliable browser format, and the mapping is disclosed in the proposal. The user can revise it before `GO`.

### 5. Approval gate

The gate stores the proposal hash and displays `WAITING FOR GO`. No project source files are written before approval. Research and plan metadata may be stored in Nova's session data so the proposal survives a restart.

Changing the proposal invalidates the previous approval and creates a new proposal hash. Nova must wait for a new `GO`.

### 6. Project generator

Each approved game is saved under:

```text
sandbox/game_builder_projects/<project-slug>/
```

Expected files:

```text
index.html
styles.css
game.js
game.config.json
README.md
manifest.json
research.json
plan.json
test-report.json
repair-log.jsonl
```

Games use HTML, CSS, JavaScript, Canvas, and `requestAnimationFrame` by default. The generator composes tested modules for input, physics, collision, scoring, game states, restart behavior, responsive sizing, touch controls, and deterministic testing. Game-specific values live in `game.config.json` wherever practical so common modifications do not require rewriting engine code.

The Nova web server exposes a confined read-only game route:

```text
http://127.0.0.1:3000/games/<project-slug>/
```

Path traversal and access outside the game-project sandbox are rejected.

### 7. Source presentation

After a successful build, chat shows:

- the primary source in a collapsible code section;
- a file list with individual source views;
- the Open Game link;
- the project folder;
- the build and test summary.

For larger projects, Nova shows the main file first and supports `SHOW CODE <filename>` or `SHOW ALL CODE` to avoid an unreadable single response.

## Play-Until-Passing Debug Loop

The success loop is:

```text
Generate -> Launch -> Playtest -> Diagnose -> Repair -> Repeat
```

Nova may not report success merely because files were created or JavaScript parsed.

### Static gates

- required files exist;
- JSON files parse;
- JavaScript syntax passes;
- asset paths resolve;
- source remains inside the approved project;
- generated configuration values are within safe ranges.

### Real browser gates

Browser automation launches the game and checks:

- the page and game surface render;
- no uncaught page or console errors occur;
- keyboard controls affect the player;
- touch controls exist on touch-capable layouts;
- jumping produces visible upward and downward movement for platform games;
- collision changes the expected game state;
- score or progress can increase;
- game-over or completion can be reached;
- restart returns the game to a playable initial state;
- the game remains responsive during a deterministic smoke run.

Generated games expose a small test-only telemetry interface when opened with a test flag. It reports state such as player position, velocity, score, game mode, collisions, and restart count. The normal game does not show this interface to players.

### Diagnosis and repair

Failures are classified into syntax, missing asset, load, input, physics, collision, state-machine, scoring, responsive-layout, or runtime categories. The repair engine first uses deterministic fixes and safe regeneration from known-good modules. An optional configured AI coding provider may propose a patch, but its patch must pass the same tests and sandbox restrictions.

Each attempt appends:

- observed failure;
- evidence;
- selected repair;
- changed files;
- post-repair test result.

Nova continues while tests are failing and new repair progress is possible. To prevent an infinite blind loop, it enters `BLOCKED` only when:

- an external requirement is unavailable, such as internet, permission, hardware, or a required paid service; or
- the same failure persists for three evidence-equivalent repair cycles with no measurable progress.

`BLOCKED` is not presented as success. Nova explains the exact blocker, preserves the project and logs, and proposes the smallest user action needed to continue.

## Research and Technical Basis

The design uses browser-native technology because Canvas supports game graphics and animation, and `requestAnimationFrame` is broadly available for browser animation:

- MDN Canvas API: https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API
- MDN `requestAnimationFrame`: https://developer.mozilla.org/en-US/docs/Web/API/Window/requestAnimationFrame

HTML, CSS, and JavaScript also produce portable games that can later be packaged for browser-game hosting:

- itch.io HTML5 game guidance: https://itch.io/docs/creators/html5

The research layer uses documented public APIs where possible:

- GitHub REST API: https://docs.github.com/rest
- MediaWiki OpenSearch API: https://www.mediawiki.org/wiki/API:Opensearch

## Safety and Boundaries

- Internet research is read-only.
- Building and repairs write only inside the selected game project.
- Nova does not publish, purchase, upload, send messages, or use private credentials without a separate explicit request.
- Remote code found during research is never executed automatically.
- Downloaded scripts and binary assets are not imported automatically.
- External assets require a compatible license and recorded attribution; otherwise Nova creates original procedural shapes and effects.
- Generated games do not receive filesystem, shell, camera, microphone, or network access unless the user explicitly requests and approves that capability.
- Existing projects are backed up or versioned before structural modifications.

## Error Handling

- Research-provider failures are isolated and recorded.
- Invalid or ambiguous `GO` commands return a clear request to select the pending plan.
- Build failures preserve logs and enter the repair loop.
- Server restart restores pending and active project state.
- Port conflicts use an available local port while preserving a stable Open Game route when possible.
- Missing browser automation support triggers a one-time local setup attempt. If installation is impossible, Nova reports that real-browser verification is blocked and does not claim the game passed.

## Testing Strategy

### Unit tests

- game requests outrank fuzzy memory matches;
- capability questions do not accidentally start builds;
- `GO` requires a pending plan;
- proposal edits invalidate prior approval;
- research results retain source attribution;
- small and major modifications classify correctly;
- project paths cannot escape the sandbox;
- generated config remains valid;
- repair categories map to permitted repair actions.

### Integration tests

- idea -> research -> proposal -> wait for `GO`;
- no source project exists before `GO`;
- `GO` -> generated project -> served Open Game route;
- `SHOW CODE` returns actual generated files;
- small modification rebuilds immediately;
- major modification waits for a new `GO`;
- restart restores pending and ready project state;
- blocked research still produces an honestly labeled local-knowledge proposal.

### End-to-end browser tests

For the block-jumping runner reference case:

- game loads without console errors;
- left/right or runner movement works as designed;
- jump clears a reachable obstacle;
- collision can trigger loss;
- score increases during survival;
- restart resets score and player state;
- touch controls work in a mobile viewport;
- a deterministic smoke run completes without freezing.

The repair-loop test intentionally generates one known defect, verifies that the browser test fails, confirms the repair is applied, and verifies that the same test then passes.

## Acceptance Criteria

The feature is complete when:

1. “Make me a block jumping game runner” enters game-builder research instead of memory recall.
2. Nova shows an enhanced, sourced proposal and waits for `GO`.
3. No game source is generated before `GO`.
4. After `GO`, Nova saves and serves a playable browser game.
5. Nova performs real-browser gameplay checks and automatically repairs a seeded failure.
6. Nova does not announce success until all required gates pass.
7. Chat provides an Open Game link, source access, project location, and test report.
8. Small modifications apply and retest immediately.
9. Major modifications return to the approval gate.
10. External or stagnant blockers are reported honestly with preserved evidence.

## Out of Scope for the First Release

- automatic public deployment;
- online multiplayer servers;
- account systems, payments, or cloud databases;
- native Windows executables;
- Roblox, Unity, Unreal, or console exports;
- automatic use of copyrighted commercial assets;
- unrestricted execution of code found on the internet.

These may be added later as separate approved capabilities without weakening the browser-game workflow or safety boundaries.
