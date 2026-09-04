import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

import * as trustModule from "../../assets/nova_companion/companion-trust.js";

const {
  createTrustController,
  projectTrustState,
  redactTrustValue,
  trustConnectionLabel,
} = trustModule;

function loadFoundationHelpers() {
  const stored = new Map();
  const context = {
    URL,
    clearTimeout,
    console: { error() {}, log() {}, warn() {} },
    document: {
      getElementById() { return null; },
    },
    history: { replaceState() {} },
    location: { href: "http://localhost/companion" },
    localStorage: {
      getItem(key) { return stored.get(key) || null; },
      removeItem(key) { stored.delete(key); },
      setItem(key, value) { stored.set(key, String(value)); },
    },
    navigator: {
      serviceWorker: { register() { return Promise.resolve(); } },
      userAgent: "Node test browser",
    },
    setTimeout,
  };
  context.window = context;
  context.addEventListener = () => {};
  return readFile(new URL("../../assets/nova_foundation_ui.js", import.meta.url), "utf8")
    .then((source) => {
      vm.runInNewContext(source, context, { filename: "nova_foundation_ui.js" });
      return context;
    });
}

test("trust projection never copies private content", () => {
  assert.equal(typeof projectTrustState, "function");
  const projected = projectTrustState({
    status: { local: true, private_mode: true, permissions: { camera: false } },
    health: { provider: "existing-nova", model: "nova", prompt: "secret prompt" },
    trace: { answer_status: { memory: "used" }, hidden_reasoning: "secret" },
  });
  assert.deepEqual(projected, {
    connection: "local",
    provider: "existing-nova",
    model: "nova",
    privateMode: true,
    memoryUsed: true,
    camera: { active: false, persisted: false },
    microphone: { active: false },
    pendingConfirmation: false,
    estimatedCost: null,
    recentActions: [],
  });
  assert.equal(JSON.stringify(projected).includes("secret"), false);
});

test("sensitive keys are always redacted", () => {
  assert.equal(typeof redactTrustValue, "function");
  for (const key of [
    "authorization",
    "api_key",
    "apiKey",
    "token",
    "prompt",
    "memory_content",
    "image_base64",
    "hidden_reasoning",
    "tool_arguments",
  ]) {
    assert.equal(redactTrustValue(key, "secret"), "[redacted]");
  }
  assert.equal(redactTrustValue("provider", "existing-nova"), "existing-nova");
});

test("trust projection copies only safe recent action metadata", () => {
  const projected = projectTrustState({
    connection: "remote",
    trace: {
      recent_actions: [{
        name: "web.search",
        state: "completed",
        timestamp: "2026-07-29T12:00:00Z",
        arguments: { query: "private question" },
        result: "private answer",
        authorization: "Bearer private",
      }],
    },
  });
  assert.deepEqual(projected.recentActions, [{
    name: "web.search",
    state: "completed",
    timestamp: "2026-07-29T12:00:00Z",
  }]);
  const serialized = JSON.stringify(projected);
  assert.equal(serialized.includes("private question"), false);
  assert.equal(serialized.includes("private answer"), false);
  assert.equal(serialized.includes("Bearer private"), false);
});

test("unknown or missing action states never become completed", () => {
  const projected = projectTrustState({
    trace: {
      recent_actions: [
        { name: "missing.state" },
        { name: "future.state", state: "teleported" },
        { name: "observed.state", state: "attempted" },
      ],
    },
  });
  assert.deepEqual(projected.recentActions, [{
    name: "observed.state",
    state: "attempted",
    timestamp: "",
  }]);
});

test("trust projection uses the public regular-chat route for current provider and model", () => {
  const projected = projectTrustState({
    status: {
      regular_chat_routing: {
        primary_provider: "ollama",
        primary_model: "nova-qwen3-14b-8k",
        primary_adapter_id: "must-not-be-copied",
      },
    },
  });
  assert.equal(projected.provider, "ollama");
  assert.equal(projected.model, "nova-qwen3-14b-8k");
  assert.equal(JSON.stringify(projected).includes("must-not-be-copied"), false);
});

test("unrelated updates and refreshes preserve cost and recent action evidence until explicitly replaced", async () => {
  const api = {
    async getJson(path) {
      if (path === "/api/pairing/status") {
        return { enabled: true, local_client: true, pairing_required: false };
      }
      return { ok: true };
    },
    async postJson() { return {}; },
  };
  const controller = createTrustController({ api, rememberPairedDeviceToken() {} });
  controller.update({
    trace: {
      estimated_cost: 0.25,
      recent_actions: [{
        name: "memory.search",
        state: "completed",
        timestamp: "2026-07-29T12:00:00Z",
      }],
    },
  });
  controller.update({ camera: { active: true, persisted: false } });
  await controller.refresh();
  assert.equal(controller.getState().estimatedCost, 0.25);
  assert.deepEqual(controller.getState().recentActions, [{
    name: "memory.search",
    state: "completed",
    timestamp: "2026-07-29T12:00:00Z",
  }]);

  controller.update({ trace: { estimated_cost: null, recent_actions: [] } });
  assert.equal(controller.getState().estimatedCost, null);
  assert.deepEqual(controller.getState().recentActions, []);
});

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

function refreshBatchApi() {
  const batches = [];
  let calls = 0;
  return {
    batches,
    async postJson() { return {}; },
    getJson() {
      const batchIndex = Math.floor(calls / 4);
      const itemIndex = calls % 4;
      calls += 1;
      if (!batches[batchIndex]) {
        batches[batchIndex] = Array.from({ length: 4 }, () => deferred());
      }
      return batches[batchIndex][itemIndex].promise;
    },
  };
}

function resolveRefreshBatch(batch, { pairing, status, healthz = { ok: true }, novaHealth = { ok: true } }) {
  batch[0].resolve(pairing);
  batch[1].resolve(status);
  batch[2].resolve(healthz);
  batch[3].resolve(novaHealth);
}

test("an older refresh cannot overwrite a newer Trust projection", async () => {
  const api = refreshBatchApi();
  const controller = createTrustController({ api, rememberPairedDeviceToken() {} });
  const older = controller.refresh();
  const newer = controller.refresh();
  resolveRefreshBatch(api.batches[1], {
    pairing: { enabled: true, local_client: false, pairing_required: false },
    status: { ok: true, provider: "new-provider", model: "new-model" },
  });
  await newer;
  resolveRefreshBatch(api.batches[0], {
    pairing: { enabled: true, local_client: false, pairing_required: true },
    status: { ok: true, provider: "stale-provider", model: "stale-model" },
  });
  await older;
  assert.equal(controller.getState().provider, "new-provider");
  assert.equal(controller.getState().model, "new-model");
  assert.equal(controller.pairingRequired, false);
});

test("post-pair refresh wins over an older pre-pair refresh", async () => {
  const api = refreshBatchApi();
  api.postJson = async () => ({ token: "nova_valid_test_value" });
  const controller = createTrustController({
    api,
    rememberPairedDeviceToken() {},
  });
  const prePair = controller.refresh();
  const exchange = controller.exchangePairing({ deviceName: "Test phone", code: "123456" });
  await Promise.resolve();
  resolveRefreshBatch(api.batches[1], {
    pairing: { enabled: true, local_client: false, pairing_required: false },
    status: { ok: true, provider: "paired-provider", model: "paired-model" },
  });
  await exchange;
  resolveRefreshBatch(api.batches[0], {
    pairing: { enabled: true, local_client: false, pairing_required: true },
    status: { ok: true, provider: "pre-pair-provider", model: "pre-pair-model" },
  });
  await prePair;
  assert.equal(controller.getState().provider, "paired-provider");
  assert.equal(controller.pairingRequired, false);
});

test("pairing-disabled remote access is labeled plain Remote everywhere", async () => {
  assert.equal(typeof trustConnectionLabel, "function");
  const snapshots = [];
  const controller = createTrustController({
    api: {
      async getJson(path) {
        if (path === "/api/pairing/status") {
          return { enabled: false, local_client: false, pairing_required: false };
        }
        return { ok: true };
      },
      async postJson() { return {}; },
    },
    rememberPairedDeviceToken() {},
    onStateChange(state, access) { snapshots.push({ state, access }); },
  });
  const state = await controller.refresh();
  const access = snapshots.at(-1).access;
  assert.equal(access.pairingEnabled, false);
  assert.equal(access.paired, false);
  assert.equal(trustConnectionLabel(state, access), "Remote");
});

test("a failed pairing-status check never turns partial remote evidence into Local", async () => {
  const controller = createTrustController({
    api: {
      async getJson(path) {
        if (path === "/api/pairing/status") throw new Error("pairing status unavailable");
        if (path === "/status") return { ok: true, private_mode: true };
        return { ok: true };
      },
      async postJson() { return {}; },
    },
    rememberPairedDeviceToken() {},
  });

  const state = await controller.refresh();

  assert.equal(state.connection, "unknown");
  assert.equal(trustConnectionLabel(state), "Connection unknown");
  assert.equal(trustConnectionLabel(state).includes("Local"), false);
});

test("an asserted Local label is ignored without affirmative same-host evidence", () => {
  const state = projectTrustState({
    connection: "local",
    status: { ok: true, private_mode: true },
  });

  assert.equal(state.connection, "unknown");
  assert.equal(trustConnectionLabel(state), "Connection unknown");
});

test("validated Foundation token helpers authorize later requests and reject invalid text", async () => {
  const foundation = await loadFoundationHelpers();
  assert.equal(typeof foundation.pairedDeviceToken, "function");
  assert.equal(typeof foundation.rememberPairedDeviceToken, "function");
  foundation.rememberPairedDeviceToken("nova_valid_test_value");
  assert.equal(foundation.pairedDeviceToken(), "nova_valid_test_value");
  assert.equal(
    foundation.authHeaders({ Accept: "application/json" }).Authorization,
    "Bearer nova_valid_test_value",
  );
  assert.throws(
    () => foundation.rememberPairedDeviceToken("invalid"),
    /invalid device token/i,
  );
  assert.equal(foundation.pairedDeviceToken(), "nova_valid_test_value");
});

test("Foundation auth headers ignore invalid token text already present in browser storage", async () => {
  const foundation = await loadFoundationHelpers();
  foundation.localStorage.setItem("nova_paired_device_token_v1", "invalid");
  assert.equal(foundation.pairedDeviceToken(), "");
  assert.equal("Authorization" in foundation.authHeaders({ Accept: "application/json" }), false);
});

test("pairing exchange remembers the validated token, clears code from state, and refreshes trust", async () => {
  assert.equal(typeof createTrustController, "function");
  const exchanges = [];
  let remembered = "";
  const api = {
    async postJson(path, body) {
      exchanges.push({ path, body: { ...body } });
      return { token: "nova_valid_test_value" };
    },
    async getJson(path) {
      if (path === "/api/pairing/status") {
        return { ok: true, local_client: false, pairing_required: false };
      }
      if (path === "/status") {
        return { ok: true, private_mode: true, provider: "existing-nova", model: "nova" };
      }
      return { ok: true };
    },
  };
  const controller = createTrustController({
    api,
    rememberPairedDeviceToken(value) { remembered = value; },
  });
  const state = await controller.exchangePairing({
    deviceName: "Test phone",
    code: "123456",
  });
  assert.deepEqual(exchanges, [{
    path: "/api/pairing/exchange",
    body: { code: "123456", device_name: "Test phone" },
  }]);
  assert.equal(remembered, "nova_valid_test_value");
  assert.equal(state.connection, "remote");
  assert.equal(state.provider, "existing-nova");
  assert.equal(state.model, "nova");
  assert.equal(state.privateMode, true);
  assert.equal(JSON.stringify(controller.getState()).includes("123456"), false);
  assert.equal(JSON.stringify(controller.getState()).includes("nova_valid"), false);
});

test("invalid pairing code is rejected before an exchange request", async () => {
  let calls = 0;
  const controller = createTrustController({
    api: {
      async postJson() { calls += 1; return {}; },
      async getJson() { return {}; },
    },
    rememberPairedDeviceToken() {},
  });
  await assert.rejects(
    controller.exchangePairing({ deviceName: "Test phone", code: "12 34" }),
    /six-digit/i,
  );
  assert.equal(calls, 0);
});

test("pairing-required API failures open pairing and remain rejected for explicit retry", async () => {
  let opened = 0;
  const controller = createTrustController({
    api: {
      async getJson() { return {}; },
      async postJson() { return {}; },
    },
    rememberPairedDeviceToken() {},
    onPairingRequired() { opened += 1; },
  });
  const wrapped = controller.wrapApi({
    async streamChat() {
      const error = new Error("Pairing required");
      error.status = 401;
      error.code = "pairing_required";
      throw error;
    },
  });
  await assert.rejects(wrapped.streamChat({ text: "Do not replay me" }), /Pairing required/);
  await assert.rejects(wrapped.streamChat({ text: "Do not replace the open sheet" }), /Pairing required/);
  assert.equal(opened, 1);
});

class FakeElement {
  constructor(document, tagName) {
    this.ownerDocument = document;
    this.tagName = tagName;
    this.children = [];
    this.parent = null;
    this.hidden = false;
    this.disabled = false;
    this.isConnected = true;
    this.listeners = new Map();
    this.attributes = new Map();
    this.classList = {
      values: new Set(),
      add: (...values) => values.forEach((value) => this.classList.values.add(value)),
      remove: (...values) => values.forEach((value) => this.classList.values.delete(value)),
    };
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
  replaceChildren(...nodes) {
    for (const child of this.children) child.parent = null;
    this.children = [];
    this.append(...nodes);
  }
  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter((child) => child !== this);
    this.parent = null;
    if (this.ownerDocument.activeElement === this) this.ownerDocument.activeElement = this.ownerDocument.body;
  }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  async dispatch(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ preventDefault() {}, key: "", shiftKey: false, ...event });
    }
  }
  focus() { this.ownerDocument.activeElement = this; }
  querySelectorAll() {
    const descendants = [];
    const visit = (node) => {
      for (const child of node.children) {
        if ((child.tagName === "button" || child.tagName === "input") && !child.disabled) descendants.push(child);
        visit(child);
      }
    };
    visit(this);
    return descendants;
  }
}

function createTrustDom() {
  const document = {
    activeElement: null,
    listeners: new Map(),
    elements: new Map(),
    createElement(tagName) { return new FakeElement(this, tagName); },
    getElementById(id) { return this.elements.get(id); },
    addEventListener(type, listener) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); },
    async dispatch(type, event = {}) {
      for (const listener of this.listeners.get(type) || []) {
        await listener({ preventDefault() {}, key: "", shiftKey: false, ...event });
      }
    },
  };
  document.body = new FakeElement(document, "body");
  document.activeElement = document.body;
  const button = new FakeElement(document, "button");
  const host = new FakeElement(document, "section");
  const backdrop = new FakeElement(document, "div");
  document.elements.set("companionTrustButton", button);
  document.elements.set("companionSheetHost", host);
  document.elements.set("companionSheetBackdrop", backdrop);
  return { document, button, host, backdrop };
}

function descendants(root, tagName) {
  const found = [];
  const visit = (node) => {
    for (const child of node.children) {
      if (child.tagName === tagName) found.push(child);
      visit(child);
    }
  };
  visit(root);
  return found;
}

test("pairing dialog owns focus through success, Escape, backdrop close, and trigger restoration", async () => {
  const dom = createTrustDom();
  const controller = createTrustController({
    document: dom.document,
    api: {
      async postJson() { return { token: "nova_valid_test_value" }; },
      async getJson(path) {
        if (path === "/api/pairing/status") {
          return { enabled: true, local_client: false, pairing_required: false };
        }
        return { ok: true };
      },
    },
    rememberPairedDeviceToken() {},
  });

  controller.openPairing(dom.button);
  assert.equal(dom.button.getAttribute("aria-expanded"), "true");
  const inputs = descendants(dom.host, "input");
  const form = descendants(dom.host, "form")[0];
  const buttons = descendants(dom.host, "button");
  assert.equal(dom.document.activeElement, inputs[0]);

  dom.document.activeElement = dom.document.body;
  await dom.document.dispatch("keydown", { key: "Tab" });
  assert.equal(dom.document.activeElement, inputs[0]);

  inputs[0].value = "Test phone";
  inputs[1].value = "123456";
  dom.document.activeElement = buttons[0];
  await form.dispatch("submit");
  assert.equal(buttons[1].textContent, "Close and Retry");
  assert.equal(dom.document.activeElement, buttons[1]);

  await dom.document.dispatch("keydown", { key: "Escape" });
  assert.equal(dom.host.hidden, true);
  assert.equal(dom.button.getAttribute("aria-expanded"), "false");
  assert.equal(dom.document.activeElement, dom.button);

  controller.open(dom.button);
  assert.equal(dom.button.getAttribute("aria-expanded"), "true");
  await dom.backdrop.dispatch("click");
  assert.equal(dom.host.hidden, true);
  assert.equal(dom.button.getAttribute("aria-expanded"), "false");
  assert.equal(dom.document.activeElement, dom.button);
});
