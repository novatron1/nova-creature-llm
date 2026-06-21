# Nova Self-Coding Display Workshop Design

## Goal

Let Nova improve its display and practice coding inside a confined preview sandbox while protecting the main brain, safety controls, launcher, and verified application.

## Scope

The workshop edits display projects, not Nova's protected runtime directly. Nova may create:

- panels, cards, meters, overlays, buttons, diagrams, animations, and training-world decorations;
- HTML, CSS, JavaScript, SVG, and JSON assets supported by the sandbox;
- reusable display components and small demonstrations;
- tests that describe the intended visual or interactive behavior.

The first project is **Nova Display Lab**, separate from generated games. Changes reach the main Command Center only through an explicit reviewed promotion step.

## Protected Boundaries

Self-authored code cannot modify:

- movement safety and physical adapters;
- launcher files;
- authentication, permissions, or browser security policy;
- Nova's memory database or learned-association store directly;
- server routing outside the registered display-project API;
- files outside the configured display sandbox.

The preview uses a restrictive Content Security Policy, no external network access by default, confined file paths, bounded file sizes, and a resettable execution frame. Microphone, camera, location, downloads, popups, and top-level navigation are unavailable inside the preview.

## Coding Loop

Nova follows one evidence-driven loop:

1. interpret the requested display change;
2. describe the intended behavior and visible result;
3. retrieve relevant coding lessons and previous repair evidence;
4. write or update a failing behavior test;
5. create a checkpoint;
6. make the smallest source change;
7. run static checks and browser tests;
8. inspect console errors, DOM state, and screenshots;
9. apply a bounded repair;
10. keep the candidate only after all gates pass.

Each failure becomes a coding association linking the error, source context, attempted repair, test result, and final resolution. Repeated successful associations may guide later edits, but they remain suggestions until tests pass.

## User Experience

The **Code + Preview** tab provides:

- project and file selector;
- code editor;
- live preview;
- visible test, console, and repair status;
- **Ask Nova to Change This**;
- **Save and Test**;
- **Run**;
- **Undo**;
- **Restore Working Version**;
- checkpoint history and source diff;
- **Promote to Command Center** only for a fully verified candidate.

The user can type code directly or describe a change conversationally. Small display edits may run immediately inside the sandbox. A structural rebuild or promotion to the main interface requires a clear proposal and explicit **GO**.

## Verification and Repair

Static checks reject:

- syntax errors;
- path escape attempts;
- forbidden APIs and remote resource loading;
- missing required entry files;
- excessive file size or unsupported file types.

Browser checks verify:

- the preview loads without uncaught errors;
- required elements are visible;
- controls respond;
- the frame remains confined;
- accessibility labels exist for interactive controls;
- the requested behavior appears in DOM evidence;
- screenshots remain within basic layout and overflow limits.

Nova may attempt up to three evidence-distinct repairs. Repeating the same failure without new evidence stops the loop. An unrepairable candidate is preserved for inspection while the preview restores the latest verified checkpoint.

## Learning to Code Better

Nova's coding-learning record contains:

- request and intended outcome;
- relevant files and symbols;
- initial test failure;
- diagnostics and console evidence;
- patch and diff;
- repair attempts;
- final test and browser evidence;
- lesson tags and confidence.

Lessons are retrieved by error type, language feature, component type, and intended behavior. A lesson is promoted only after it succeeds in multiple projects or independent test cases. Nova must prefer the current project's tests and documentation over a remembered repair.

## Promotion

Promotion copies a verified component manifest and approved files into a reviewable Command Center extension area. It never overwrites protected files automatically.

Promotion requires:

- all static and browser gates passing;
- a clean diff against the last promoted version;
- no forbidden permissions or APIs;
- an automatic rollback checkpoint;
- explicit user **GO** for structural changes;
- a visible record of what will change.

After promotion, the complete Command Center regression suite runs. Failure rolls back the promoted extension without deleting the sandbox draft.

## Acceptance Criteria

1. Nova and the user can edit display code and see a live confined preview.
2. Every save creates a checkpoint and runs validation.
3. Broken edits start a bounded evidence-based repair loop.
4. The last verified preview is restored when repair cannot progress.
5. Coding failures and successful repairs become inspectable learning records.
6. Retrieved coding lessons never replace current tests.
7. Sandbox code cannot access protected Nova files, devices, permissions, or external networks.
8. Promotion requires passing regressions and explicit approval for structural changes.
9. Rollback restores the previous Command Center extension after a failed promotion.
10. Nova can explain what it changed, why, and which evidence proves it works.
