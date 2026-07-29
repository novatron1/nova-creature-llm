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
const conversation = await importModule("../../assets/nova_companion/companion-conversation.js");
const composer = await importModule("../../assets/nova_companion/companion-composer.js");

const {
  COMPANION_EVENTS,
  COMPANION_PHASES,
  createInitialCompanionState,
  reduceCompanionState,
} = store;
const { presenceViewModel, renderPresence } = presence;
const { appendMessage, beginStreamingMessage, appendStreamingDelta } = conversation;
const { createComposerController } = composer;

class FakeNode {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.style = {};
    this.listeners = new Map();
    this._textContent = "";
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); return node; }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  addEventListener(type, listener) { this.listeners.set(type, listener); }
  removeEventListener(type) { this.listeners.delete(type); }
  focus() { this.focused = true; }
  get textContent() { return this.children.length ? this.children.map((child) => child.textContent).join("") : this._textContent; }
  set textContent(value) { this._textContent = String(value); this.children = []; }
  querySelector(selector) {
    const match = selector.match(/^\[data-([^\]]+)\]$/);
    if (!match) return null;
    const key = match[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
    for (const child of this.children) {
      if (child.dataset?.[key] !== undefined) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
}

class FakeDocument {
  createElement(tagName) { return new FakeNode(tagName); }
  createTextNode(text) { const node = new FakeNode("#text"); node.textContent = text; return node; }
}

test("cancelled requests ignore late deltas", () => {
  const initial = createInitialCompanionState({ clientId: "phone", conversationId: "conv-1" });
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "req-1", text: "Hello" });
  const cancelled = reduceCompanionState(submitted, { type: "CANCELLED", requestId: "req-1" });
  const late = reduceCompanionState(cancelled, { type: "DELTA", requestId: "req-1", delta: "late" });
  assert.equal(late.phase, "cancelled");
  assert.equal(late.streamingText, "");
});

test("a tool is acting only after an observed tool-start event", () => {
  const state = reduceCompanionState(createInitialCompanionState({}), {
    type: "SUBMIT", requestId: "r", text: "Observe this",
  });
  const proposed = reduceCompanionState(state, {
    type: "TOOL_PROPOSED", requestId: "r", toolName: "vision.observe",
  });
  assert.notEqual(proposed.phase, "acting");
  assert.equal(proposed.activeTool.status, "proposed");
  assert.ok(Object.isFrozen(proposed.activeTool));
  const acting = reduceCompanionState(proposed, { type: "TOOL_STARTED", requestId: "r", toolName: "vision.observe" });
  assert.equal(acting.phase, "acting");
});

test("presence labels match real phases", () => {
  const thinking = presenceViewModel({ phase: "thinking", conversationTurnCount: 2 }, false);
  assert.equal(thinking.label, "Nova is thinking");
  assert.equal(thinking.size, "compact");
  assert.equal(thinking.motion, "thinking");
});

test("adaptive presence remains full until Nova completes the first turn", () => {
  const initial = createInitialCompanionState({});
  assert.equal(presenceViewModel(initial, false).size, "full");
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "r", text: "Hello" });
  const completed = reduceCompanionState(submitted, { type: "COMPLETED", requestId: "r" });
  assert.equal(presenceViewModel(completed, false).size, "compact");
});

test("presence only presents listening or speaking when that modality is currently active", () => {
  assert.equal(presenceViewModel({ phase: "completed", voice: { listening: false, speaking: true } }).label, "Nova is speaking");
  assert.equal(presenceViewModel({ phase: "completed", voice: { listening: false, speaking: false } }).label, "Nova is here");
});

test("conversation rendering keeps model markup inert while linking only safe URLs", () => {
  const document = new FakeDocument();
  const timeline = new FakeNode();
  timeline.ownerDocument = document;
  const message = appendMessage(timeline, {
    id: "msg-1", role: "assistant", text: "<b>safe</b> https://nova.local/help ftp://unsafe.example", status: "completed",
  });
  const body = message.querySelector("[data-message-text]");
  assert.equal(body.children.some((node) => node.tagName === "A" && node.href === "https://nova.local/help"), true);
  assert.equal(body.children.some((node) => node.tagName === "A" && String(node.href).startsWith("ftp:")), false);
  assert.equal(body.children.some((node) => node.textContent.includes("<b>safe</b>")), true);
});

test("streaming message rebuilds safe text once for every appended delta", () => {
  const document = new FakeDocument();
  const timeline = new FakeNode();
  timeline.ownerDocument = document;
  const message = beginStreamingMessage(timeline, "response-1");
  appendStreamingDelta(message, "Nova ");
  appendStreamingDelta(message, "responds.");
  assert.equal(message.querySelector("[data-message-text]").textContent, "Nova responds.");
});

test("composer keeps drafts only in the live control and never writes browser storage", async () => {
  const storage = new Map([["nova_companion_draft_v1", "draft"]]);
  const calls = [];
  const form = new FakeNode("form");
  const input = new FakeNode("textarea");
  input.value = "draft";
  input.scrollHeight = 48;
  const sendButton = new FakeNode("button");
  const controller = createComposerController({
    form, input, sendButton,
    storage: { getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
    onSubmit: async (text) => calls.push(text),
  });
  input.value = "voice transcript";
  input.listeners.get("input")();
  await controller.submit();
  assert.equal(storage.get("nova_companion_draft_v1"), "draft");
  controller.markRequestAccepted();
  assert.equal(storage.get("nova_companion_draft_v1"), "draft");
  assert.equal(input.value, "");
  assert.deepEqual(calls, ["voice transcript"]);
});

test("composer passes accepted evidence as a callable option to the submit lifecycle", async () => {
  const storage = new Map([["nova_companion_draft_v1", "draft"]]);
  const form = new FakeNode("form");
  const input = new FakeNode("textarea");
  input.value = "draft";
  input.scrollHeight = 48;
  const sendButton = new FakeNode("button");
  let receivedAcceptedEvidence = false;
  const controller = createComposerController({
    form, input, sendButton,
    storage: { getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) },
    onSubmit: async (_text, { markRequestAccepted }) => {
      assert.equal(typeof markRequestAccepted, "function");
      markRequestAccepted();
      receivedAcceptedEvidence = true;
    },
  });
  await controller.submit();
  assert.equal(receivedAcceptedEvidence, true);
  assert.equal(storage.has("nova_companion_draft_v1"), true);
});

test("composer restores focus to Send unless the user explicitly requests the textarea", () => {
  const form = new FakeNode("form");
  const input = new FakeNode("textarea");
  input.scrollHeight = 48;
  const sendButton = new FakeNode("button");
  const controller = createComposerController({ form, input, sendButton, storage: new Map() });
  controller.restoreFocus();
  assert.equal(sendButton.focused, true);
  assert.equal(input.focused, undefined);
  controller.restoreFocus({ userInitiated: true });
  assert.equal(input.focused, true);
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

test("identity, trust, sensor, tool, and sheet fields are display-only projections", () => {
  const state = createInitialCompanionState({ clientId: "desktop", conversationId: "conv-2" });
  assert.deepEqual(state.trust, { local: null, provider: "", model: "", memoryUsed: false });
  assert.equal(state.sheet, null);
  assert.equal(state.camera.active, false);
  assert.equal(state.microphone.active, false);
  assert.equal(state.activeTool, null);
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

test("tool proposals apply only to the active matching request", () => {
  const initial = createInitialCompanionState({});
  const submitted = reduceCompanionState(initial, { type: "SUBMIT", requestId: "r", text: "Hi" });
  const stale = reduceCompanionState(submitted, { type: "TOOL_PROPOSED", requestId: "old", toolName: "vision.observe" });
  const proposed = reduceCompanionState(submitted, { type: "TOOL_PROPOSED", requestId: "r", toolName: "vision.observe" });
  assert.equal(stale, submitted);
  assert.equal(proposed.phase, "submitting");
  assert.deepEqual(proposed.activeTool, { name: "vision.observe", status: "proposed" });
  assert.equal(presenceViewModel(proposed, false).label, "Nova is proposing an action");
});

test("late and evicted tool proposals cannot start or revive requests", () => {
  let state = createInitialCompanionState({});
  assert.equal(reduceCompanionState(state, { type: "TOOL_PROPOSED", requestId: "blank", toolName: "vision.observe" }), state);
  for (let index = 0; index < 22; index += 1) {
    state = reduceCompanionState(state, { type: "SUBMIT", requestId: `r-${index}`, text: "Hi" });
  }
  const completed = reduceCompanionState(state, { type: "COMPLETED", requestId: "r-21" });
  const evicted = reduceCompanionState(completed, { type: "TOOL_PROPOSED", requestId: "r-0", toolName: "vision.observe" });
  const completedLate = reduceCompanionState(completed, { type: "TOOL_PROPOSED", requestId: "r-21", toolName: "vision.observe" });
  assert.equal(evicted, completed);
  assert.equal(completedLate, completed);
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
