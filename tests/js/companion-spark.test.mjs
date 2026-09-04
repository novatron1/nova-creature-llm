import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPANION_CAPABILITIES,
  classicPanelUrl,
  resolveCapabilityAvailability,
  resolveSparkActions,
} from "../../assets/nova_companion/companion-spark.js";
import { loadSparkServerState } from "../../assets/nova_companion/companion-app.js";

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

class FakeElement {
  constructor(document, tagName) {
    this.ownerDocument = document;
    this.tagName = tagName;
    this.children = [];
    this.dataset = {};
    this.hidden = false;
    this.disabled = false;
    this.listeners = new Map();
    this.attributes = new Map();
    this.focusCount = 0;
  }

  append(...nodes) { this.children.push(...nodes.filter((node) => node?.tagName)); }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type).add(listener);
  }
  removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
  dispatch(type, event = {}) {
    for (const listener of this.listeners.get(type) || []) {
      listener({ preventDefault() {}, key: "", shiftKey: false, ...event });
    }
  }
  focus() { this.ownerDocument.activeElement = this; this.focusCount += 1; }
  querySelectorAll() {
    const descendants = [];
    const visit = (node) => {
      for (const child of node.children) {
        if (child.tagName === "button" && !child.disabled) descendants.push(child);
        visit(child);
      }
    };
    visit(this);
    return descendants;
  }
}

function createSparkDom() {
  const document = {
    activeElement: null,
    listeners: new Map(),
    createElement(tagName) { return new FakeElement(this, tagName); },
    createTextNode() { return {}; },
    addEventListener(type, listener) {
      if (!this.listeners.has(type)) this.listeners.set(type, new Set());
      this.listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); },
    getElementById(id) { return this.elements.get(id); },
    elements: new Map(),
  };
  const button = new FakeElement(document, "button");
  const host = new FakeElement(document, "section");
  const backdrop = new FakeElement(document, "div");
  document.elements.set("novaSparkButton", button);
  document.elements.set("companionSheetHost", host);
  document.elements.set("companionSheetBackdrop", backdrop);
  return { document, button, host, backdrop };
}

function buttonsIn(host) {
  const buttons = [];
  const visit = (node) => {
    for (const child of node.children) {
      if (child.tagName === "button") buttons.push(child);
      visit(child);
    }
  };
  visit(host);
  return buttons;
}

test("the model cannot add an unregistered Spark action", () => {
  const shown = resolveSparkActions(
    [{ id: "chat", available: true }, { id: "invented-shell", available: true }],
    COMPANION_CAPABILITIES,
  );

  assert.deepEqual(shown.map((item) => item.id), ["chat"]);
});

test("classic panel URLs use an allowlist", () => {
  assert.equal(classicPanelUrl("memory"), "/classic?panel=memory");
  assert.equal(classicPanelUrl("../../settings"), "/classic");
});

test("unavailable capabilities remain visible with a reason", () => {
  const item = resolveCapabilityAvailability(
    { id: "vision", requiredCapability: "vision.image_input" },
    { capabilities: {} },
  );

  assert.equal(item.available, false);
  assert.equal(item.reason, "Vision is not available on this Nova server.");
});

test("server capability state may refine an unavailable reason without changing the action", () => {
  const item = resolveCapabilityAvailability(
    { id: "vision", requiredCapability: "vision.image_input" },
    { capabilities: { vision: { image_input: { available: false, reason: "Camera support is disabled." } } } },
  );

  assert.equal(item.id, "vision");
  assert.equal(item.available, false);
  assert.equal(item.reason, "Camera support is disabled.");
});

test("the current local vision service makes the fixed See action reachable without changing text-model image input", () => {
  const vision = COMPANION_CAPABILITIES.find((item) => item.id === "vision");
  const serverState = {
    capabilities: { vision: { image_input: { available: false, reason: "The text model has no image input." } } },
    companion: { vision_service: { available: true, endpoint: "/api/vision" } },
    items: new Map(),
  };
  const resolved = resolveCapabilityAvailability(vision, serverState);

  assert.equal(resolved.available, true);
  assert.equal(serverState.capabilities.vision.image_input.available, false);
});

test("an unavailable local vision service keeps See disabled with its honest reason", () => {
  const vision = COMPANION_CAPABILITIES.find((item) => item.id === "vision");
  const resolved = resolveCapabilityAvailability(vision, {
    companion: { vision_service: { available: false, reason: "The local vision service is offline." } },
    items: new Map(),
  });

  assert.equal(resolved.available, false);
  assert.equal(resolved.reason, "The local vision service is offline.");
});

test("an exact public vision.observe record overrides the local vision projection", () => {
  const vision = COMPANION_CAPABILITIES.find((item) => item.id === "vision");
  const resolved = resolveCapabilityAvailability(vision, {
    capabilities: { vision: { image_input: { available: false } } },
    companion: { vision_service: { available: true, endpoint: "/api/vision" } },
    items: new Map([[
      "vision.observe",
      {
        name: "vision.observe",
        availability_status: "disabled",
        reason: "The public vision tool is disabled for this device.",
      },
    ]]),
  });

  assert.equal(resolved.available, false);
  assert.equal(resolved.reason, "The public vision tool is disabled for this device.");
});

test("an unknown tool name cannot enable fixed See without the local service projection", () => {
  const vision = COMPANION_CAPABILITIES.find((item) => item.id === "vision");
  const resolved = resolveCapabilityAvailability(vision, {
    capabilities: { vision: { image_input: { available: false } } },
    items: new Map([["vision.inspect", { name: "vision.inspect", availability_status: "available" }]]),
  });

  assert.equal(resolved.available, false);
});

test("the fixed registry has visible labels in every approved Spark group", () => {
  const groups = new Set(COMPANION_CAPABILITIES.map((item) => item.group));
  assert.deepEqual(groups, new Set(["see", "speak", "create", "remember", "work", "system"]));
  for (const item of COMPANION_CAPABILITIES) {
    assert.ok(item.label);
    assert.ok(item.description);
    assert.ok(item.requiredPermission);
  }
});

test("camera tool metadata uses the documented live-input status without adding unknown actions", () => {
  const shown = resolveSparkActions([
    { name: "vision.observe", availability_status: "requires_live_input" },
    { name: "invented.shell", availability_status: "available" },
  ], COMPANION_CAPABILITIES);

  assert.deepEqual(shown.map((item) => item.id), ["vision"]);
  assert.equal(shown[0].available, true);

  const disabled = resolveSparkActions([
    { name: "vision.observe", availability_status: "disabled", reason: "Camera service is disabled." },
  ], COMPANION_CAPABILITIES);
  assert.equal(disabled[0].available, false);
  assert.equal(disabled[0].reason, "Camera service is disabled.");
});

test("unmapped Classic actions ignore similarly named tool records", () => {
  const chat = COMPANION_CAPABILITIES.find((item) => item.id === "chat");
  const resolved = resolveCapabilityAvailability(chat, {
    items: new Map([["chat", { availability_status: "disabled", reason: "Not a chat action." }]]),
  });

  assert.equal(resolved.available, true);
  assert.equal(resolved.reason, "");
});

test("Spark focuses immediately and never refocuses a hidden sheet after a delayed load closes", async () => {
  const dom = createSparkDom();
  const pending = deferred();
  const { createSparkController } = await import("../../assets/nova_companion/companion-spark.js");
  const controller = createSparkController({ ...dom, loadServerState: () => pending.promise });

  const opening = controller.open();
  assert.ok(dom.document.activeElement);
  assert.notEqual(dom.document.activeElement, dom.button);
  controller.close();
  assert.equal(dom.document.activeElement, dom.button);
  pending.resolve({});
  await opening;
  assert.equal(dom.document.activeElement, dom.button);
  assert.equal(dom.host.hidden, true);
});

test("destroy removes Spark click listeners and blocks old voice or pending-load reopen attempts", async () => {
  const dom = createSparkDom();
  const pending = deferred();
  const { createSparkController } = await import("../../assets/nova_companion/companion-spark.js");
  const controller = createSparkController({ ...dom, loadServerState: () => pending.promise });

  const opening = controller.open();
  controller.destroy();
  dom.button.dispatch("click");
  assert.equal(controller.isOpen, false);
  assert.equal(controller.handleVoiceCommand("open nova spark"), false);
  pending.resolve({});
  await opening;
  assert.equal(controller.isOpen, false);
  assert.equal(dom.document.activeElement, dom.button);
});

test("a late first open cannot overwrite focus from a newer Spark open", async () => {
  const dom = createSparkDom();
  const first = deferred();
  const second = deferred();
  let loads = 0;
  const { createSparkController } = await import("../../assets/nova_companion/companion-spark.js");
  const controller = createSparkController({
    ...dom,
    loadServerState: () => (loads++ === 0 ? first.promise : second.promise),
  });

  const openA = controller.open();
  controller.close();
  const openB = controller.open();
  second.resolve({ capabilities: {} });
  await openB;
  const focusFromB = dom.document.activeElement;
  first.resolve({ capabilities: { vision: { image_input: { available: true } } } });
  await openA;

  assert.equal(dom.document.activeElement, focusFromB);
  assert.equal(controller.isOpen, true);
});

test("separate Spark opens replace an available vision status with a fresh unavailable status", async () => {
  const dom = createSparkDom();
  const statusResponses = [
    { companion: { vision_service: { available: true, endpoint: "/api/vision" } } },
    {
      companion: {
        vision_service: {
          available: false,
          reason: "Vision authorization changed after the server restarted.",
        },
      },
    },
  ];
  let statusLoads = 0;
  const api = {
    async getStatus() {
      statusLoads += 1;
      return statusResponses.shift();
    },
    async getJson(path) {
      if (path === "/nova/v1/tools") return { data: [] };
      return { vision: { image_input: { available: false } } };
    },
  };
  const { createSparkController } = await import("../../assets/nova_companion/companion-spark.js");
  const controller = createSparkController({
    ...dom,
    loadServerState: () => loadSparkServerState(api),
  });

  await controller.open();
  const firstSee = buttonsIn(dom.host).find((item) => item.dataset.sparkAction === "vision");
  assert.equal(firstSee.disabled, false);

  controller.close();
  await controller.open();
  const secondSee = buttonsIn(dom.host).find((item) => item.dataset.sparkAction === "vision");
  assert.equal(secondSee.disabled, true);
  assert.equal(
    secondSee.children[1].children[1].textContent,
    "Vision authorization changed after the server restarted.",
  );
  assert.equal(statusLoads, 2);
});

test("dismissing the Spark discovery hint restores focus to a current sheet control", async () => {
  const dom = createSparkDom();
  const { createSparkController } = await import("../../assets/nova_companion/companion-spark.js");
  const controller = createSparkController({ ...dom });

  await controller.open();
  const dismiss = buttonsIn(dom.host).find((item) => item.textContent === "Got it");
  assert.ok(dismiss);
  dismiss.dispatch("click");
  assert.notEqual(dom.document.activeElement, dismiss);
  assert.ok(buttonsIn(dom.host).includes(dom.document.activeElement));
});
