import assert from "node:assert/strict";
import test from "node:test";

import {
  buildVisionPayload,
  createVisionController,
  prepareVisionCanvas,
  visionStateAfter,
} from "../../assets/nova_companion/companion-senses.js";

test("vision payload declares local preprocessing and no persistence", () => {
  const payload = buildVisionPayload(
    { filename: "camera-frame.jpg", mimeType: "image/jpeg", imageBase64: "abc", width: 640, height: 480, resized: true },
    "What is in front of me?"
  );
  assert.equal(payload.mime_type, "image/jpeg");
  assert.equal(payload.client_processing.width, 640);
  assert.equal(payload.client_processing.height, 480);
  assert.equal(payload.client_processing.resized, true);
  assert.equal(payload.persist, false);
});

test("camera state is not active before a stream exists", () => {
  const state = visionStateAfter({ type: "CAMERA_PERMISSION_GRANTED" });
  assert.equal(state.active, false);
  assert.equal(state.permission, "granted");
});

test("picture preprocessing uses a bounded local JPEG frame", async () => {
  const draws = [];
  const frame = await prepareVisionCanvas({ type: "image/png", name: "phone.png" }, {
    createImageBitmap: async () => ({ width: 2000, height: 1500, close() {} }),
    canvasFactory: (width, height) => ({
      width,
      height,
      getContext: () => ({ drawImage: (...args) => draws.push(args) }),
      toDataURL: (mime, quality) => `data:${mime};base64,abc`,
    }),
  });
  assert.equal(frame.mimeType, "image/jpeg");
  assert.equal(frame.width, 1280);
  assert.equal(frame.height, 960);
  assert.equal(frame.sourceWidth, 2000);
  assert.equal(frame.sourceHeight, 1500);
  assert.equal(frame.resized, true);
  assert.equal(frame.imageBase64, "abc");
  assert.deepEqual(draws[0].slice(-2), [1280, 960]);
});

test("camera becomes active only after Nova permission and a live video track", async () => {
  const calls = [];
  const liveTrack = { readyState: "live", stop() { calls.push("track.stop"); } };
  const controller = createVisionController({
    api: { chat: async (body) => { calls.push(body.text); return {}; } },
    mediaDevices: { getUserMedia: async (constraints) => {
      calls.push(constraints);
      return { getVideoTracks: () => [liveTrack], getTracks: () => [liveTrack] };
    } },
  });
  assert.equal(controller.getState().active, false);
  await controller.enableCamera();
  assert.equal(calls[0], "allow camera");
  assert.deepEqual(calls[1], { video: { facingMode: "environment" }, audio: false });
  assert.equal(controller.getState().active, true);
});

test("stopping camera ends every track and clears the preview", async () => {
  const tracks = [{ readyState: "live", stopped: false, stop() { this.stopped = true; } }];
  const preview = { srcObject: { stale: true } };
  const controller = createVisionController({
    api: { chat: async () => ({}) },
    preview,
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => tracks, getTracks: () => tracks }) },
  });
  await controller.enableCamera();
  controller.stopCamera();
  assert.equal(tracks[0].stopped, true);
  assert.equal(preview.srcObject, null);
  assert.equal(controller.getState().active, false);
});

test("Look captures the live preview into an ephemeral canvas before posting vision", async () => {
  const draws = [];
  const posted = [];
  const preview = { videoWidth: 640, videoHeight: 480, srcObject: null };
  const previewCanvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: (...args) => draws.push(args), clearRect() {} }),
  };
  const liveTrack = { readyState: "live", stop() {} };
  const controller = createVisionController({
    api: { chat: async () => ({}), postVision: async (body) => { posted.push(body); return { ok: true }; } },
    preview,
    previewCanvas,
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [liveTrack], getTracks: () => [liveTrack] }) },
    prepareFrame: async (source) => {
      assert.equal(source, previewCanvas);
      return { filename: "camera-frame.jpg", mimeType: "image/jpeg", imageBase64: "abc", width: 640, height: 480 };
    },
  });
  await controller.enableCamera();
  await controller.look("Read the label");
  assert.equal(previewCanvas.width, 640);
  assert.equal(previewCanvas.height, 480);
  assert.deepEqual(draws[0].slice(0, 1), [preview]);
  assert.equal(posted[0].prompt, "Read the label");
  assert.equal(posted[0].persist, false);
});
