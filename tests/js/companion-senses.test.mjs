import assert from "node:assert/strict";
import test from "node:test";

import {
  buildVisionPayload,
  createVisionController,
  createVoiceController,
  prepareVisionCanvas,
  visionStateAfter,
  voiceAvailability,
} from "../../assets/nova_companion/companion-senses.js";

const deferred = () => {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
};

function makeFakeAudio() {
  const listeners = new Map();
  return {
    src: "",
    paused: false,
    addEventListener(type, listener) { listeners.set(type, listener); },
    removeEventListener(type, listener) { if (listeners.get(type) === listener) listeners.delete(type); },
    emit(type) { listeners.get(type)?.(); },
    pause() { this.paused = true; },
    load() {},
    play() { return Promise.resolve(); },
  };
}

test("unsupported recognition never reports listening", () => {
  const availability = voiceAvailability({});
  assert.equal(availability.transcription, false);
  assert.equal(availability.reason, "Speech recognition is unavailable in this browser.");
  const events = [];
  const controller = createVoiceController({ windowLike: {}, dispatch: (event) => events.push(event) });
  controller.startListening();
  assert.equal(events.some((event) => event.type === "LISTENING_STARTED"), false);
  assert.equal(events.at(-1).type, "LISTENING_UNAVAILABLE");
});

test("recognition reports listening only after the browser engine starts", () => {
  let recognition;
  class FakeRecognition {
    start() {}
    abort() {}
  }
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class extends FakeRecognition { constructor() { super(); recognition = this; } } },
    dispatch: (event) => events.push(event),
  });
  controller.startListening();
  assert.equal(events.some((event) => event.type === "LISTENING_STARTED"), false);
  recognition.onstart();
  assert.equal(events.at(-1).type, "LISTENING_STARTED");
});

test("recognition errors use safe distinct microphone messages and end listening", () => {
  let recognition;
  class FakeRecognition {
    start() {}
    abort() {}
  }
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { recognition = new FakeRecognition(); return recognition; } } },
    dispatch: (event) => events.push(event),
  });
  controller.startListening();
  recognition.onerror({ error: "audio-capture" });
  recognition.onend();
  assert.equal(events.find((event) => event.type === "LISTENING_FAILED").message, "No microphone is available.");
  assert.equal(events.at(-1).type, "LISTENING_STOPPED");
});

test("audio is speaking only after the play event", () => {
  const events = [];
  const controller = createVoiceController({ dispatch: (event) => events.push(event), audioFactory: makeFakeAudio });
  const audio = makeFakeAudio();
  controller.attachAudio(audio);
  assert.equal(events.some((event) => event.type === "SPEECH_STARTED"), false);
  audio.emit("play");
  assert.equal(events.at(-1).type, "SPEECH_STARTED");
});

test("Stop invalidates recognition and audio callbacks", () => {
  let recognition;
  class FakeRecognition {
    start() {}
    abort() {}
  }
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { recognition = new FakeRecognition(); return recognition; } } },
    dispatch: (event) => events.push(event),
  });
  const audio = makeFakeAudio();
  controller.attachAudio(audio);
  controller.startListening();
  controller.stop();
  recognition.onstart();
  audio.emit("play");
  assert.equal(events.some((event) => event.type === "LISTENING_STARTED" || event.type === "SPEECH_STARTED"), false);
  assert.equal(audio.paused, true);
  assert.equal(audio.src, "");
});

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
    api: { postPermissionCommand: async (text) => { calls.push(text); return {}; } },
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
    api: { postPermissionCommand: async () => ({}) },
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
    api: { postPermissionCommand: async () => ({}), postVision: async (body) => { posted.push(body); return { ok: true }; } },
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

test("camera permission uses the Companion /api/chat command contract", async () => {
  const calls = [];
  const liveTrack = { readyState: "live", stop() {} };
  const controller = createVisionController({
    api: { postPermissionCommand: async (text, options) => { calls.push({ text, options }); return {}; } },
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [liveTrack], getTracks: () => [liveTrack] }) },
  });
  await controller.enableCamera();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].text, "allow camera");
  assert.ok(calls[0].options.signal instanceof AbortSignal);
});

test("Stop invalidates a pending permission command before browser camera access", async () => {
  const permission = deferred();
  let mediaRequests = 0;
  const controller = createVisionController({
    api: { postPermissionCommand: () => permission.promise },
    mediaDevices: { getUserMedia: async () => { mediaRequests += 1; return null; } },
  });
  const enable = controller.enableCamera();
  controller.stopCamera();
  permission.resolve({});
  await enable;
  assert.equal(mediaRequests, 0);
  assert.equal(controller.getState().active, false);
});

test("Stop immediately ends a stream that resolves after getUserMedia was invalidated", async () => {
  const media = deferred();
  const track = { readyState: "live", stopped: false, stop() { this.stopped = true; } };
  const controller = createVisionController({
    api: { postPermissionCommand: async () => ({}) },
    mediaDevices: { getUserMedia: () => media.promise },
  });
  const enable = controller.enableCamera();
  await new Promise((resolve) => setImmediate(resolve));
  controller.stopCamera();
  media.resolve({ getVideoTracks: () => [track], getTracks: () => [track] });
  await enable;
  assert.equal(track.stopped, true);
  assert.equal(controller.getState().active, false);
});

test("repeated Enable taps share one pending camera operation", async () => {
  const permission = deferred();
  let permissionCalls = 0;
  const track = { readyState: "live", stop() {} };
  const controller = createVisionController({
    api: { postPermissionCommand: () => { permissionCalls += 1; return permission.promise; } },
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [track], getTracks: () => [track] }) },
  });
  const first = controller.enableCamera();
  const second = controller.enableCamera();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(permissionCalls, 1);
  permission.resolve({});
  await Promise.all([first, second]);
  assert.equal(controller.getState().active, true);
});

test("a synchronous permission failure releases the Enable operation for retry", async () => {
  let calls = 0;
  const track = { readyState: "live", stop() {} };
  const controller = createVisionController({
    api: { postPermissionCommand: () => {
      calls += 1;
      if (calls === 1) throw new Error("offline");
      return {};
    } },
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [track], getTracks: () => [track] }) },
  });
  await assert.rejects(() => controller.enableCamera(), /offline/);
  await controller.enableCamera();
  assert.equal(calls, 2);
  assert.equal(controller.getState().active, true);
});

test("camera switch wins a race with an earlier pending enable", async () => {
  const firstMedia = deferred();
  const secondMedia = deferred();
  const oldTrack = { readyState: "live", stopped: false, stop() { this.stopped = true; } };
  const newTrack = { readyState: "live", stopped: false, stop() { this.stopped = true; } };
  let mediaCalls = 0;
  const controller = createVisionController({
    api: { postPermissionCommand: async () => ({}) },
    mediaDevices: { getUserMedia: () => (++mediaCalls === 1 ? firstMedia.promise : secondMedia.promise) },
  });
  const enable = controller.enableCamera();
  await new Promise((resolve) => setImmediate(resolve));
  const switched = controller.changeFacingMode("user");
  firstMedia.resolve({ getVideoTracks: () => [oldTrack], getTracks: () => [oldTrack] });
  secondMedia.resolve({ getVideoTracks: () => [newTrack], getTracks: () => [newTrack] });
  await Promise.all([enable, switched]);
  assert.equal(oldTrack.stopped, true);
  assert.equal(newTrack.stopped, false);
  assert.deepEqual(controller.getState(), { permission: "granted", active: true, persisted: false, facingMode: "user" });
});

test("Stop suppresses a late vision result and aborts the request when supported", async () => {
  const result = deferred();
  const track = { readyState: "live", stop() {} };
  const preview = { videoWidth: 640, videoHeight: 480, srcObject: null };
  const previewCanvas = { width: 0, height: 0, getContext: () => ({ drawImage() {}, clearRect() {} }) };
  let received = 0;
  const controller = createVisionController({
    api: {
      postPermissionCommand: async () => ({}),
      postVision: (_body, options) => {
        assert.ok(options.signal instanceof AbortSignal);
        return result.promise;
      },
    },
    preview,
    previewCanvas,
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [track], getTracks: () => [track] }) },
    prepareFrame: async () => ({ filename: "camera-frame.jpg", mimeType: "image/jpeg", imageBase64: "abc", width: 640, height: 480 }),
    onResult: () => { received += 1; },
  });
  await controller.enableCamera();
  const look = controller.look();
  controller.stopCamera();
  result.resolve({ ok: true, response: "stale" });
  await look;
  assert.equal(received, 0);
});

test("closing then reopening a vision session cannot deliver the prior deferred result", async () => {
  const result = deferred();
  const received = [];
  const track = { readyState: "live", stop() {} };
  const preview = { videoWidth: 640, videoHeight: 480, srcObject: null };
  const canvas = { width: 0, height: 0, getContext: () => ({ drawImage() {}, clearRect() {} }) };
  const options = {
    api: {
      postPermissionCommand: async () => ({}),
      postVision: () => result.promise,
    },
    preview,
    previewCanvas: canvas,
    mediaDevices: { getUserMedia: async () => ({ getVideoTracks: () => [track], getTracks: () => [track] }) },
    prepareFrame: async () => ({ filename: "camera-frame.jpg", mimeType: "image/jpeg", imageBase64: "abc", width: 640, height: 480 }),
    onResult: (value) => received.push(value.response),
  };
  const first = createVisionController(options);
  await first.enableCamera();
  const oldLook = first.look();
  first.destroy();
  const reopened = createVisionController({ ...options, onResult: (value) => received.push(`new:${value.response}`) });
  assert.equal(reopened.getState().active, false);
  result.resolve({ ok: true, response: "old" });
  await oldLook;
  assert.deepEqual(received, []);
});
