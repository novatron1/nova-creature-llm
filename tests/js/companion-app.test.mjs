import assert from "node:assert/strict";
import test from "node:test";

import * as companionApp from "../../assets/nova_companion/companion-app.js";

const {
  acquireBrowserStorage,
  bootstrapCompanion,
  createCompanionIdentity,
  createSelectedPictureVisionSubmitter,
  resolveVisionFocusRestoreTarget,
  startCompanion,
  storageValue,
  stopVoiceAndActiveRequest,
} = companionApp;

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const pictureFrame = Object.freeze({
  filename: "nova-phone.jpg",
  mimeType: "image/jpeg",
  imageBase64: "abc",
  width: 606,
  height: 1280,
  resized: true,
});

test("vision focus restoration uses the persistent Spark button when its invoker was detached", () => {
  const detachedInvoker = { isConnected: false, focus() { throw new Error("detached invoker must not receive focus"); } };
  let focused = 0;
  const sparkButton = { isConnected: true, focus() { focused += 1; } };

  const target = resolveVisionFocusRestoreTarget(detachedInvoker, sparkButton);
  assert.equal(target, sparkButton);
  target.focus({ preventScroll: true });
  assert.equal(focused, 1);
});

test("vision focus restoration keeps a connected invoker when it remains durable", () => {
  const invoker = { isConnected: true, focus() {} };
  const sparkButton = { isConnected: true, focus() {} };
  assert.equal(resolveVisionFocusRestoreTarget(invoker, sparkButton), invoker);
});

test("voice Stop cancels the active normal chat request after stopping local voice", async () => {
  const calls = [];
  await stopVoiceAndActiveRequest({
    voice: { stop() { calls.push("voice.stop"); } },
    api: { cancel: async (requestId) => { calls.push(`cancel:${requestId}`); } },
    requestId: "request_7",
  });
  assert.deepEqual(calls, ["voice.stop", "cancel:request_7"]);
});

test("blocked browser storage falls back to generated in-memory Companion IDs", () => {
  assert.equal(typeof acquireBrowserStorage, "function");
  assert.equal(typeof createCompanionIdentity, "function");
  assert.equal(typeof storageValue, "function");
  const blockedGlobal = {};
  Object.defineProperty(blockedGlobal, "localStorage", {
    get() { throw new Error("storage blocked"); },
  });
  const storage = acquireBrowserStorage(blockedGlobal);
  assert.equal(storage, null);
  assert.match(storageValue(storage, "client-key", "client"), /^client_/);
  assert.match(storageValue(storage, "conversation-key", "conversation"), /^conversation_/);
  const identity = createCompanionIdentity(blockedGlobal);
  assert.match(identity.clientId, /^client_/);
  assert.match(identity.conversationId, /^conversation_/);
});

test("available browser storage preserves existing Companion IDs", () => {
  const existing = new Map([
    ["client-key", "client_existing"],
    ["conversation-key", "conversation_existing"],
  ]);
  const storage = {
    getItem(key) { return existing.get(key) || null; },
    setItem(key, value) { existing.set(key, value); },
  };
  assert.equal(storageValue(storage, "client-key", "client"), "client_existing");
  assert.equal(storageValue(storage, "conversation-key", "conversation"), "conversation_existing");
  const globalLike = { localStorage: storage };
  const identity = createCompanionIdentity(globalLike, {
    clientKey: "client-key",
    conversationKey: "conversation-key",
  });
  assert.deepEqual(identity, {
    clientId: "client_existing",
    conversationId: "conversation_existing",
  });
});

test("bootstrap failure becomes visible and fail closed without exposing the raw error", async () => {
  assert.equal(typeof startCompanion, "function");
  const elements = new Map();
  const makeElement = () => ({
    attributes: new Map(),
    classList: {
      values: new Set(["sr-only"]),
      add(value) { this.values.add(value); },
      remove(value) { this.values.delete(value); },
      contains(value) { return this.values.has(value); },
    },
    dataset: {},
    textContent: "",
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
    getAttribute(name) { return this.attributes.get(name); },
  });
  const root = makeElement();
  const trust = makeElement();
  const status = makeElement();
  const input = makeElement();
  const send = makeElement();
  const spark = makeElement();
  elements.set("companionApp", root);
  elements.set("companionTrustLabel", trust);
  elements.set("companionLiveStatus", status);
  elements.set("companionInput", input);
  elements.set("companionSendButton", send);
  elements.set("novaSparkButton", spark);
  const document = { getElementById(id) { return elements.get(id) || null; } };

  await startCompanion({
    document,
    boot: async () => {
      throw new Error("private prompt and credential material");
    },
  });

  assert.equal(root.getAttribute("aria-busy"), "false");
  assert.equal(root.dataset.companionReady, "false");
  assert.equal(trust.textContent, "Setup unavailable");
  assert.equal(status.classList.contains("sr-only"), false);
  assert.match(status.textContent, /reload/i);
  assert.match(status.textContent, /Nova Classic/i);
  assert.equal(status.textContent.includes("private prompt"), false);
  assert.equal(status.textContent.includes("credential"), false);
  assert.equal(input.disabled, true);
  assert.equal(send.disabled, true);
  assert.equal(spark.disabled, true);
});

test("synchronously thrown bootstrap failures use the same safe recovery presentation", async () => {
  const root = {
    attributes: new Map(),
    classList: { add() {}, remove() {} },
    dataset: {},
    setAttribute(name, value) { this.attributes.set(name, String(value)); },
  };
  const trust = { textContent: "" };
  const status = {
    classList: { add() {}, remove() {} },
    textContent: "",
  };
  const elements = new Map([
    ["companionApp", root],
    ["companionTrustLabel", trust],
    ["companionLiveStatus", status],
  ]);
  const document = { getElementById(id) { return elements.get(id) || null; } };
  const result = await startCompanion({
    document,
    boot() { throw new Error("synchronous private failure"); },
  });
  assert.equal(result, null);
  assert.equal(root.attributes.get("aria-busy"), "false");
  assert.equal(trust.textContent, "Setup unavailable");
  assert.equal(status.textContent.includes("synchronous private failure"), false);
});

class BootstrapElement {
  constructor(document, tagName, id = "") {
    this.ownerDocument = document;
    this.tagName = tagName;
    this.id = id;
    this.children = [];
    this.parent = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this.dataset = {};
    this.style = {};
    this.classList = {
      values: new Set(),
      add: (...values) => values.forEach((value) => this.classList.values.add(value)),
      remove: (...values) => values.forEach((value) => this.classList.values.delete(value)),
      contains: (value) => this.classList.values.has(value),
    };
    this.hidden = false;
    this.disabled = false;
    this.isConnected = true;
    this.scrollHeight = 44;
    this.scrollTop = 0;
    this.textContent = "";
    this.value = "";
  }

  append(...nodes) {
    for (const node of nodes.filter((item) => item?.tagName)) {
      node.parent = this;
      this.children.push(node);
    }
  }
  appendChild(node) { this.append(node); return node; }
  insertBefore(node, reference) {
    node.parent = this;
    const index = this.children.indexOf(reference);
    if (index < 0) this.children.push(node);
    else this.children.splice(index, 0, node);
    return node;
  }
  replaceChildren(...nodes) {
    this.children = [];
    this.append(...nodes);
  }
  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter((child) => child !== this);
    this.parent = null;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  removeAttribute(name) { this.attributes.delete(name); }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  focus() { this.ownerDocument.activeElement = this; }
  querySelectorAll() {
    const found = [];
    const visit = (node) => {
      for (const child of node.children || []) {
        if (["button", "input", "textarea", "select", "a"].includes(child.tagName) && !child.disabled) {
          found.push(child);
        }
        visit(child);
      }
    };
    visit(this);
    return found;
  }
}

function createBootstrapDom() {
  const document = {
    activeElement: null,
    elements: new Map(),
    listeners: new Map(),
    createElement(tagName) { return new BootstrapElement(this, tagName); },
    createTextNode() { return { tagName: "#text" }; },
    getElementById(id) { return this.elements.get(id) || null; },
    addEventListener(type, listener) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); },
  };
  document.body = new BootstrapElement(document, "body");
  document.activeElement = document.body;
  const add = (id, tagName) => {
    const element = new BootstrapElement(document, tagName, id);
    document.elements.set(id, element);
    return element;
  };
  const root = add("companionApp", "main");
  const timeline = add("conversationTimeline", "section");
  const form = add("companionComposer", "form");
  const input = add("companionInput", "textarea");
  const send = add("companionSendButton", "button");
  form.append(input, send);
  add("novaPresence", "section");
  add("novaFace", "div");
  add("novaGreeting", "h1");
  add("companionLiveStatus", "p");
  add("companionTrustLabel", "span");
  add("companionTrustButton", "button");
  add("companionSheetHost", "section");
  add("companionSheetBackdrop", "div");
  add("novaSparkButton", "button");
  root.append(timeline, form);
  return { document, root, form, input, send };
}

function companionJsonResponse(payload = {}) {
  return {
    ok: true,
    status: 200,
    headers: { get() { return null; } },
    async json() { return payload; },
  };
}

function companionStreamResponse(text) {
  const encoder = new TextEncoder();
  const payload = [
    `event: response.delta\ndata: ${JSON.stringify({ event_type: "response.delta", response_id: "response-test", sequence: 0, delta: text })}\n\n`,
    `event: response.completed\ndata: ${JSON.stringify({ event_type: "response.completed", response_id: "response-test", sequence: 1, done: true, metadata: { trace: { source: "test" } } })}\n\n`,
    "data: [DONE]\n\n",
  ];
  let index = 0;
  return {
    ok: true,
    status: 200,
    headers: { get() { return "text/event-stream"; } },
    body: {
      getReader() {
        return {
          async read() {
            if (index >= payload.length) return { done: true, value: undefined };
            return { done: false, value: encoder.encode(payload[index++]) };
          },
          async cancel() {},
        };
      },
    },
  };
}

test("a real second Companion turn sends the completed first exchange as bounded canonical history", async () => {
  const dom = createBootstrapDom();
  const descriptors = new Map([
    ["fetch", Object.getOwnPropertyDescriptor(globalThis, "fetch")],
    ["authHeaders", Object.getOwnPropertyDescriptor(globalThis, "authHeaders")],
    ["pairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "pairedDeviceToken")],
    ["rememberPairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "rememberPairedDeviceToken")],
  ]);
  const chatBodies = [];
  const replies = ["The code word is blue.", "Yes, the code word is blue."];
  globalThis.authHeaders = (headers = {}) => ({ ...headers });
  globalThis.pairedDeviceToken = () => "";
  globalThis.rememberPairedDeviceToken = () => {};
  globalThis.fetch = async (url, options = {}) => {
    const path = String(url);
    if (path.endsWith("/nova/v1/chat")) {
      chatBodies.push(JSON.parse(options.body));
      return companionStreamResponse(replies[chatBodies.length - 1]);
    }
    if (path.endsWith("/api/pairing/status")) {
      return companionJsonResponse({ enabled: true, local_client: true, pairing_required: false });
    }
    if (path.endsWith("/status")) {
      return companionJsonResponse({ ok: true, private_mode: true });
    }
    return companionJsonResponse({ ok: true });
  };

  try {
    const controller = await bootstrapCompanion(dom.document);
    dom.input.value = "Remember that the code word is blue.";
    await controller.composer.submit();
    dom.input.value = "What is the code word?";
    await controller.composer.submit();

    assert.equal(chatBodies.length, 2);
    assert.deepEqual(chatBodies[0].conversation_history, []);
    assert.deepEqual(chatBodies[1].conversation_history, [
      { role: "user", content: "Remember that the code word is blue." },
      { role: "assistant", content: "The code word is blue." },
    ]);
    assert.equal(JSON.stringify(globalThis.localStorage || {}).includes("code word"), false);
    controller.destroy();
  } finally {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
});

test("an enabled Spark Voice action executes the same recognition path as Talk", async () => {
  const dom = createBootstrapDom();
  const descriptors = new Map([
    ["fetch", Object.getOwnPropertyDescriptor(globalThis, "fetch")],
    ["authHeaders", Object.getOwnPropertyDescriptor(globalThis, "authHeaders")],
    ["pairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "pairedDeviceToken")],
    ["rememberPairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "rememberPairedDeviceToken")],
    ["SpeechRecognition", Object.getOwnPropertyDescriptor(globalThis, "SpeechRecognition")],
  ]);
  let recognitionStarts = 0;
  class TestRecognition {
    start() {
      recognitionStarts += 1;
      this.onstart?.();
    }
    stop() { this.onend?.(); }
    abort() { this.onend?.(); }
  }
  globalThis.SpeechRecognition = TestRecognition;
  globalThis.authHeaders = (headers = {}) => ({ ...headers });
  globalThis.pairedDeviceToken = () => "";
  globalThis.rememberPairedDeviceToken = () => {};
  globalThis.fetch = async (url) => {
    const path = String(url);
    if (path.endsWith("/api/pairing/status")) {
      return companionJsonResponse({ enabled: true, local_client: true, pairing_required: false });
    }
    if (path.endsWith("/status")) {
      return companionJsonResponse({ ok: true, companion: {} });
    }
    if (path.endsWith("/nova/v1/capabilities")) {
      return companionJsonResponse({ audio: { input: { available: true } } });
    }
    if (path.endsWith("/nova/v1/tools")) {
      return companionJsonResponse({ object: "list", data: [] });
    }
    return companionJsonResponse({ ok: true });
  };

  try {
    const controller = await bootstrapCompanion(dom.document);
    const sparkButton = dom.document.getElementById("novaSparkButton");
    for (const listener of sparkButton.listeners.get("click") || []) listener({});
    await new Promise((resolve) => setTimeout(resolve, 0));
    const host = dom.document.getElementById("companionSheetHost");
    const voiceAction = host.querySelectorAll().find((item) => item.dataset.sparkAction === "voice");
    assert.ok(voiceAction);
    assert.equal(voiceAction.disabled, false);

    for (const listener of voiceAction.listeners.get("click") || []) listener({});
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(recognitionStarts, 1);
    controller.destroy();
  } finally {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  }
});

test("real Companion bootstrap mounts securely when the global storage getter throws", async () => {
  assert.equal(typeof bootstrapCompanion, "function");
  const dom = createBootstrapDom();
  const descriptors = new Map([
    ["localStorage", Object.getOwnPropertyDescriptor(globalThis, "localStorage")],
    ["fetch", Object.getOwnPropertyDescriptor(globalThis, "fetch")],
    ["authHeaders", Object.getOwnPropertyDescriptor(globalThis, "authHeaders")],
    ["pairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "pairedDeviceToken")],
    ["rememberPairedDeviceToken", Object.getOwnPropertyDescriptor(globalThis, "rememberPairedDeviceToken")],
  ]);
  const restore = () => {
    for (const [name, descriptor] of descriptors) {
      if (descriptor) Object.defineProperty(globalThis, name, descriptor);
      else delete globalThis[name];
    }
  };
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    get() { throw new Error("storage getter blocked"); },
  });
  globalThis.authHeaders = (headers = {}) => ({ ...headers });
  globalThis.pairedDeviceToken = () => "";
  globalThis.rememberPairedDeviceToken = () => {};
  globalThis.fetch = async (url) => {
    const path = String(url);
    let payload = { ok: true };
    if (path.endsWith("/api/pairing/status")) {
      payload = { ok: true, enabled: true, local_client: true, pairing_required: false };
    } else if (path.endsWith("/status")) {
      payload = {
        ok: true,
        private_mode: true,
        regular_chat_routing: { primary_provider: "existing-nova", primary_model: "nova" },
      };
    }
    return { ok: true, status: 200, async json() { return payload; } };
  };

  try {
    const controller = await bootstrapCompanion(dom.document);
    assert.ok(controller);
    assert.equal(dom.root.dataset.companionReady, "true");
    assert.equal(dom.root.getAttribute("aria-busy"), "false");
    assert.equal(dom.document.getElementById("companionTrustLabel").textContent, "Local · Private");
    assert.equal(dom.document.getElementById("companionTrustButton").getAttribute("aria-expanded"), "false");
    assert.ok(dom.form.children.some((child) => child.id === "companionVoiceButton"));
    assert.ok(dom.form.listeners.get("submit")?.size);
    assert.equal(dom.input.disabled, false);
    assert.equal(dom.send.type, "submit");
    controller.destroy();
  } finally {
    restore();
  }
});

test("selected pictures grant local vision permission before upload without starting browser camera", async () => {
  const calls = [];
  const statuses = [];
  const results = [];
  let getUserMediaCalls = 0;
  const originalNavigator = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: { mediaDevices: { getUserMedia() { getUserMediaCalls += 1; } } },
  });
  const controller = new AbortController();
  const api = {
    async postPermissionCommand(text, options) {
      assert.equal(options.signal, controller.signal);
      calls.push(`permission:${text}`);
      return {
        response: "Camera access allowed.",
        trace: { permissions_snapshot: { camera: true } },
        permissions: { camera: true, mic: false, speaker: false },
      };
    },
    async postVision(payload, options) {
      assert.equal(options.signal, controller.signal);
      assert.equal(payload.persist, false);
      assert.equal(payload.prompt, "Identify this app.");
      calls.push("vision");
      return {
        ok: true,
        response: "This is Nova Creature.",
        trace: { skills: ["tesseract_ocr"], image_persisted: false },
        answer_status: { safety: "checked" },
        permissions: { camera: true, mic: false, speaker: false },
      };
    },
  };

  try {
    const submitter = createSelectedPictureVisionSubmitter({
      api,
      signal: controller.signal,
      isCurrentSheet: () => true,
      onStatus: (value) => statuses.push(value),
      onResult: (value) => results.push(value),
    });
    await submitter.submit(pictureFrame, "Identify this app.");
  } finally {
    if (originalNavigator) Object.defineProperty(globalThis, "navigator", originalNavigator);
    else delete globalThis.navigator;
  }

  assert.deepEqual(calls, ["permission:allow camera", "vision"]);
  assert.equal(getUserMediaCalls, 0);
  assert.equal(results.length, 1);
  assert.match(statuses[0], /local vision permission/i);
  assert.match(statuses[0], /does not start.*browser camera/i);
  assert.equal(statuses.at(-1), "Result added. Browser camera remains off.");
});

test("selected-picture completion preserves a browser camera that was already live", async () => {
  const statuses = [];
  const submitter = createSelectedPictureVisionSubmitter({
    api: {
      async postPermissionCommand() { return { permissions: { camera: true } }; },
      async postVision() {
        return { ok: true, response: "seen", trace: {}, permissions: { camera: true } };
      },
    },
    cameraIsActive: () => true,
    onStatus: (value) => statuses.push(value),
  });

  await submitter.submit(pictureFrame, "Look");

  assert.equal(statuses.at(-1), "Result added. Browser camera remains live.");
});

test("selected pictures reuse one successful permission grant within the same sheet", async () => {
  let permissionCalls = 0;
  let visionCalls = 0;
  const submitter = createSelectedPictureVisionSubmitter({
    api: {
      async postPermissionCommand() {
        permissionCalls += 1;
        return { permissions: { camera: true } };
      },
      async postVision() {
        visionCalls += 1;
        return { ok: true, response: "seen", trace: {}, permissions: { camera: true } };
      },
    },
  });

  await submitter.submit(pictureFrame, "First look");
  await submitter.submit(pictureFrame, "Second look");

  assert.equal(permissionCalls, 1);
  assert.equal(visionCalls, 2);
});

test("closing during selected-picture permission prevents a later upload or result", async () => {
  const permission = deferred();
  const controller = new AbortController();
  let current = true;
  let visionCalls = 0;
  let resultCalls = 0;
  const submitter = createSelectedPictureVisionSubmitter({
    api: {
      postPermissionCommand(_text, options) {
        assert.equal(options.signal, controller.signal);
        return permission.promise;
      },
      async postVision() {
        visionCalls += 1;
        return { ok: true, response: "stale" };
      },
    },
    signal: controller.signal,
    isCurrentSheet: () => current,
    onResult: () => { resultCalls += 1; },
  });

  const submission = submitter.submit(pictureFrame, "Do not upload after close");
  await new Promise((resolve) => setImmediate(resolve));
  current = false;
  controller.abort();
  permission.resolve({ permissions: { camera: true } });
  const result = await submission;

  assert.equal(result, null);
  assert.equal(visionCalls, 0);
  assert.equal(resultCalls, 0);
});

test("selected-picture ok:false responses end with a safe failure status", async () => {
  const statuses = [];
  const submitter = createSelectedPictureVisionSubmitter({
    api: {
      async postPermissionCommand() { return { permissions: { camera: true } }; },
      async postVision() {
        return {
          ok: false,
          error: "Vision could not inspect this picture.",
          trace: {},
          permissions: { camera: true },
        };
      },
    },
    onStatus: (value) => statuses.push(value),
  });

  await submitter.submit(pictureFrame, "Look");

  assert.equal(statuses.at(-1), "Nova could not inspect that picture. Browser camera remains off.");
});

test("selected-picture request errors replace inspecting copy with a safe failure status", async () => {
  const statuses = [];
  const submitter = createSelectedPictureVisionSubmitter({
    api: {
      async postPermissionCommand() { return { permissions: { camera: true } }; },
      async postVision() { throw new Error("private transport details"); },
    },
    onStatus: (value) => statuses.push(value),
  });

  await assert.rejects(() => submitter.submit(pictureFrame, "Look"), /private transport details/);

  assert.equal(statuses.at(-1), "Nova could not inspect that picture. Browser camera remains off.");
  assert.doesNotMatch(statuses.at(-1), /private transport details/);
});
