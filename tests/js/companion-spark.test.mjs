import assert from "node:assert/strict";
import test from "node:test";

import {
  COMPANION_CAPABILITIES,
  classicPanelUrl,
  resolveCapabilityAvailability,
  resolveSparkActions,
} from "../../assets/nova_companion/companion-spark.js";

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

test("the fixed registry has visible labels in every approved Spark group", () => {
  const groups = new Set(COMPANION_CAPABILITIES.map((item) => item.group));
  assert.deepEqual(groups, new Set(["see", "speak", "create", "remember", "work", "system"]));
  for (const item of COMPANION_CAPABILITIES) {
    assert.ok(item.label);
    assert.ok(item.description);
    assert.ok(item.requiredPermission);
  }
});
