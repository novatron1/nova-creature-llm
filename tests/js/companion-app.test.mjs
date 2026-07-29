import assert from "node:assert/strict";
import test from "node:test";

import { resolveVisionFocusRestoreTarget } from "../../assets/nova_companion/companion-app.js";

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
