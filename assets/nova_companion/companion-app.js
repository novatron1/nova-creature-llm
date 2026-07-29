import { NovaCompanionApi, NovaApiError, createRequestId } from "./companion-api.js";
import { createInitialCompanionState, reduceCompanionState } from "./companion-store.js";
import { presenceViewModel, renderPresence } from "./companion-presence.js";
import { appendMessage, beginStreamingMessage, appendStreamingDelta } from "./companion-conversation.js";
import { createComposerController } from "./companion-composer.js";
import { createSparkController } from "./companion-spark.js";
import { buildVisionPayload, createVisionController, createVoiceController, prepareVisionCanvas, voiceAvailability } from "./companion-senses.js";
import { createTrustController, trustConnectionLabel } from "./companion-trust.js";

const CLIENT_ID_KEY = "nova_companion_client_id_v1";
const CONVERSATION_ID_KEY = "nova_companion_conversation_id_v1";

function generatedId(prefix) {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${globalThis.crypto.randomUUID()}`;
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

export function acquireBrowserStorage(globalLike = globalThis) {
  try {
    return globalLike?.localStorage || null;
  } catch {
    return null;
  }
}

export function storageValue(storage, key, prefix) {
  try {
    const existing = storage?.getItem(key);
    if (existing) return existing;
    const created = generatedId(prefix);
    storage?.setItem(key, created);
    return created;
  } catch {
    return generatedId(prefix);
  }
}

export function createCompanionIdentity(globalLike = globalThis, {
  clientKey = CLIENT_ID_KEY,
  conversationKey = CONVERSATION_ID_KEY,
} = {}) {
  const storage = acquireBrowserStorage(globalLike);
  return {
    clientId: storageValue(storage, clientKey, "client"),
    conversationId: storageValue(storage, conversationKey, "conversation"),
  };
}

function eventType(event) {
  return String(event?.event_type || event?.type || "");
}

function traceFor(event) {
  return event?.metadata?.trace || event?.trace || {};
}

function markMessageStatus(message, status) {
  if (message) message.dataset.status = status;
}

export function resolveVisionFocusRestoreTarget(invoker, fallback) {
  if (invoker?.isConnected && typeof invoker.focus === "function") return invoker;
  if (fallback?.isConnected && typeof fallback.focus === "function") return fallback;
  return null;
}

export async function stopVoiceAndActiveRequest({ voice, api, requestId } = {}) {
  voice?.stop?.();
  if (requestId) await api?.cancel?.(requestId);
}

export async function loadSparkServerState(api) {
  const [statusResult, capabilitiesResult, toolsResult] = await Promise.allSettled([
    api.getStatus(),
    api.getJson("/nova/v1/capabilities"),
    api.getJson("/nova/v1/tools"),
  ]);
  const freshStatus = statusResult.status === "fulfilled" ? statusResult.value : {};
  const capabilities = capabilitiesResult.status === "fulfilled" ? capabilitiesResult.value : {};
  const toolData = toolsResult.status === "fulfilled" && Array.isArray(toolsResult.value?.data)
    ? toolsResult.value.data
    : [];
  const items = new Map(toolData.map((item) => [String(item?.id || item?.name || ""), item]));
  return { capabilities, items, companion: freshStatus?.companion || {} };
}

export function createSelectedPictureVisionSubmitter({
  api,
  signal,
  isCurrentSheet = () => true,
  cameraIsActive = () => false,
  onStatus = () => {},
  onResult = () => {},
} = {}) {
  if (!api?.postPermissionCommand || !api?.postVision) {
    throw new TypeError("Selected-picture vision requires the Companion API.");
  }
  let permissionGranted = false;
  let pendingPermission = null;
  const sheetIsCurrent = () => isCurrentSheet() && !signal?.aborted;
  const browserCameraStatus = () => (
    cameraIsActive() ? "Browser camera remains live." : "Browser camera remains off."
  );
  const setStatus = (text, isCurrentRequest = () => true) => {
    if (sheetIsCurrent() && isCurrentRequest()) onStatus(text);
  };
  const ensurePermission = () => {
    if (permissionGranted) return Promise.resolve(true);
    if (pendingPermission) return pendingPermission;
    setStatus("Enabling Nova’s local vision permission for this picture. This does not start or change the browser camera.");
    let request;
    request = Promise.resolve()
      .then(() => api.postPermissionCommand("allow camera", { signal }))
      .then((permission) => {
        if (!sheetIsCurrent()) return false;
        if (permission?.permissions?.camera === false) {
          throw new NovaApiError("Nova could not enable local vision permission.", { code: "permission_denied" });
        }
        permissionGranted = true;
        return true;
      })
      .finally(() => {
        if (pendingPermission === request) pendingPermission = null;
      });
    pendingPermission = request;
    return request;
  };
  return {
    async submit(frame, prompt, { isCurrentRequest = () => true } = {}) {
      const current = () => sheetIsCurrent() && isCurrentRequest();
      if (!current()) return null;
      try {
        const permitted = await ensurePermission();
        if (!permitted || !current()) return null;
        setStatus(`Nova is inspecting the picture you chose. ${browserCameraStatus()}`, isCurrentRequest);
        const result = await api.postVision(buildVisionPayload(frame, prompt), { signal });
        if (!current()) return null;
        onResult(result);
        setStatus(
          result?.ok === false
            ? `Nova could not inspect that picture. ${browserCameraStatus()}`
            : `Result added. ${browserCameraStatus()}`,
          isCurrentRequest,
        );
        return result;
      } catch (error) {
        setStatus(`Nova could not inspect that picture. ${browserCameraStatus()}`, isCurrentRequest);
        throw error;
      }
    },
  };
}

function appendCompletionDetails(message, answerStatus, permissions) {
  if (!message) return;
  const document = message.ownerDocument;
  if (!document?.createElement) return;
  if (answerStatus && typeof answerStatus === "object") {
    const answer = document.createElement("p");
    answer.className = "companion-message__answer-status";
    answer.textContent = `Answer safety: ${String(answerStatus.safety || "checked")}`;
    message.appendChild(answer);
  }
  const permissionNames = ["camera", "mic", "microphone", "speaker"];
  const visiblePermissions = permissionNames.filter((name) => typeof permissions?.[name] === "boolean");
  if (visiblePermissions.length) {
    const permission = document.createElement("p");
    permission.className = "companion-message__answer-status";
    permission.textContent = `Permissions: ${visiblePermissions.map((name) => `${name} ${permissions[name] ? "on" : "off"}`).join(", ")}`;
    message.appendChild(permission);
  }
}

function appendVisionTraceDetails(message, trace = {}) {
  if (!message || !trace || typeof trace !== "object") return;
  const document = message.ownerDocument;
  if (!document?.createElement) return;
  const details = [];
  const image = trace.image;
  if (image?.width && image?.height) {
    details.push(`Basic inspection: ${image.width} × ${image.height}px${image.format ? `, ${image.format}` : ""}.`);
  } else if (Array.isArray(trace.skills) && trace.skills.includes("basic_image_inspection")) {
    details.push("Basic inspection ran.");
  }
  const ocrUsed = Array.isArray(trace.skills) && trace.skills.some((skill) => /(?:^|_)ocr$/i.test(String(skill)));
  if (ocrUsed) details.push("OCR ran on this picture.");
  if (trace.vision_model_used === true) details.push(`Vision model: ${String(trace.vision_model || "local model")}.`);
  for (const detail of details) {
    const item = document.createElement("p");
    item.className = "companion-message__answer-status";
    item.textContent = detail;
    message.appendChild(item);
  }
}

function renderRetry(timeline, text, retry) {
  const document = timeline.ownerDocument;
  const row = document.createElement("div");
  row.className = "companion-retry";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Retry";
  button.addEventListener("click", () => { void retry(text); });
  row.appendChild(button);
  timeline.appendChild(row);
}

function updateTrustFromTrace(dispatch, trace = {}, status = {}) {
  const permissions = trace.permissions_snapshot || trace.permissions || status.permissions || {};
  const answerStatus = trace.answer_status || {};
  dispatch({
    type: "TRUST_CHANGED",
    local: typeof status.local === "boolean" ? status.local : null,
    provider: String(trace.provider || status.provider || ""),
    model: String(trace.model || status.model || ""),
    memoryUsed: Boolean(answerStatus.memory === "used" || answerStatus.memory_used),
  });
  return permissions;
}

export async function bootstrapCompanion(document = globalThis.document) {
  const root = document?.getElementById("companionApp");
  const timeline = document?.getElementById("conversationTimeline");
  const form = document?.getElementById("companionComposer");
  const input = document?.getElementById("companionInput");
  const sendButton = document?.getElementById("companionSendButton");
  if (!root || !timeline || !form || !input || !sendButton) return null;

  const { clientId, conversationId } = createCompanionIdentity(globalThis);
  const rawApi = new NovaCompanionApi();
  let api = rawApi;
  let state = createInitialCompanionState({ clientId, conversationId });
  let status = {};
  let composer;
  let spark;
  let trust;
  let vision;
  let voice;
  let voiceState = { listening: false, speaking: false };
  let closeVisionSheet = () => {};
  let visionSheetGeneration = 0;
  let inFlight = false;

  const elements = {
    presence: document.getElementById("novaPresence"),
    face: document.getElementById("novaFace"),
    greeting: document.getElementById("novaGreeting"),
    liveStatus: document.getElementById("companionLiveStatus"),
  };
  const trustLabel = document.getElementById("companionTrustLabel");
  const render = () => {
    renderPresence(elements, presenceViewModel({ ...state, voice: voiceState }, globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches));
    root.setAttribute("aria-busy", String(Boolean(state.activeRequestId)));
  };
  const dispatch = (event) => {
    state = reduceCompanionState(state, event);
    render();
    return state;
  };
  const setConnectionLabel = (label) => {
    if (trustLabel) trustLabel.textContent = label;
  };
  trust = createTrustController({
    document,
    api: rawApi,
    pairedDeviceToken: globalThis.pairedDeviceToken,
    rememberPairedDeviceToken: globalThis.rememberPairedDeviceToken,
    onBeforeOpen: () => {
      spark?.close();
      closeVisionSheet();
    },
    onPairingRequired: () => {
      setConnectionLabel("Remote · Pairing required");
      elements.liveStatus.textContent = "Pair this device, then choose Retry on your message.";
    },
    onPaired: () => {
      setConnectionLabel("Remote · Paired");
      elements.liveStatus.textContent = "Paired securely. Choose Retry to send your message.";
    },
    onStateChange: (projected, pairing) => {
      setConnectionLabel(trustConnectionLabel(projected, pairing));
      dispatch({
        type: "TRUST_CHANGED",
        local: projected.connection === "local",
        provider: projected.provider,
        model: projected.model,
        memoryUsed: projected.memoryUsed,
      });
    },
  });
  api = trust.wrapApi(rawApi);
  const voiceSupport = voiceAvailability(globalThis, { ttsAvailable: typeof api.postTts === "function" });
  let voiceOutputEnabled = false;
  const voiceButton = document.createElement("button");
  voiceButton.type = "button";
  voiceButton.id = "companionVoiceButton";
  voiceButton.textContent = voiceSupport.transcription ? (voiceSupport.playback ? "Talk" : "Talk (input only)") : "Voice input unavailable";
  voiceButton.setAttribute("aria-label", voiceSupport.transcription ? "Talk with Nova" : voiceSupport.reason);
  if (!voiceSupport.transcription) {
    voiceButton.disabled = true;
    voiceButton.title = voiceSupport.reason;
  }
  const voiceOutputButton = document.createElement("button");
  voiceOutputButton.type = "button";
  voiceOutputButton.id = "companionVoiceOutputButton";
  const setVoiceOutputEnabled = (enabled) => {
    voiceOutputEnabled = Boolean(enabled) && voiceSupport.playback;
    voiceOutputButton.textContent = voiceOutputEnabled ? "Voice output on" : voiceSupport.playback ? "Voice output off" : "Voice output unavailable";
    voiceOutputButton.setAttribute("aria-pressed", String(voiceOutputEnabled));
    voiceOutputButton.setAttribute("aria-label", voiceSupport.playback ? "Toggle Nova voice output" : voiceSupport.outputReason);
  };
  voiceOutputButton.disabled = !voiceSupport.playback;
  if (!voiceSupport.playback) voiceOutputButton.title = voiceSupport.outputReason;
  setVoiceOutputEnabled(false);
  const voiceStopButton = document.createElement("button");
  voiceStopButton.type = "button";
  voiceStopButton.id = "companionVoiceStopButton";
  voiceStopButton.textContent = "Stop voice";
  voiceStopButton.setAttribute("aria-label", "Stop voice and Nova's active response");
  form.insertBefore(voiceButton, sendButton);
  form.insertBefore(voiceOutputButton, sendButton);
  form.insertBefore(voiceStopButton, sendButton);

  const showVoiceStatus = (event) => {
    switch (event.type) {
      case "LISTENING_INTERIM":
        elements.liveStatus.textContent = `Hearing: ${event.text}`;
        break;
      case "LISTENING_FINAL":
        elements.liveStatus.textContent = "Transcript ready. Review it, then Send.";
        break;
      case "LISTENING_UNAVAILABLE":
      case "LISTENING_FAILED":
      case "SPEECH_FAILED":
      case "SPEECH_UNAVAILABLE":
        elements.liveStatus.textContent = event.message;
        break;
      default:
        break;
    }
  };
  const handleVoiceEvent = (event) => {
    switch (event.type) {
      case "LISTENING_STARTED":
        voiceState = { ...voiceState, listening: true };
        dispatch({ type: "MICROPHONE_CHANGED", permission: "granted", active: true });
        break;
      case "LISTENING_STOPPED":
      case "LISTENING_FAILED":
      case "LISTENING_UNAVAILABLE":
        voiceState = { ...voiceState, listening: false };
        dispatch({ type: "MICROPHONE_CHANGED", active: false });
        break;
      case "SPEECH_STARTED":
        voiceState = { ...voiceState, speaking: true };
        dispatch(event);
        break;
      case "SPEECH_FINISHED":
      case "SPEECH_STOPPED":
      case "SPEECH_FAILED":
      case "SPEECH_UNAVAILABLE":
        voiceState = { ...voiceState, speaking: false };
        dispatch(event);
        if (event.type === "SPEECH_FAILED") setVoiceOutputEnabled(false);
        break;
      default:
        dispatch(event);
        break;
    }
    showVoiceStatus(event);
    trust.update({ camera: state.camera, microphone: state.microphone });
  };

  const addVisionResult = (result, isCurrentSheet = () => true) => {
    if (!isCurrentSheet()) return false;
    const trace = result?.trace || {};
    const message = appendMessage(timeline, {
      id: `vision_${createRequestId()}`,
      role: "assistant",
      text: String(result?.response || result?.error || "Nova did not return a vision answer."),
      status: result?.ok === false ? "failed" : "completed",
      answerStatus: null,
      artifact: null,
    });
    const answerStatus = result?.answer_status || trace.answer_status;
    if (answerStatus) message.dataset.answerStatus = JSON.stringify(answerStatus);
    appendCompletionDetails(message, answerStatus, result?.permissions);
    appendVisionTraceDetails(message, trace);
    updateTrustFromTrace(dispatch, trace, { permissions: result?.permissions });
    trust.update({ trace, camera: state.camera, microphone: state.microphone });
    timeline.scrollTop = timeline.scrollHeight;
    return true;
  };

  const openVisionSheet = (invoker = document.activeElement) => {
    const host = document.getElementById("companionSheetHost");
    const backdrop = document.getElementById("companionSheetBackdrop");
    if (!host || !backdrop) return false;
    closeVisionSheet();
    const sheetGeneration = ++visionSheetGeneration;
    const sheetAbort = new AbortController();
    const isCurrentSheet = () => sheetGeneration === visionSheetGeneration && !sheetAbort.signal.aborted;
    host.replaceChildren();
    host.hidden = false;
    backdrop.hidden = false;
    host.classList.add("companion-vision");
    host.setAttribute("aria-label", "See with Nova");
    dispatch({ type: "SHEET_CHANGED", sheet: "vision" });

    const title = document.createElement("h2");
    title.textContent = "See with Nova";
    const privacy = document.createElement("p");
    privacy.className = "companion-vision__privacy";
    privacy.textContent = "Pictures are prepared locally. Nova sends only the frame you choose for this request; image persistence is off.";
    const statusLine = document.createElement("p");
    statusLine.className = "companion-vision__status";
    statusLine.setAttribute("role", "status");
    statusLine.textContent = "Camera is off. Choose a picture or enable the camera.";
    const prompt = document.createElement("textarea");
    prompt.rows = 2;
    prompt.maxLength = 500;
    prompt.placeholder = "What should Nova look for?";
    prompt.value = "What is in front of me?";
    prompt.className = "companion-vision__prompt";
    const pictureLabel = document.createElement("label");
    pictureLabel.className = "companion-vision__file";
    pictureLabel.textContent = "Choose picture";
    const picture = document.createElement("input");
    picture.type = "file";
    picture.accept = "image/jpeg,image/png,image/webp";
    pictureLabel.appendChild(picture);
    const preview = document.createElement("video");
    preview.className = "companion-vision__preview";
    preview.autoplay = true;
    preview.muted = true;
    preview.playsInline = true;
    const previewCanvas = document.createElement("canvas");
    previewCanvas.hidden = true;
    const buttons = document.createElement("div");
    buttons.className = "companion-vision__actions";
    const enable = document.createElement("button");
    enable.type = "button";
    enable.textContent = "Enable Camera";
    const facing = document.createElement("button");
    facing.type = "button";
    facing.textContent = "Use front camera";
    const look = document.createElement("button");
    look.type = "button";
    look.textContent = "Look";
    const stop = document.createElement("button");
    stop.type = "button";
    stop.textContent = "Stop";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "companion-vision__close";
    close.textContent = "Close";
    buttons.append(enable, facing, look, stop, close);
    host.append(title, privacy, statusLine, pictureLabel, prompt, preview, previewCanvas, buttons);

    let preparedPicture = null;
    let picturePreparationGeneration = 0;
    let visionRequestGeneration = 0;
    const updateCameraStatus = (camera) => {
      statusLine.textContent = camera.active
        ? `Camera is live (${camera.facingMode === "user" ? "front" : "back"}). Tap Look to capture one frame.`
        : camera.permission === "denied"
          ? "Camera permission was not granted. You can still choose a picture."
          : "Camera is off. Choose a picture or enable the camera.";
      facing.textContent = camera.facingMode === "user" ? "Use back camera" : "Use front camera";
    };
    vision = createVisionController({
      api,
      preview,
      previewCanvas,
      onStateChange: (camera) => {
        if (!isCurrentSheet()) return;
        dispatch({ type: "CAMERA_CHANGED", permission: camera.permission, active: camera.active, persisted: false });
        trust.update({ camera: state.camera, microphone: state.microphone });
        updateCameraStatus(camera);
      },
      onResult: (result) => { addVisionResult(result, isCurrentSheet); },
    });
    const pictureSubmitter = createSelectedPictureVisionSubmitter({
      api,
      signal: sheetAbort.signal,
      isCurrentSheet,
      cameraIsActive: () => vision?.getState().active === true,
      onStatus: (text) => { statusLine.textContent = text; },
      onResult: (result) => { addVisionResult(result, isCurrentSheet); },
    });
    const focusVisionControl = (index) => {
      const controls = [...host.querySelectorAll("button:not([disabled]), input:not([disabled]), textarea:not([disabled])")];
      const control = index < 0 ? controls.at(-1) : controls[index];
      control?.focus?.({ preventScroll: true });
    };
    const closeSheet = () => {
      if (!isCurrentSheet()) return;
      visionSheetGeneration += 1;
      picturePreparationGeneration += 1;
      visionRequestGeneration += 1;
      sheetAbort.abort();
      vision?.stopCamera();
      vision = null;
      preparedPicture = null;
      host.hidden = true;
      backdrop.hidden = true;
      host.classList.remove("companion-vision");
      dispatch({ type: "SHEET_CHANGED", sheet: null });
      document.removeEventListener?.("keydown", onKeydown);
      backdrop.removeEventListener("click", closeSheet);
      closeVisionSheet = () => {};
      const fallback = document.getElementById("novaSparkButton");
      resolveVisionFocusRestoreTarget(invoker, fallback)?.focus?.({ preventScroll: true });
    };
    const onKeydown = (event) => {
      if (!isCurrentSheet()) return;
      if (event.key === "Escape") {
        event.preventDefault();
        closeSheet();
        return;
      }
      if (event.key !== "Tab") return;
      const controls = [...host.querySelectorAll("button:not([disabled]), input:not([disabled]), textarea:not([disabled])")];
      if (!controls.length) return;
      const first = controls[0];
      const last = controls.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        focusVisionControl(-1);
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        focusVisionControl(0);
      }
    };
    closeVisionSheet = closeSheet;
    document.addEventListener?.("keydown", onKeydown);
    backdrop.addEventListener("click", closeSheet, { once: true });
    picture.addEventListener("change", async () => {
      if (!isCurrentSheet()) return;
      const file = picture.files?.[0];
      picture.value = "";
      if (!file) return;
      const preparationGeneration = ++picturePreparationGeneration;
      try {
        statusLine.textContent = "Preparing the selected picture locally…";
        const frame = await prepareVisionCanvas(file);
        if (!isCurrentSheet() || preparationGeneration !== picturePreparationGeneration) return;
        preparedPicture = frame;
        statusLine.textContent = `Picture ready: ${preparedPicture.width} × ${preparedPicture.height}px. Tap Look to send it.`;
      } catch (error) {
        if (!isCurrentSheet() || preparationGeneration !== picturePreparationGeneration) return;
        preparedPicture = null;
        statusLine.textContent = error instanceof Error ? error.message : "Nova could not prepare that picture.";
      }
    });
    enable.addEventListener("click", async () => {
      if (!isCurrentSheet()) return;
      try {
        await vision?.enableCamera();
      } catch (error) {
        if (!isCurrentSheet()) return;
        statusLine.textContent = error instanceof Error ? error.message : "Nova could not enable the camera.";
      }
    });
    facing.addEventListener("click", async () => {
      if (!isCurrentSheet()) return;
      try {
        const next = vision?.getState().facingMode === "user" ? "environment" : "user";
        await vision?.changeFacingMode(next);
      } catch (error) {
        if (!isCurrentSheet()) return;
        statusLine.textContent = error instanceof Error ? error.message : "Nova could not switch cameras.";
      }
    });
    look.addEventListener("click", async () => {
      if (!isCurrentSheet()) return;
      const requestGeneration = ++visionRequestGeneration;
      const pictureForRequest = preparedPicture;
      try {
        if (pictureForRequest) {
          await pictureSubmitter.submit(pictureForRequest, prompt.value, {
            isCurrentRequest: () => requestGeneration === visionRequestGeneration,
          });
        } else {
          statusLine.textContent = "Nova is inspecting the live frame you chose…";
          await vision?.look(prompt.value);
        }
      } catch (error) {
        if (!isCurrentSheet() || requestGeneration !== visionRequestGeneration) return;
        if (!pictureForRequest) {
          statusLine.textContent = error instanceof Error ? error.message : "Nova could not inspect that frame.";
        }
      }
    });
    stop.addEventListener("click", () => vision?.stopCamera());
    close.addEventListener("click", closeSheet);
    updateCameraStatus(vision.getState());
    focusVisionControl(0);
    return true;
  };

  const sendConversation = async (text, { markRequestAccepted }) => {
    if (inFlight) return;
    inFlight = true;
    const requestId = createRequestId();
    const userMessage = appendMessage(timeline, {
      id: `msg_${requestId}`, role: "user", text, status: "pending", answerStatus: null, artifact: null,
    });
    let assistantMessage = null;
    let accepted = false;
    dispatch({ type: "SUBMIT", requestId, text });
    try {
      const result = await api.streamChat({ text, requestId, clientId, conversationId }, {
        onEvent(event) {
          if (!accepted && !event?.error && eventType(event) !== "error") {
            accepted = true;
            dispatch({ type: "REQUEST_ACCEPTED", requestId });
            markMessageStatus(userMessage, "completed");
            markRequestAccepted();
            assistantMessage = beginStreamingMessage(timeline, event?.response_id || event?.response?.id || requestId);
          }
          const type = eventType(event);
          if (type === "response.progress") dispatch({ type: "THINKING", requestId });
          if (type === "tool.proposed") dispatch({ type: "TOOL_PROPOSED", requestId, toolName: event?.tool?.name });
          if (type === "tool.started") dispatch({ type: "TOOL_STARTED", requestId, toolName: event?.tool?.name });
        },
        onDelta(delta) {
          if (!assistantMessage) assistantMessage = beginStreamingMessage(timeline, requestId);
          appendStreamingDelta(assistantMessage, delta);
          dispatch({ type: "DELTA", requestId, delta });
        },
      });
      if (assistantMessage) {
        markMessageStatus(assistantMessage, "completed");
        const answerStatus = result.trace?.answer_status;
        if (answerStatus) assistantMessage.dataset.answerStatus = JSON.stringify(answerStatus);
        appendCompletionDetails(assistantMessage, answerStatus, result.trace?.permissions_snapshot || result.trace?.permissions);
      }
      updateTrustFromTrace(dispatch, result.trace, status);
      trust.update({
        trace: result.trace,
        status,
        camera: state.camera,
        microphone: state.microphone,
      });
      dispatch({ type: "COMPLETED", requestId });
      if (voiceOutputEnabled) await voice?.speak(String(result?.response || result?.text || ""));
    } catch (error) {
      const safeError = error instanceof NovaApiError ? error : new NovaApiError();
      const cancelled = safeError.code === "cancelled";
      markMessageStatus(userMessage, cancelled ? "cancelled" : "failed");
      if (assistantMessage) markMessageStatus(assistantMessage, cancelled ? "cancelled" : "failed");
      dispatch({ type: cancelled ? "CANCELLED" : "FAILED", requestId, error: safeError.message });
      if (!cancelled) {
        appendMessage(timeline, {
          id: `msg_error_${requestId}`, role: "system", text: safeError.message, status: "failed", answerStatus: null, artifact: null,
        });
        renderRetry(timeline, text, async (retryText) => {
          input.value = retryText;
          await composer.submit();
        });
      }
    } finally {
      inFlight = false;
    }
  };

  const stopVoiceAndRequest = () => stopVoiceAndActiveRequest({ voice, api, requestId: state.activeRequestId });
  composer = createComposerController({
    form, input, sendButton,
    onSubmit: sendConversation,
    onStop: stopVoiceAndRequest,
  });
  const voiceApi = { postTts: (...args) => api.postTts(...args) };
  voice = createVoiceController({
    windowLike: globalThis,
    api: voiceApi,
    ttsAvailable: voiceSupport.playback,
    dispatch: handleVoiceEvent,
    onInterimTranscript: () => {},
    onTranscript: (text) => {
      composer.setTransientText(text);
      input.focus({ preventScroll: true });
    },
  });
  voiceButton.addEventListener("click", () => { voice.startListening(); });
  voiceOutputButton.addEventListener("click", () => { setVoiceOutputEnabled(!voiceOutputEnabled); });
  voiceStopButton.addEventListener("click", () => { void stopVoiceAndRequest(); });
  spark = createSparkController({
    document,
    loadServerState: () => loadSparkServerState(api),
    onCompanionAction: async (action) => {
      if (action.id === "vision") {
        const invoker = document.activeElement;
        globalThis.setTimeout?.(() => { openVisionSheet(invoker); }, 0);
        return true;
      }
      elements.liveStatus.textContent = `${action.label} is not available in this Companion version yet.`;
      return false;
    },
  });
  const restoreAfterPersistedNavigation = (event) => {
    if (event.persisted) composer.restoreFocus();
  };
  if (typeof globalThis.addEventListener === "function") {
    globalThis.addEventListener("pageshow", restoreAfterPersistedNavigation);
  }

  try {
    const projected = await trust.refresh();
    status = {
      local: projected.connection === "local",
      provider: projected.provider,
      model: projected.model,
    };
    if (trust.pairingRequired) {
      setConnectionLabel("Remote · Pairing required");
      elements.liveStatus.textContent = "Pair this device, then choose Retry on your message.";
      trust.openPairing(document.getElementById("companionTrustButton"));
    } else if (projected.connection === "offline") {
      setConnectionLabel("Offline");
      dispatch({ type: "OFFLINE" });
    } else {
      dispatch({ type: "READY" });
      updateTrustFromTrace(dispatch, {}, status);
    }
  } catch (error) {
    const pairingRequired = error instanceof NovaApiError && error.code === "pairing_required";
    if (pairingRequired) {
      setConnectionLabel("Pairing required");
      elements.liveStatus.textContent = "Pairing required";
    } else {
      setConnectionLabel("Offline");
      dispatch({ type: "OFFLINE" });
    }
  }
  render();
  root.dataset.companionReady = "true";
  return {
    api,
    composer,
    getState: () => state,
    destroy() {
      if (typeof globalThis.removeEventListener === "function") {
        globalThis.removeEventListener("pageshow", restoreAfterPersistedNavigation);
      }
      composer.destroy();
      voiceButton.remove();
      voiceOutputButton.remove();
      voiceStopButton.remove();
      voice?.destroy();
      spark?.destroy();
      trust?.destroy();
      closeVisionSheet();
    },
  };
}

export function presentBootstrapFailure(document = globalThis.document) {
  const root = document?.getElementById?.("companionApp");
  const trustLabel = document?.getElementById?.("companionTrustLabel");
  const liveStatus = document?.getElementById?.("companionLiveStatus");
  const input = document?.getElementById?.("companionInput");
  const sendButton = document?.getElementById?.("companionSendButton");
  const sparkButton = document?.getElementById?.("novaSparkButton");
  if (root) {
    root.setAttribute("aria-busy", "false");
    root.dataset.companionReady = "false";
  }
  if (trustLabel) trustLabel.textContent = "Setup unavailable";
  if (liveStatus) {
    liveStatus.textContent = "Nova Companion could not finish setup. Reload this page or open Nova Classic.";
    liveStatus.classList?.remove("sr-only");
    liveStatus.classList?.add("companion-boot-failure");
  }
  if (input) input.disabled = true;
  if (sendButton) sendButton.disabled = true;
  if (sparkButton) sparkButton.disabled = true;
}

export async function startCompanion({
  document = globalThis.document,
  boot = bootstrapCompanion,
} = {}) {
  try {
    return await boot(document);
  } catch {
    presentBootstrapFailure(document);
    return null;
  }
}

function start() {
  void startCompanion();
}

if (globalThis.document) {
  if (globalThis.document.readyState === "loading") globalThis.document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}
