const ACCEPTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

export const VISION_MAX_EDGE = 1280;
export const VISION_JPEG_QUALITY = 0.82;
export const VISION_MAX_ENCODED_BYTES = 6_000_000;

const defaultVisionState = Object.freeze({
  permission: "unknown",
  active: false,
  persisted: false,
  facingMode: "environment",
});

function normalizedVisionState(state) {
  return { ...defaultVisionState, ...(state || {}) };
}

export function visionStateAfter(stateOrEvent = {}, maybeEvent) {
  const hasEventArgument = maybeEvent !== undefined;
  const state = normalizedVisionState(hasEventArgument ? stateOrEvent : {});
  const event = hasEventArgument ? maybeEvent : stateOrEvent;
  switch (String(event?.type || "")) {
    case "CAMERA_PERMISSION_GRANTED":
      return { ...state, permission: "granted", active: false };
    case "CAMERA_PERMISSION_DENIED":
      return { ...state, permission: "denied", active: false };
    case "CAMERA_STREAM_LIVE":
      return { ...state, permission: "granted", active: true };
    case "CAMERA_STOPPED":
      return { ...state, active: false };
    case "CAMERA_FACING_CHANGED":
      return { ...state, facingMode: event.facingMode === "user" ? "user" : "environment", active: false };
    default:
      return state;
  }
}

export function buildVisionPayload(frame = {}, prompt = "") {
  const mimeType = String(frame.mimeType || frame.mime_type || "").toLowerCase();
  if (!ACCEPTED_IMAGE_TYPES.has(mimeType)) throw new TypeError("Nova can inspect JPEG, PNG, or WebP pictures.");
  const width = Number(frame.width) || 0;
  const height = Number(frame.height) || 0;
  return {
    filename: String(frame.filename || "picture.jpg"),
    mime_type: mimeType,
    image_base64: String(frame.imageBase64 || frame.image_base64 || ""),
    prompt: String(prompt || "").trim().slice(0, 500),
    persist: false,
    client_processing: {
      resized: Boolean(frame.resized),
      width,
      height,
      source_width: Number(frame.sourceWidth || frame.source_width) || width,
      source_height: Number(frame.sourceHeight || frame.source_height) || height,
      cropped: false,
      enhanced: false,
      picture_quality: VISION_JPEG_QUALITY,
    },
  };
}

function canvasFor(width, height, canvasFactory) {
  const canvas = canvasFactory?.(width, height) || globalThis.document?.createElement?.("canvas");
  if (!canvas?.getContext || !canvas?.toDataURL) throw new TypeError("This browser cannot prepare a local picture frame.");
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

function dataUrlBase64(value) {
  const match = /^data:image\/jpeg;base64,([a-z0-9+/=]+)$/i.exec(String(value || ""));
  if (!match) throw new TypeError("The browser could not encode a local JPEG frame.");
  return match[1];
}

function base64Bytes(base64) {
  const padding = String(base64 || "").match(/=+$/)?.[0].length || 0;
  return Math.max(0, Math.floor(String(base64 || "").length * 0.75) - padding);
}

function dimensionsFor(width, height, maxEdge) {
  const longestEdge = Math.max(width, height);
  if (longestEdge <= maxEdge) return { width, height, resized: false };
  const scale = maxEdge / longestEdge;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)), resized: true };
}

async function decodedImageFor(source, createImageBitmapImpl) {
  if (source?.videoWidth && source?.videoHeight) return source;
  if (source?.naturalWidth && source?.naturalHeight) return source;
  if (source?.width && source?.height && source?.getContext) return source;
  const decode = createImageBitmapImpl || globalThis.createImageBitmap;
  if (typeof decode !== "function") throw new TypeError("This browser cannot decode the selected picture.");
  return decode(source);
}

export async function prepareVisionCanvas(source, {
  createImageBitmap: createImageBitmapImpl,
  canvasFactory,
  maxEdge = VISION_MAX_EDGE,
  maxEncodedBytes = VISION_MAX_ENCODED_BYTES,
  filename = String(source?.name || "picture.jpg"),
} = {}) {
  const sourceMimeType = String(source?.type || "image/jpeg").toLowerCase();
  if (!ACCEPTED_IMAGE_TYPES.has(sourceMimeType)) throw new TypeError("Nova can inspect JPEG, PNG, or WebP pictures.");
  const decoded = await decodedImageFor(source, createImageBitmapImpl);
  const sourceWidth = Number(decoded?.videoWidth || decoded?.naturalWidth || decoded?.width) || 0;
  const sourceHeight = Number(decoded?.videoHeight || decoded?.naturalHeight || decoded?.height) || 0;
  if (!sourceWidth || !sourceHeight) throw new TypeError("The selected picture has no usable dimensions.");
  let target = dimensionsFor(sourceWidth, sourceHeight, Math.max(1, Number(maxEdge) || VISION_MAX_EDGE));
  let encoded = "";
  try {
    while (true) {
      const canvas = canvasFor(target.width, target.height, canvasFactory);
      const context = canvas.getContext("2d", { alpha: false });
      if (!context?.drawImage) throw new TypeError("This browser cannot draw a local picture frame.");
      context.drawImage(decoded, 0, 0, target.width, target.height);
      encoded = dataUrlBase64(canvas.toDataURL("image/jpeg", VISION_JPEG_QUALITY));
      if (base64Bytes(encoded) <= maxEncodedBytes) break;
      if (target.width <= 1 || target.height <= 1) throw new RangeError("The processed picture is still too large for Nova's vision route.");
      target = {
        width: Math.max(1, Math.floor(target.width * 0.8)),
        height: Math.max(1, Math.floor(target.height * 0.8)),
        resized: true,
      };
    }
  } finally {
    decoded?.close?.();
  }
  return {
    filename,
    mimeType: "image/jpeg",
    imageBase64: encoded,
    width: target.width,
    height: target.height,
    sourceWidth,
    sourceHeight,
    resized: target.resized,
  };
}

function hasLiveVideoTrack(stream) {
  return Boolean(stream?.getVideoTracks?.().some((track) => track?.readyState === "live"));
}

function stopTracks(stream) {
  for (const track of stream?.getTracks?.() || []) track?.stop?.();
}

export function createVisionController({
  api,
  mediaDevices = globalThis.navigator?.mediaDevices,
  preview = null,
  previewCanvas = null,
  onStateChange = () => {},
  onResult = () => {},
  prepareFrame = prepareVisionCanvas,
  facingMode = "environment",
} = {}) {
  if (!api?.postPermissionCommand) {
    throw new TypeError("Nova vision requires the Companion API.");
  }
  let camera = visionStateAfter({ ...defaultVisionState, facingMode }, { type: "CAMERA_STOPPED" });
  let stream = null;
  let operation = 0;
  let pendingEnable = null;
  let permissionAbort = null;
  let visionAbort = null;
  let destroyed = false;
  const emit = () => onStateChange({ ...camera });
  const isCurrent = (token) => !destroyed && token === operation;
  const abortPendingWork = () => {
    permissionAbort?.abort();
    permissionAbort = null;
    visionAbort?.abort();
    visionAbort = null;
  };
  const stopCamera = () => {
    operation += 1;
    pendingEnable = null;
    abortPendingWork();
    stopTracks(stream);
    stream = null;
    if (preview) preview.srcObject = null;
    const context = previewCanvas?.getContext?.("2d");
    context?.clearRect?.(0, 0, previewCanvas.width || 0, previewCanvas.height || 0);
    camera = visionStateAfter(camera, { type: "CAMERA_STOPPED" });
    emit();
    return camera;
  };
  const openStream = async (token) => {
    if (!mediaDevices?.getUserMedia) throw new TypeError("Camera access is not supported by this browser.");
    const next = await mediaDevices.getUserMedia({ video: { facingMode: camera.facingMode }, audio: false });
    if (!isCurrent(token)) {
      stopTracks(next);
      return { ...camera };
    }
    if (!hasLiveVideoTrack(next)) {
      stopTracks(next);
      throw new TypeError("The camera did not provide a live video track.");
    }
    stopTracks(stream);
    stream = next;
    if (preview) preview.srcObject = stream;
    camera = visionStateAfter(camera, { type: "CAMERA_STREAM_LIVE" });
    emit();
    return camera;
  };
  return {
    getState: () => ({ ...camera }),
    enableCamera() {
      if (destroyed || camera.active) return Promise.resolve({ ...camera });
      if (pendingEnable) return pendingEnable;
      const token = ++operation;
      const controller = new AbortController();
      permissionAbort = controller;
      let request;
      request = Promise.resolve().then(async () => {
        try {
          const permission = await api.postPermissionCommand("allow camera", { signal: controller.signal });
          if (!isCurrent(token)) return { ...camera };
          if (permission?.permissions?.camera === false) {
            camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_DENIED" });
            emit();
            return { ...camera };
          }
          camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_GRANTED" });
          emit();
          return await openStream(token);
        } catch (error) {
          if (!isCurrent(token)) return { ...camera };
          camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_DENIED" });
          emit();
          throw error;
        } finally {
          if (pendingEnable === request) pendingEnable = null;
          if (permissionAbort === controller) permissionAbort = null;
        }
      });
      pendingEnable = request;
      return request;
    },
    async changeFacingMode(nextFacingMode) {
      const requested = nextFacingMode === "user" ? "user" : "environment";
      stopCamera();
      camera = visionStateAfter(camera, { type: "CAMERA_FACING_CHANGED", facingMode: requested });
      emit();
      if (destroyed) return { ...camera };
      if (camera.permission === "granted") return openStream(++operation);
      return { ...camera };
    },
    async look(prompt = "What is in front of me?") {
      if (!camera.active || !stream) throw new TypeError("Enable a live camera before asking Nova to look.");
      if (typeof api.postVision !== "function") throw new TypeError("Nova vision requires the Companion API.");
      visionAbort?.abort();
      const token = operation;
      const controller = new AbortController();
      visionAbort = controller;
      const width = Number(preview?.videoWidth) || 0;
      const height = Number(preview?.videoHeight) || 0;
      if (!previewCanvas?.getContext || !width || !height) throw new TypeError("The live camera frame is not ready yet.");
      previewCanvas.width = width;
      previewCanvas.height = height;
      const context = previewCanvas.getContext("2d", { alpha: false });
      if (!context?.drawImage) throw new TypeError("This browser cannot capture the live camera frame.");
      context.drawImage(preview, 0, 0, width, height);
      const frame = await prepareFrame(previewCanvas, { filename: "camera-frame.jpg" });
      if (!isCurrent(token) || controller.signal.aborted) return null;
      try {
        const result = await api.postVision(buildVisionPayload(frame, prompt), { signal: controller.signal });
        if (!isCurrent(token) || controller.signal.aborted) return null;
        onResult(result);
        return result;
      } finally {
        if (visionAbort === controller) visionAbort = null;
      }
    },
    stopCamera,
    destroy() {
      destroyed = true;
      return stopCamera();
    },
  };
}

const VOICE_UNAVAILABLE_REASON = "Speech recognition is unavailable in this browser.";
export const VOICE_RECOGNITION_START_TIMEOUT_MS = 8_000;
const MICROPHONE_START_TIMEOUT_MESSAGE = "Microphone did not start. Check browser permission and try again.";

const RECOGNITION_ERRORS = Object.freeze({
  "not-allowed": "Microphone permission was not granted.",
  "audio-capture": "No microphone is available.",
  "no-speech": "Nova did not hear speech. Try again.",
  network: "Speech recognition network service is unavailable.",
});

function recognitionConstructor(windowLike) {
  return windowLike?.SpeechRecognition || windowLike?.webkitSpeechRecognition || null;
}

export function voiceAvailability(windowLike = globalThis, { ttsAvailable = false, audioAvailable = typeof windowLike?.Audio === "function" } = {}) {
  const Recognition = recognitionConstructor(windowLike);
  const transcription = typeof Recognition === "function";
  const playback = Boolean(audioAvailable) && Boolean(ttsAvailable);
  return Object.freeze({
    transcription,
    playback,
    reason: transcription ? "" : VOICE_UNAVAILABLE_REASON,
    outputReason: !audioAvailable
      ? "Audio playback is unavailable in this browser."
      : playback ? "" : "Nova voice output is unavailable.",
  });
}

function recognitionErrorMessage(error) {
  return RECOGNITION_ERRORS[String(error?.error || "")] || "Speech recognition could not start.";
}

function transcriptFor(resultEvent) {
  const parts = [];
  const interim = [];
  const results = resultEvent?.results || [];
  for (let index = Number(resultEvent?.resultIndex) || 0; index < results.length; index += 1) {
    const item = results[index];
    const text = String(item?.[0]?.transcript || "").trim();
    if (!text) continue;
    (item.isFinal ? parts : interim).push(text);
  }
  return { finalText: parts.join(" ").trim(), interimText: interim.join(" ").trim() };
}

function audioSource(tts = {}) {
  const mimeType = String(tts?.mime_type || "audio/mpeg").trim() || "audio/mpeg";
  const audioBase64 = String(tts?.audio_base64 || "").trim();
  if (!audioBase64) throw new TypeError("Nova did not return playable voice audio.");
  return `data:${mimeType};base64,${audioBase64}`;
}

export function createVoiceController({
  windowLike = globalThis,
  api = null,
  ttsAvailable = false,
  dispatch = () => {},
  audioFactory = null,
  onTranscript = () => {},
  onInterimTranscript = () => {},
  recognitionStartTimeoutMs = VOICE_RECOGNITION_START_TIMEOUT_MS,
  setTimeout: setTimeoutImpl = globalThis.setTimeout,
  clearTimeout: clearTimeoutImpl = globalThis.clearTimeout,
} = {}) {
  let recognition = null;
  let recognitionStartWatchdog = null;
  let listening = false;
  let audioRecord = null;
  let playbackOperation = 0;
  let ttsAbort = null;
  let destroyed = false;
  const resolvedAudioFactory = audioFactory || (typeof windowLike?.Audio === "function" ? (source) => new windowLike.Audio(source) : null);
  const availability = voiceAvailability(windowLike, { ttsAvailable, audioAvailable: typeof resolvedAudioFactory === "function" });
  const emit = (event) => dispatch(event);
  const clearRecognitionStartWatchdog = (engine = null) => {
    if (!recognitionStartWatchdog || (engine && recognitionStartWatchdog.engine !== engine)) return;
    clearTimeoutImpl?.(recognitionStartWatchdog.timer);
    recognitionStartWatchdog = null;
  };
  const armRecognitionStartWatchdog = (engine) => {
    clearRecognitionStartWatchdog();
    const timeout = Math.max(0, Number(recognitionStartTimeoutMs) || 0);
    if (!timeout || typeof setTimeoutImpl !== "function") return;
    const timer = setTimeoutImpl(() => {
      if (!destroyed && recognition === engine) finishRecognition(engine, { failure: MICROPHONE_START_TIMEOUT_MESSAGE, abort: true });
    }, timeout);
    recognitionStartWatchdog = { engine, timer };
  };
  const currentPlayback = (record) => !destroyed && audioRecord === record && record.token === playbackOperation && !record.finished;
  const clearAudio = (record) => {
    const audio = record?.audio || record;
    if (!audio) return;
    audio.pause?.();
    audio.removeAttribute?.("src");
    audio.src = "";
    audio.load?.();
  };
  const finishAudio = (record, event) => {
    if (!currentPlayback(record)) return false;
    record.finished = true;
    audioRecord = null;
    clearAudio(record);
    emit(event);
    return true;
  };
  const stopAudio = () => {
    if (audioRecord) finishAudio(audioRecord, { type: "SPEECH_STOPPED" });
  };
  const attachAudio = (nextAudio, token = playbackOperation) => {
    stopAudio();
    if (!nextAudio) return null;
    const record = { audio: nextAudio, token, finished: false, started: false };
    audioRecord = record;
    nextAudio.addEventListener?.("play", () => {
      if (currentPlayback(record) && !record.started) {
        record.started = true;
        emit({ type: "SPEECH_STARTED" });
      }
    });
    nextAudio.addEventListener?.("ended", () => {
      finishAudio(record, { type: "SPEECH_FINISHED" });
    });
    nextAudio.addEventListener?.("error", () => {
      finishAudio(record, { type: "SPEECH_FAILED", message: "Nova voice playback failed." });
    });
    return nextAudio;
  };
  const finishRecognition = (engine, { failure = null, abort = false } = {}) => {
    if (recognition !== engine) return false;
    clearRecognitionStartWatchdog(engine);
    recognition = null;
    const wasListening = listening;
    listening = false;
    if (abort) engine.abort?.();
    if (failure) emit({ type: "LISTENING_FAILED", message: failure });
    if (wasListening || failure) emit({ type: "LISTENING_STOPPED" });
    return true;
  };
  const stopRecognition = () => {
    if (!recognition) return false;
    return finishRecognition(recognition, { abort: true });
  };
  const stop = () => {
    ttsAbort?.abort();
    ttsAbort = null;
    stopRecognition();
    stopAudio();
    playbackOperation += 1;
  };
  return {
    availability,
    getAvailability: () => availability,
    attachAudio,
    startListening() {
      if (destroyed || !availability.transcription) {
        emit({ type: "LISTENING_UNAVAILABLE", message: availability.reason });
        return false;
      }
      if (recognition) return true;
      const Recognition = recognitionConstructor(windowLike);
      const engine = new Recognition();
      recognition = engine;
      engine.continuous = false;
      engine.interimResults = true;
      engine.onstart = () => {
        if (!destroyed && recognition === engine) {
          clearRecognitionStartWatchdog(engine);
          listening = true;
          emit({ type: "LISTENING_STARTED" });
        }
      };
      engine.onresult = (event) => {
        if (destroyed || recognition !== engine) return;
        const { finalText, interimText } = transcriptFor(event);
        if (interimText) {
          onInterimTranscript(interimText);
          emit({ type: "LISTENING_INTERIM", text: interimText });
        }
        if (finalText) {
          onTranscript(finalText);
          emit({ type: "LISTENING_FINAL", text: finalText });
        }
      };
      engine.onerror = (event) => {
        finishRecognition(engine, { failure: recognitionErrorMessage(event) });
      };
      engine.onend = () => {
        finishRecognition(engine);
      };
      try {
        armRecognitionStartWatchdog(engine);
        engine.start();
        return true;
      } catch (error) {
        finishRecognition(engine, { failure: recognitionErrorMessage(error) });
        return false;
      }
    },
    async speak(text) {
      const spokenText = String(text || "").trim();
      if (!spokenText || destroyed || !availability.playback || typeof api?.postTts !== "function") {
        if (spokenText && !destroyed) emit({ type: "SPEECH_UNAVAILABLE", message: availability.outputReason || "Nova voice output is unavailable." });
        return null;
      }
      stopRecognition();
      ttsAbort?.abort();
      stopAudio();
      const token = ++playbackOperation;
      const controller = new AbortController();
      ttsAbort = controller;
      try {
        const tts = await api.postTts(spokenText, { signal: controller.signal });
        if (destroyed || token !== playbackOperation || controller.signal.aborted) return null;
        const nextAudio = attachAudio(resolvedAudioFactory(audioSource(tts)), token);
        const record = audioRecord;
        const playback = nextAudio?.play?.();
        if (playback?.catch) {
          playback.catch(() => {
            finishAudio(record, { type: "SPEECH_FAILED", message: "Nova voice playback could not start." });
          });
        }
        return nextAudio;
      } catch (error) {
        if (!destroyed && token === playbackOperation && !controller.signal.aborted) emit({ type: "SPEECH_FAILED", message: "Nova voice playback failed." });
        return null;
      } finally {
        if (ttsAbort === controller) ttsAbort = null;
      }
    },
    stop,
    destroy() {
      stop();
      destroyed = true;
    },
  };
}
