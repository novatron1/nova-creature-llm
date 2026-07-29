import { NovaCompanionApi, NovaApiError, createRequestId } from "./companion-api.js";
import { createInitialCompanionState, reduceCompanionState } from "./companion-store.js";
import { presenceViewModel, renderPresence } from "./companion-presence.js";
import { appendMessage, beginStreamingMessage, appendStreamingDelta } from "./companion-conversation.js";
import { createComposerController } from "./companion-composer.js";

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
