import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import vm from "node:vm";

import * as trustModule from "../../assets/nova_companion/companion-trust.js";

const {
  createTrustController,
  projectTrustState,
  redactTrustValue,
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
    status: { private_mode: true, permissions: { camera: false } },
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
