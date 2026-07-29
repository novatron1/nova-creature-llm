import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const source = (path) => new URL(path, import.meta.url);
const importModule = async (path) => {
  const code = await readFile(source(path), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
};

const store = await importModule("../../assets/nova_companion/companion-store.js");
const presence = await importModule("../../assets/nova_companion/companion-presence.js");

const {
  COMPANION_EVENTS,
  COMPANION_PHASES,
  createInitialCompanionState,
  reduceCompanionState,
} = store;
const { presenceViewModel, renderPresence } = presence;

test("cancelled requests ignore late deltas", () => {
  const initial = createInitialCompanionState({ clientId: "phone", conversationId: "conv-1" });
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "req-1", text: "Hello" });
  const cancelled = reduceCompanionState(submitted, { type: "CANCELLED", requestId: "req-1" });
  const late = reduceCompanionState(cancelled, { type: "DELTA", requestId: "req-1", delta: "late" });
  assert.equal(late.phase, "cancelled");
  assert.equal(late.streamingText, "");
});

test("a tool is acting only after an observed tool-start event", () => {
  const state = createInitialCompanionState({});
  const proposed = reduceCompanionState(state, { type: "TOOL_PROPOSED", requestId: "r", toolName: "vision.observe" });
  assert.notEqual(proposed.phase, "acting");
  const acting = reduceCompanionState(proposed, { type: "TOOL_STARTED", requestId: "r", toolName: "vision.observe" });
  assert.equal(acting.phase, "acting");
});

test("presence labels match real phases", () => {
  const thinking = presenceViewModel({ phase: "thinking", conversationTurnCount: 2 }, false);
  assert.equal(thinking.label, "Nova is thinking");
  assert.equal(thinking.size, "compact");
  assert.equal(thinking.motion, "thinking");
});

test("initial state has the documented immutable shape", () => {
  const state = createInitialCompanionState({ clientId: "desktop", conversationId: "conv-2" });
  assert.deepEqual(state, {
    phase: "booting", clientId: "desktop", conversationId: "conv-2", activeRequestId: "",
    acceptedRequestIds: [], conversationTurnCount: 0, streamingText: "", activeTool: null,
    error: null, offline: false, sheet: null,
    camera: { permission: "unknown", active: false, persisted: false },
    microphone: { permission: "unknown", active: false },
    trust: { local: null, provider: "", model: "", memoryUsed: false },
  });
  assert.ok(Object.isFrozen(state));
  assert.ok(COMPANION_PHASES.has("responding"));
  assert.ok(COMPANION_EVENTS.has("SUBMIT"));
});

test("reducer returns a new state and ignores stale request-bound events", () => {
  const initial = createInitialCompanionState({});
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "current", text: "Hi" });
  const stale = reduceCompanionState(submitted, { type: "DELTA", requestId: "old", delta: "ignored" });
  assert.notEqual(submitted, initial);
  assert.equal(stale, submitted);
  assert.equal(submitted.streamingText, "");
});

test("accepted request ids are unique and bounded to the latest twenty", () => {
  let state = createInitialCompanionState({});
  for (let index = 0; index < 22; index += 1) {
    state = reduceCompanionState(state, { type: "SUBMIT", requestId: `r-${index}`, text: "Hi" });
  }
  assert.equal(state.acceptedRequestIds.length, 20);
  assert.deepEqual(state.acceptedRequestIds.slice(0, 2), ["r-2", "r-3"]);
});

test("identity changes clear private transient state", () => {
  const initial = createInitialCompanionState({ clientId: "phone", conversationId: "one" });
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "r", text: "Hi" });
  const changed = reduceCompanionState(submitted, { type: "IDENTITY_CHANGED", clientId: "desktop", conversationId: "two" });
  assert.equal(changed.clientId, "desktop");
  assert.equal(changed.conversationId, "two");
  assert.equal(changed.activeRequestId, "");
  assert.deepEqual(changed.acceptedRequestIds, []);
  assert.equal(changed.streamingText, "");
  assert.equal(changed.activeTool, null);
  assert.equal(changed.trust.memoryUsed, false);
  assert.equal(changed.camera.active, false);
  assert.equal(changed.microphone.active, false);
});

test("a cancelled request cannot be reactivated by a late tool proposal", () => {
  const initial = createInitialCompanionState({});
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "r", text: "Hi" });
  const cancelled = reduceCompanionState(submitted, { type: "CANCELLED", requestId: "r" });
  const late = reduceCompanionState(cancelled, { type: "TOOL_PROPOSED", requestId: "r", toolName: "vision.observe" });
  assert.equal(late, cancelled);
});

test("presence rendering uses text content and state attributes", () => {
  const elements = {
    presence: { dataset: {}, setAttribute(name, value) { this[name] = value; } },
    face: { dataset: {} },
    greeting: {},
  };
  const viewModel = presenceViewModel({ phase: "responding", conversationTurnCount: 1 }, true);
  renderPresence(elements, viewModel);
  assert.equal(viewModel.motion, "none");
  assert.equal(elements.presence.dataset.phase, "responding");
  assert.equal(elements.presence.dataset.presenceSize, "compact");
  assert.equal(elements.presence["aria-busy"], "true");
  assert.equal(elements.greeting.textContent, "Nova is responding");
});
