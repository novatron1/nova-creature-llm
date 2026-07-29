// This is a display-only reducer. It never persists state, authorizes actions,
// or decides backend truth; the backend remains authoritative for all of those.
const phases = [
  "booting", "submitting", "thinking", "acting", "responding", "completed",
  "offline", "failed", "cancelled",
];

const events = [
  "READY", "SUBMIT", "REQUEST_ACCEPTED", "THINKING", "TOOL_PROPOSED",
  "TOOL_STARTED", "DELTA", "COMPLETED", "FAILED", "CANCELLED", "OFFLINE",
  "ONLINE", "IDENTITY_CHANGED", "SHEET_CHANGED", "CAMERA_CHANGED",
  "MICROPHONE_CHANGED", "TRUST_CHANGED",
];

export const COMPANION_PHASES = new Set(phases);
export const COMPANION_EVENTS = new Set(events);

const REQUEST_EVENTS = new Set([
  "REQUEST_ACCEPTED", "THINKING", "TOOL_PROPOSED", "TOOL_STARTED", "DELTA", "COMPLETED", "FAILED", "CANCELLED",
]);

function freezeState(state) {
  Object.freeze(state.acceptedRequestIds);
  if (state.activeTool) Object.freeze(state.activeTool);
  Object.freeze(state.camera);
  Object.freeze(state.microphone);
  Object.freeze(state.trust);
  return Object.freeze(state);
}

function asText(value) {
  return typeof value === "string" ? value : "";
}

function acceptedRequestIds(ids, requestId) {
  const next = ids.filter((id) => id !== requestId);
  if (requestId) next.push(requestId);
  return next.slice(-20);
}

function requestMatches(state, event) {
  return Boolean(event.requestId) && event.requestId === state.activeRequestId;
}

function withRequest(state, requestId, changes) {
  return freezeState({
    ...state,
    ...changes,
    activeRequestId: requestId,
    acceptedRequestIds: acceptedRequestIds(state.acceptedRequestIds, requestId),
  });
}

export function createInitialCompanionState(options = {}) {
  return freezeState({
    phase: "booting",
    // These are read-only UI projections, never authorization or persistence inputs.
    clientId: asText(options.clientId),
    conversationId: asText(options.conversationId),
    activeRequestId: "",
    acceptedRequestIds: [],
    conversationTurnCount: 0,
    streamingText: "",
    activeTool: null, // Observed/proposed tool display metadata only.
    error: null,
    offline: false,
    sheet: null, // UI-only sheet selection.
    camera: { permission: "unknown", active: false, persisted: false }, // Display projection.
    microphone: { permission: "unknown", active: false }, // Display projection.
    trust: { local: null, provider: "", model: "", memoryUsed: false }, // Display projection.
  });
}

export function reduceCompanionState(state, event) {
  if (!state || !event || !COMPANION_EVENTS.has(event.type)) return state;
  if (REQUEST_EVENTS.has(event.type) && !requestMatches(state, event)) return state;

  switch (event.type) {
    case "READY":
      return freezeState({ ...state, phase: state.offline ? "offline" : "completed" });
    case "SUBMIT": {
      const requestId = asText(event.requestId);
      if (!requestId) return state;
      return withRequest(state, requestId, {
        phase: "submitting", streamingText: "", activeTool: null, error: null, offline: false,
      });
    }
    case "REQUEST_ACCEPTED":
    case "THINKING":
      return freezeState({ ...state, phase: "thinking", error: null, offline: false });
    case "TOOL_PROPOSED": {
      return freezeState({
        ...state,
        activeTool: { name: asText(event.toolName), status: "proposed" },
      });
    }
    case "TOOL_STARTED":
      return freezeState({
        ...state,
        phase: "acting",
        activeTool: { name: asText(event.toolName) || state.activeTool?.name || "", status: "started" },
      });
    case "DELTA":
      return freezeState({
        ...state,
        phase: "responding",
        streamingText: state.streamingText + asText(event.delta),
        activeTool: null,
      });
    case "COMPLETED":
      return freezeState({ ...state, phase: "completed", activeRequestId: "", activeTool: null });
    case "FAILED":
      return freezeState({
        ...state, phase: "failed", activeRequestId: "", activeTool: null,
        error: asText(event.error) || "Nova could not complete that request.",
      });
    case "CANCELLED":
      return freezeState({
        ...state, phase: "cancelled", activeRequestId: "", streamingText: "", activeTool: null,
      });
    case "OFFLINE":
      return freezeState({ ...state, phase: "offline", offline: true, activeRequestId: "", activeTool: null });
    case "ONLINE":
      return freezeState({ ...state, phase: "completed", offline: false, error: null });
    case "IDENTITY_CHANGED": {
      const identityChanged = asText(event.clientId) !== state.clientId
        || asText(event.conversationId) !== state.conversationId;
      if (!identityChanged) return state;
      return freezeState({
        ...state,
        clientId: asText(event.clientId), conversationId: asText(event.conversationId),
        phase: "completed", activeRequestId: "", acceptedRequestIds: [], streamingText: "",
        activeTool: null, error: null, sheet: null,
        camera: { ...state.camera, active: false },
        microphone: { ...state.microphone, active: false },
        trust: { ...state.trust, memoryUsed: false },
      });
    }
    case "SHEET_CHANGED":
      return freezeState({ ...state, sheet: event.sheet ?? null });
    case "CAMERA_CHANGED":
      return freezeState({
        ...state,
        camera: {
          permission: asText(event.permission) || state.camera.permission,
          active: Boolean(event.active), persisted: Boolean(event.persisted),
        },
      });
    case "MICROPHONE_CHANGED":
      return freezeState({
        ...state,
        microphone: {
          permission: asText(event.permission) || state.microphone.permission,
          active: Boolean(event.active),
        },
      });
    case "TRUST_CHANGED":
      return freezeState({
        ...state,
        trust: {
          local: typeof event.local === "boolean" ? event.local : state.trust.local,
          provider: asText(event.provider), model: asText(event.model), memoryUsed: Boolean(event.memoryUsed),
        },
      });
    default:
      return state;
  }
}
