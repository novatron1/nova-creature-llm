import { NovaCompanionApi, NovaApiError, createRequestId } from "./companion-api.js";
import { createInitialCompanionState, reduceCompanionState } from "./companion-store.js";
import { presenceViewModel, renderPresence } from "./companion-presence.js";
import { appendMessage, beginStreamingMessage, appendStreamingDelta } from "./companion-conversation.js";
import { createComposerController } from "./companion-composer.js";
import { createSparkController } from "./companion-spark.js";
import { buildVisionPayload, createVisionController, prepareVisionCanvas } from "./companion-senses.js";

const CLIENT_ID_KEY = "nova_companion_client_id_v1";
const CONVERSATION_ID_KEY = "nova_companion_conversation_id_v1";
const DRAFT_KEY = "nova_companion_draft_v1";

function generatedId(prefix) {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${globalThis.crypto.randomUUID()}`;
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

function storageValue(storage, key, prefix) {
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

  const storage = globalThis.localStorage;
  const clientId = storageValue(storage, CLIENT_ID_KEY, "client");
  const conversationId = storageValue(storage, CONVERSATION_ID_KEY, "conversation");
  const api = new NovaCompanionApi();
  let state = createInitialCompanionState({ clientId, conversationId });
  let status = {};
  let composer;
  let spark;
  let vision;
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
    renderPresence(elements, presenceViewModel(state, globalThis.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches));
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
        updateCameraStatus(camera);
      },
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
      try {
        statusLine.textContent = "Nova is inspecting the frame you chose…";
        if (preparedPicture) {
          const result = await api.postVision(buildVisionPayload(preparedPicture, prompt.value), { signal: sheetAbort.signal });
          if (!isCurrentSheet() || requestGeneration !== visionRequestGeneration) return;
          addVisionResult(result, isCurrentSheet);
        } else {
          await vision?.look(prompt.value);
        }
      } catch (error) {
        if (!isCurrentSheet() || requestGeneration !== visionRequestGeneration) return;
        statusLine.textContent = error instanceof Error ? error.message : "Nova could not inspect that frame.";
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
      dispatch({ type: "COMPLETED", requestId });
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

  composer = createComposerController({
    form, input, sendButton, storage, draftKey: DRAFT_KEY,
    onSubmit: sendConversation,
    onStop: async () => {
      const requestId = state.activeRequestId;
      if (requestId) await api.cancel(requestId);
    },
  });
  spark = createSparkController({
    document,
    loadServerState: async () => {
      const [capabilitiesResult, toolsResult] = await Promise.allSettled([
        api.getJson("/nova/v1/capabilities"),
        api.getJson("/nova/v1/tools"),
      ]);
      const capabilities = capabilitiesResult.status === "fulfilled" ? capabilitiesResult.value : {};
      const toolData = toolsResult.status === "fulfilled" && Array.isArray(toolsResult.value?.data)
        ? toolsResult.value.data
        : [];
      const items = new Map(toolData.map((item) => [String(item?.id || item?.name || ""), item]));
      return { capabilities, items, companion: status?.companion || {} };
    },
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
    status = await api.getStatus();
    const pairingRequired = status?.code === "pairing_required" || status?.pairing_required === true;
    if (pairingRequired) {
      setConnectionLabel("Pairing required");
      elements.liveStatus.textContent = "Pairing required";
    } else {
      setConnectionLabel("Present");
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
      spark?.destroy();
      closeVisionSheet();
    },
  };
}

function start() {
  void bootstrapCompanion().catch(() => {
    const root = globalThis.document?.getElementById("companionApp");
    if (root) root.setAttribute("aria-busy", "false");
  });
}

if (globalThis.document) {
  if (globalThis.document.readyState === "loading") globalThis.document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}
