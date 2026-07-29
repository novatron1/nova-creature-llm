import assert from "node:assert/strict";
import test from "node:test";

import {
  createSelectedPictureVisionSubmitter,
  resolveVisionFocusRestoreTarget,
  stopVoiceAndActiveRequest,
} from "../../assets/nova_companion/companion-app.js";

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
