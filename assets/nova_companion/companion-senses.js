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
  if (!api?.chat) {
    throw new TypeError("Nova vision requires the Companion API.");
  }
  let camera = visionStateAfter({ ...defaultVisionState, facingMode }, { type: "CAMERA_STOPPED" });
  let stream = null;
  const emit = () => onStateChange({ ...camera });
  const stopCamera = () => {
    stopTracks(stream);
    stream = null;
    if (preview) preview.srcObject = null;
    const context = previewCanvas?.getContext?.("2d");
    context?.clearRect?.(0, 0, previewCanvas.width || 0, previewCanvas.height || 0);
    camera = visionStateAfter(camera, { type: "CAMERA_STOPPED" });
    emit();
    return camera;
  };
  const openStream = async () => {
    if (!mediaDevices?.getUserMedia) throw new TypeError("Camera access is not supported by this browser.");
    const next = await mediaDevices.getUserMedia({ video: { facingMode: camera.facingMode }, audio: false });
    if (!hasLiveVideoTrack(next)) {
      stopTracks(next);
      throw new TypeError("The camera did not provide a live video track.");
    }
    stream = next;
    if (preview) preview.srcObject = stream;
    camera = visionStateAfter(camera, { type: "CAMERA_STREAM_LIVE" });
    emit();
    return camera;
  };
  return {
    getState: () => ({ ...camera }),
    async enableCamera() {
      if (camera.active) return { ...camera };
      try {
        const permission = await api.chat({ text: "allow camera" });
        if (permission?.permissions?.camera === false) {
          camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_DENIED" });
          emit();
          return { ...camera };
        }
        camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_GRANTED" });
        emit();
        return await openStream();
      } catch (error) {
        camera = visionStateAfter(camera, { type: "CAMERA_PERMISSION_DENIED" });
        emit();
        throw error;
      }
    },
    async changeFacingMode(nextFacingMode) {
      const requested = nextFacingMode === "user" ? "user" : "environment";
      stopCamera();
      camera = visionStateAfter(camera, { type: "CAMERA_FACING_CHANGED", facingMode: requested });
      emit();
      if (camera.permission === "granted") return openStream();
      return { ...camera };
    },
    async look(prompt = "What is in front of me?") {
      if (!camera.active || !stream) throw new TypeError("Enable a live camera before asking Nova to look.");
      if (typeof api.postVision !== "function") throw new TypeError("Nova vision requires the Companion API.");
      const width = Number(preview?.videoWidth) || 0;
      const height = Number(preview?.videoHeight) || 0;
      if (!previewCanvas?.getContext || !width || !height) throw new TypeError("The live camera frame is not ready yet.");
      previewCanvas.width = width;
      previewCanvas.height = height;
      const context = previewCanvas.getContext("2d", { alpha: false });
      if (!context?.drawImage) throw new TypeError("This browser cannot capture the live camera frame.");
      context.drawImage(preview, 0, 0, width, height);
      const frame = await prepareFrame(previewCanvas, { filename: "camera-frame.jpg" });
      const result = await api.postVision(buildVisionPayload(frame, prompt));
      onResult(result);
      return result;
    },
    stopCamera,
    destroy: stopCamera,
  };
}
