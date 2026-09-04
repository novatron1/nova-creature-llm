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

function makeFakeAudio(source = "", { rejectPlay = false } = {}) {
  const listeners = new Map();
  return {
    src: source,
    paused: false,
    loads: 0,
    addEventListener(type, listener) { listeners.set(type, listener); },
    removeEventListener(type, listener) { if (listeners.get(type) === listener) listeners.delete(type); },
    emit(type) { listeners.get(type)?.(); },
    pause() { this.paused = true; },
    load() { this.loads += 1; },
    play() { return rejectPlay ? Promise.reject(new Error("autoplay")) : Promise.resolve(); },
  };
}

function createFakeTimers() {
  const timers = [];
  return {
    setTimeout(callback, delay) {
      const timer = { callback, delay, cleared: false };
      timers.push(timer);
      return timer;
    },
    clearTimeout(timer) { if (timer) timer.cleared = true; },
    runAll() {
      for (const timer of timers) if (!timer.cleared) timer.callback();
    },
    activeCount() { return timers.filter((timer) => !timer.cleared).length; },
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

test("a silent microphone start times out without claiming listening and permits retry", () => {
  const timers = createFakeTimers();
  const engines = [];
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { const engine = { start() {}, aborts: 0, abort() { this.aborts += 1; } }; engines.push(engine); return engine; } } },
    dispatch: (event) => events.push(event),
    recognitionStartTimeoutMs: 25,
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
  });
  controller.startListening();
  assert.equal(events.some((event) => event.type === "LISTENING_STARTED"), false);
  assert.equal(timers.activeCount(), 1);
  timers.runAll();
  assert.equal(engines[0].aborts, 1);
  assert.equal(events.at(-2).message, "Microphone did not start. Check browser permission and try again.");
  assert.equal(events.at(-1).type, "LISTENING_STOPPED");
  controller.startListening();
  assert.equal(engines.length, 2);
});

test("real start clears the microphone watchdog and old callbacks cannot revive after retry", () => {
  const timers = createFakeTimers();
  const engines = [];
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { const engine = { start() {}, abort() {} }; engines.push(engine); return engine; } } },
    dispatch: (event) => events.push(event),
    recognitionStartTimeoutMs: 25,
    setTimeout: timers.setTimeout,
    clearTimeout: timers.clearTimeout,
  });
  controller.startListening();
  timers.runAll();
  controller.startListening();
  engines[1].onstart();
  assert.equal(timers.activeCount(), 0);
  engines[0].onstart();
  engines[0].onend();
  assert.equal(events.filter((event) => event.type === "LISTENING_STARTED").length, 1);
  assert.equal(events.filter((event) => event.type === "LISTENING_STOPPED").length, 1);
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

test("recognition maps every documented failure to a distinct safe message", () => {
  const expected = {
    "not-allowed": "Microphone permission was not granted.",
    "audio-capture": "No microphone is available.",
    "no-speech": "Nova did not hear speech. Try again.",
    network: "Speech recognition network service is unavailable.",
    bad: "Speech recognition could not start.",
  };
  for (const [code, message] of Object.entries(expected)) {
    let recognition;
    const events = [];
    const controller = createVoiceController({
      windowLike: { SpeechRecognition: class { constructor() { recognition = { start() {}, abort() {} }; return recognition; } } },
      dispatch: (event) => events.push(event),
    });
    controller.startListening();
    recognition.onerror({ error: code });
    assert.equal(events.at(-1).type, "LISTENING_STOPPED");
    assert.equal(events.at(-2).message, message);
  }
});

test("a final transcript is delivered for normal user review without submission", () => {
  let recognition;
  const transcripts = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { recognition = { start() {}, abort() {} }; return recognition; } } },
    onTranscript: (text) => transcripts.push(text),
  });
  controller.startListening();
  recognition.onresult({ resultIndex: 0, results: [{ isFinal: true, 0: { transcript: "review this first" } }] });
  assert.deepEqual(transcripts, ["review this first"]);
  controller.stop();
});

test("playback stops recognition so an old end event cannot block Talk again", async () => {
  const engines = [];
  const events = [];
  const controller = createVoiceController({
    windowLike: { SpeechRecognition: class { constructor() { const engine = { start() {}, aborts: 0, abort() { this.aborts += 1; } }; engines.push(engine); return engine; } } },
    api: { postTts: async () => ({ mime_type: "audio/mpeg", audio_base64: "AQ==" }) },
    ttsAvailable: true,
    audioFactory: makeFakeAudio,
    dispatch: (event) => events.push(event),
  });
  controller.startListening();
  engines[0].onstart();
  await controller.speak("Nova response");
  assert.equal(engines[0].aborts, 1);
  assert.equal(events.some((event) => event.type === "LISTENING_STOPPED"), true);
  engines[0].onend();
  controller.startListening();
  assert.equal(engines.length, 2);
  engines[1].onstart();
  assert.equal(events.filter((event) => event.type === "LISTENING_STARTED").length, 2);
});

test("audio terminal events clear the same data URL exactly once", async () => {
  const events = [];
  let audio;
  const controller = createVoiceController({
    api: { postTts: async () => ({ mime_type: "audio/mpeg", audio_base64: "AQ==" }) },
    ttsAvailable: true,
    audioFactory: (source) => { audio = makeFakeAudio(source); return audio; },
    dispatch: (event) => events.push(event),
  });
  await controller.speak("Nova response");
  audio.emit("ended");
  audio.emit("ended");
  assert.equal(audio.paused, true);
  assert.equal(audio.src, "");
  assert.equal(audio.loads, 1);
  assert.equal(events.filter((event) => event.type === "SPEECH_FINISHED").length, 1);
});

test("audio error and rejected play clean the data URL and fail once", async () => {
  const events = [];
  const audios = [];
  const controller = createVoiceController({
    api: { postTts: async () => ({ mime_type: "audio/mpeg", audio_base64: "AQ==" }) },
    ttsAvailable: true,
    audioFactory: (source) => { const audio = makeFakeAudio(source, { rejectPlay: audios.length === 1 }); audios.push(audio); return audio; },
    dispatch: (event) => events.push(event),
  });
  await controller.speak("first");
  audios[0].emit("error");
  await controller.speak("second");
  await new Promise((resolve) => setImmediate(resolve));
  for (const audio of audios) {
    assert.equal(audio.paused, true);
    assert.equal(audio.src, "");
    assert.equal(audio.loads, 1);
  }
  assert.equal(events.filter((event) => event.type === "SPEECH_FAILED").length, 2);
});

test("Stop aborts pending TTS and makes its late result inert", async () => {
  const tts = deferred();
  let receivedSignal;
  let audioCalls = 0;
  const controller = createVoiceController({
    api: { postTts: (_text, { signal }) => { receivedSignal = signal; return tts.promise; } },
    ttsAvailable: true,
    audioFactory: () => { audioCalls += 1; return makeFakeAudio(); },
  });
  const speaking = controller.speak("late reply");
  controller.stop();
  tts.resolve({ mime_type: "audio/mpeg", audio_base64: "AQ==" });
  await speaking;
  assert.equal(receivedSignal.aborted, true);
  assert.equal(audioCalls, 0);
});

test("a newer explicit playback cancels a prior TTS request without duplicate audio", async () => {
  const first = deferred();
  const signals = [];
  let audioCalls = 0;
  const controller = createVoiceController({
    api: { postTts: (_text, { signal }) => {
      signals.push(signal);
      return signals.length === 1 ? first.promise : Promise.resolve({ mime_type: "audio/mpeg", audio_base64: "AQ==" });
    } },
    ttsAvailable: true,
    audioFactory: () => { audioCalls += 1; return makeFakeAudio(); },
  });
  const oldPlayback = controller.speak("old");
  await controller.speak("new");
  first.resolve({ mime_type: "audio/mpeg", audio_base64: "AQ==" });
  await oldPlayback;
  assert.equal(signals[0].aborted, true);
  assert.equal(audioCalls, 1);
});

test("a stale rejected play promise cannot stop newer audio", async () => {
  const audios = [];
  let rejectFirst;
  const controller = createVoiceController({
    api: { postTts: async () => ({ mime_type: "audio/mpeg", audio_base64: "AQ==" }) },
    ttsAvailable: true,
    audioFactory: (source) => {
      const audio = makeFakeAudio(source);
      if (audios.length === 0) audio.play = () => new Promise((_resolve, reject) => { rejectFirst = reject; });
      audios.push(audio);
      return audio;
    },
  });
  await controller.speak("first");
  await controller.speak("second");
  rejectFirst(new Error("late autoplay rejection"));
  await new Promise((resolve) => setImmediate(resolve));
  assert.notEqual(audios[1].src, "");
  assert.equal(audios[1].paused, false);
});

test("destroy clears active response audio before making callbacks inert", async () => {
  let audio;
  const controller = createVoiceController({
    api: { postTts: async () => ({ mime_type: "audio/mpeg", audio_base64: "AQ==" }) },
    ttsAvailable: true,
    audioFactory: (source) => { audio = makeFakeAudio(source); return audio; },
  });
  await controller.speak("cleanup");
  controller.destroy();
  assert.equal(audio.src, "");
  assert.equal(audio.loads, 1);
});

test("voice availability reports input and output separately", () => {
  const neither = voiceAvailability({}, { ttsAvailable: true });
  assert.equal(neither.transcription, false);
  assert.equal(neither.playback, false);
  const outputOnly = voiceAvailability({ Audio() {} }, { ttsAvailable: true });
  assert.equal(outputOnly.transcription, false);
  assert.equal(outputOnly.playback, true);
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
