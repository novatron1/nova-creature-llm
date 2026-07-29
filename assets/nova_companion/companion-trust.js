const REDACTED = "[redacted]";
const SENSITIVE_KEY = /(?:authorization|api[_-]?key|token|secret|password|prompt|memory[_-]?(?:content|text)|image[_-]?(?:base64|data)|hidden[_-]?reasoning|chain[_-]?of[_-]?thought|tool[_-]?(?:arguments|input)|headers?|file[_-]?content)/i;
const ACTION_STATES = new Set(["proposed", "authorized", "attempted", "started", "completed", "failed", "cancelled"]);
const CONNECTIONS = new Set(["local", "remote", "offline", "unknown"]);

function safeText(value, maximum = 160) {
  return typeof value === "string" ? value.slice(0, maximum) : "";
}

function safeCost(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function connectionFor(inputs) {
  const explicit = safeText(inputs?.connection).toLowerCase();
  if (inputs?.offline === true) return "offline";
  const status = inputs?.status || {};
  const pairing = inputs?.pairing || {};
  if (explicit === "offline" || explicit === "remote" || explicit === "unknown") return explicit;
  if (explicit === "local" && status?.local !== true && pairing?.local_client !== true) return "unknown";
  if (CONNECTIONS.has(explicit)) return explicit;
  if (status?.ok === false && inputs?.health?.ok === false) return "offline";
  if (status?.local === false || pairing?.local_client === false || status?.pairing_required === true) return "remote";
  if (status?.local === true || pairing?.local_client === true) return "local";
  return "unknown";
}

function recentActionsFor(inputs) {
  const trace = inputs?.trace || {};
  const status = inputs?.status || {};
  const source = Array.isArray(trace.recent_actions)
    ? trace.recent_actions
    : (Array.isArray(status.recent_actions)
      ? status.recent_actions
      : (Array.isArray(inputs?.recentActions) ? inputs.recentActions : []));
  return source.slice(-12).map((item) => {
    const state = safeText(item?.state || item?.status, 32).toLowerCase();
    if (!ACTION_STATES.has(state)) return null;
    return {
      name: safeText(item?.name || item?.action || item?.tool?.name, 96),
      state,
      timestamp: safeText(item?.timestamp || item?.created_at || item?.updated_at, 64),
    };
  }).filter((item) => item?.name);
}

function hasOwn(object, key) {
  return Boolean(object && Object.prototype.hasOwnProperty.call(object, key));
}

function hasAuthoritativeCost(inputs) {
  return hasOwn(inputs, "estimatedCost")
    || hasOwn(inputs?.trace, "estimated_cost")
    || hasOwn(inputs?.status, "estimated_cost")
    || hasOwn(inputs?.health, "estimated_cost");
}

function hasAuthoritativeActions(inputs) {
  return hasOwn(inputs, "recentActions")
    || hasOwn(inputs?.trace, "recent_actions")
    || hasOwn(inputs?.status, "recent_actions");
}

/**
 * Redact values whose key can carry authorization, private content, or hidden
 * model work. This helper is intentionally conservative and safe for UI use.
 */
export function redactTrustValue(key, value) {
  return SENSITIVE_KEY.test(String(key || "")) ? REDACTED : value;
}

/**
 * Project arbitrary server inputs into the complete, fixed Trust UI schema.
 * No unrecognized server field can cross this boundary.
 */
export function projectTrustState(inputs = {}) {
  const status = inputs.status || {};
  const health = inputs.health || {};
  const trace = inputs.trace || {};
  const answerStatus = trace.answer_status || {};
  const camera = inputs.camera || {};
  const microphone = inputs.microphone || {};
  const permissions = trace.permissions_snapshot || trace.permissions || status.permissions || {};
  const regularRoute = status.regular_chat_routing || {};
  const provider = safeText(
    trace.provider
    || status.provider
    || regularRoute.primary_provider
    || health.provider
    || health.cognitive_core?.provider_id
    || inputs.provider,
  );
  const model = safeText(
    trace.model
    || status.model
    || regularRoute.primary_model
    || health.model
    || inputs.model,
  );
  const estimatedCost = trace.estimated_cost ?? status.estimated_cost ?? health.estimated_cost ?? inputs.estimatedCost;
  return {
    connection: connectionFor(inputs),
    provider,
    model,
    privateMode: Boolean(status.private_mode ?? status.privacy_mode ?? inputs.privateMode),
    memoryUsed: Boolean(
      answerStatus.memory === "used"
      || answerStatus.memory_used
      || trace.memory_used
      || inputs.memoryUsed,
    ),
    camera: {
      active: Boolean(camera.active ?? status.camera_active ?? permissions.camera_active),
      persisted: Boolean(camera.persisted ?? status.image_persistence ?? status.camera_persisted),
    },
    microphone: {
      active: Boolean(microphone.active ?? status.microphone_active ?? permissions.microphone_active),
    },
    pendingConfirmation: Boolean(
      trace.pending_confirmation
      || status.pending_confirmation
      || inputs.pendingConfirmation,
    ),
    estimatedCost: safeCost(estimatedCost),
    recentActions: recentActionsFor(inputs),
  };
}

/** Return one truthful connection label from the fixed Trust state. */
export function trustConnectionLabel(state, access = {}) {
  if (state?.connection === "offline") return "Offline";
  if (state?.connection === "unknown") return "Connection unknown";
  if (state?.connection === "local") return state?.privateMode ? "Local · Private" : "Local";
  if (state?.connection !== "remote") return "Offline";
  if (access.pairingEnabled === false) return "Remote";
  if (access.pairingRequired === true) return "Remote · Pairing required";
  if (access.paired === true) return "Remote · Paired";
  return "Remote";
}

function isPairingRequired(error) {
  return Number(error?.status) === 401 && String(error?.code || "") === "pairing_required";
}

function appendDefinition(document, list, label, value) {
  const row = document.createElement("div");
  row.className = "companion-trust__row";
  const term = document.createElement("dt");
  term.textContent = label;
  const detail = document.createElement("dd");
  detail.textContent = value;
  row.append(term, detail);
  list.appendChild(row);
}

/**
 * Coordinate privacy-safe Trust projection and the existing Foundation
 * one-time pairing flow. The controller stores only its fixed safe projection.
 */
export function createTrustController({
  document = globalThis.document,
  api,
  rememberPairedDeviceToken = globalThis.rememberPairedDeviceToken,
  pairedDeviceToken = globalThis.pairedDeviceToken,
  onStateChange = () => {},
  onPairingRequired = () => {},
  onBeforeOpen = () => {},
  onPaired = () => {},
} = {}) {
  if (!api?.getJson || !api?.postJson) throw new TypeError("Trust requires the Companion API.");
  if (typeof rememberPairedDeviceToken !== "function") {
    throw new TypeError("Trust requires Foundation's validated pairing-token helper.");
  }

  let state = projectTrustState();
  let pairingRequired = false;
  let pairingEnabled = true;
  let paired = Boolean(typeof pairedDeviceToken === "function" && pairedDeviceToken());
  let openMode = "";
  let restoreFocus = null;
  let destroyed = false;
  let refreshGeneration = 0;
  const host = document?.getElementById?.("companionSheetHost") || null;
  const backdrop = document?.getElementById?.("companionSheetBackdrop") || null;
  const trustButton = document?.getElementById?.("companionTrustButton") || null;

  const publish = (next) => {
    state = projectTrustState(next);
    onStateChange(state, { pairingEnabled, pairingRequired, paired });
    return state;
  };

  const update = (inputs = {}) => {
    const next = {
      connection: inputs.connection || state.connection,
      status: {
        local: state.connection === "local",
        private_mode: inputs.status?.private_mode ?? state.privateMode,
        provider: inputs.status?.provider || state.provider,
        model: inputs.status?.model || state.model,
        ...inputs.status,
      },
      health: inputs.health,
      trace: inputs.trace,
      camera: inputs.camera || state.camera,
      microphone: inputs.microphone || state.microphone,
      memoryUsed: inputs.memoryUsed ?? state.memoryUsed,
      pendingConfirmation: inputs.pendingConfirmation ?? state.pendingConfirmation,
    };
    if (!hasAuthoritativeCost(inputs)) next.estimatedCost = state.estimatedCost;
    if (!hasAuthoritativeActions(inputs)) next.recentActions = state.recentActions;
    return publish(next);
  };

  const refresh = async () => {
    const generation = ++refreshGeneration;
    const paths = ["/api/pairing/status", "/status", "/healthz", "/nova/v1/health"];
    const results = await Promise.allSettled(paths.map((path) => api.getJson(path)));
    if (destroyed || generation !== refreshGeneration) return state;
    const value = (index) => results[index].status === "fulfilled" ? results[index].value : {};
    const pairingStatusAvailable = results[0].status === "fulfilled";
    const pairing = value(0);
    const status = value(1);
    const healthz = value(2);
    const novaHealth = value(3);
    pairingEnabled = pairing?.enabled !== false;
    pairingRequired = pairingEnabled && pairing?.pairing_required === true;
    paired = pairing?.local_client === true
      || (pairingEnabled
        && !pairingRequired
        && (paired || Boolean(typeof pairedDeviceToken === "function" && pairedDeviceToken())));
    if (!pairingEnabled && pairing?.local_client === false) paired = false;
    const reachable = results.some((result) => result.status === "fulfilled");
    const inputs = {
      connection: !reachable
        ? "offline"
        : (!pairingStatusAvailable
          ? "unknown"
          : (pairing?.local_client === true ? "local" : (pairing?.local_client === false ? "remote" : "unknown"))),
      pairing,
      status,
      health: {
        ...(healthz && typeof healthz === "object" ? healthz : {}),
        ...(novaHealth && typeof novaHealth === "object" ? novaHealth : {}),
      },
      camera: state.camera,
      microphone: state.microphone,
      memoryUsed: state.memoryUsed,
      pendingConfirmation: state.pendingConfirmation,
    };
    if (!hasAuthoritativeCost({ status, health: inputs.health })) inputs.estimatedCost = state.estimatedCost;
    if (!hasAuthoritativeActions({ status })) inputs.recentActions = state.recentActions;
    publish(inputs);
    return state;
  };

  const focusable = () => (
    host
      ? [...host.querySelectorAll("button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])")]
      : []
  );

  const onKeydown = (event) => {
    if (!openMode) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const controls = focusable();
    if (!controls.length) return;
    const first = controls[0];
    const last = controls.at(-1);
    if (!controls.includes(document.activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first).focus?.({ preventScroll: true });
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus?.({ preventScroll: true });
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus?.({ preventScroll: true });
    }
  };

  const beginSheet = (mode, label, invoker) => {
    if (!host || !backdrop || destroyed) return false;
    onBeforeOpen();
    close(false);
    openMode = mode;
    restoreFocus = invoker?.isConnected ? invoker : trustButton;
    host.replaceChildren();
    host.hidden = false;
    backdrop.hidden = false;
    host.classList.add("companion-trust");
    host.setAttribute("aria-label", label);
    trustButton?.setAttribute("aria-expanded", "true");
    document.addEventListener?.("keydown", onKeydown);
    backdrop.addEventListener("click", close);
    return true;
  };

  const close = (restore = true) => {
    if (!openMode) return;
    openMode = "";
    if (host) {
      host.hidden = true;
      host.classList.remove("companion-trust");
      host.replaceChildren();
    }
    if (backdrop) {
      backdrop.hidden = true;
      backdrop.removeEventListener("click", close);
    }
    trustButton?.setAttribute("aria-expanded", "false");
    document?.removeEventListener?.("keydown", onKeydown);
    const target = restoreFocus;
    restoreFocus = null;
    if (restore) target?.focus?.({ preventScroll: true });
  };

  const renderTrustSheet = (invoker = document?.activeElement) => {
    if (!beginSheet("trust", "Nova Trust", invoker)) return false;
    const title = document.createElement("h2");
    title.textContent = "Nova Trust";
    const pairingLine = document.createElement("p");
    pairingLine.className = "companion-trust__summary";
    pairingLine.textContent = trustConnectionLabel(
      state,
      { pairingEnabled, pairingRequired, paired },
    );
    const list = document.createElement("dl");
    list.className = "companion-trust__list";
    appendDefinition(document, list, "Provider", state.provider || "Not reported");
    appendDefinition(document, list, "Model", state.model || "Not reported");
    appendDefinition(document, list, "Private mode", state.privateMode ? "On" : "Off");
    appendDefinition(document, list, "Memory used", state.memoryUsed ? "Yes" : "No");
    appendDefinition(document, list, "Camera", state.camera.active ? "Active" : "Off");
    appendDefinition(document, list, "Image persistence", state.camera.persisted ? "On" : "Off");
    appendDefinition(document, list, "Microphone", state.microphone.active ? "Active" : "Off");
    appendDefinition(document, list, "Confirmation", state.pendingConfirmation ? "Waiting" : "None");
    appendDefinition(
      document,
      list,
      "Estimated remote cost",
      state.estimatedCost === null ? "Not applicable or unavailable" : String(state.estimatedCost),
    );
    const actionsHeading = document.createElement("h3");
    actionsHeading.textContent = "Recent actions";
    const actions = document.createElement("ul");
    actions.className = "companion-trust__actions";
    if (!state.recentActions.length) {
      const item = document.createElement("li");
      item.textContent = "No recent tool actions reported.";
      actions.appendChild(item);
    } else {
      for (const action of state.recentActions) {
        const item = document.createElement("li");
        item.textContent = [action.name, action.state, action.timestamp].filter(Boolean).join(" · ");
        actions.appendChild(item);
      }
    }
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.textContent = "Close";
    closeButton.addEventListener("click", close);
    host.append(title, pairingLine, list, actionsHeading, actions, closeButton);
    focusable()[0]?.focus?.({ preventScroll: true });
    return true;
  };

  const exchangePairing = async ({ deviceName, code } = {}) => {
    const safeCode = String(code || "").replace(/\D/g, "");
    if (!/^\d{6}$/.test(safeCode)) throw new Error("Enter the complete six-digit pairing code.");
    const safeName = safeText(String(deviceName || "").trim(), 80);
    if (!safeName) throw new Error("Enter a name for this device.");
    const response = await api.postJson("/api/pairing/exchange", {
      code: safeCode,
      device_name: safeName,
    });
    rememberPairedDeviceToken(response?.token);
    pairingEnabled = true;
    paired = true;
    pairingRequired = false;
    await refresh();
    onPaired(state);
    return state;
  };

  const renderPairingSheet = (invoker = document?.activeElement) => {
    if (!beginSheet("pairing", "Pair this device", invoker)) return false;
    const title = document.createElement("h2");
    title.textContent = "Pair this device";
    const form = document.createElement("form");
    form.className = "companion-trust__pairing";
    const nameLabel = document.createElement("label");
    nameLabel.textContent = "Device name";
    const name = document.createElement("input");
    name.name = "device_name";
    name.maxLength = 80;
    name.required = true;
    name.autocomplete = "off";
    nameLabel.appendChild(name);
    const codeLabel = document.createElement("label");
    codeLabel.textContent = "Six-digit code";
    const code = document.createElement("input");
    code.name = "pairing_code";
    code.inputMode = "numeric";
    code.pattern = "[0-9]{6}";
    code.maxLength = 6;
    code.required = true;
    code.autocomplete = "one-time-code";
    codeLabel.appendChild(code);
    const statusLine = document.createElement("p");
    statusLine.className = "companion-trust__pairing-status";
    statusLine.setAttribute("role", "status");
    const actions = document.createElement("div");
    actions.className = "companion-trust__pairing-actions";
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Pair";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", close);
    actions.append(submit, cancel);
    form.append(nameLabel, codeLabel, statusLine, actions);
    host.append(title, form);
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const pairingCode = String(code.value || "");
      code.value = "";
      submit.disabled = true;
      statusLine.textContent = "Pairing this device…";
      try {
        await exchangePairing({ deviceName: name.value, code: pairingCode });
        name.value = "";
        statusLine.textContent = "Paired securely. Close this sheet, then choose Retry on your message.";
        submit.remove();
        cancel.textContent = "Close and Retry";
        cancel.focus?.({ preventScroll: true });
      } catch (error) {
        statusLine.textContent = error instanceof Error ? error.message : "Pairing failed.";
        submit.disabled = false;
        code.focus?.({ preventScroll: true });
      }
    });
    name.focus?.({ preventScroll: true });
    return true;
  };

  const requirePairing = () => {
    if (pairingRequired && (openMode === "pairing" || !host)) return;
    pairingRequired = true;
    paired = false;
    onPairingRequired();
    renderPairingSheet();
  };

  const wrapApi = (target) => new Proxy(target, {
    get(apiTarget, property, receiver) {
      const value = Reflect.get(apiTarget, property, receiver);
      if (typeof value !== "function") return value;
      return (...args) => {
        let result;
        try {
          result = Reflect.apply(value, apiTarget, args);
        } catch (error) {
          if (isPairingRequired(error)) requirePairing();
          throw error;
        }
        if (!result || typeof result.then !== "function") return result;
        return result.catch((error) => {
          if (isPairingRequired(error)) requirePairing();
          throw error;
        });
      };
    },
  });

  const trustClick = () => {
    void refresh().finally(() => { renderTrustSheet(trustButton); });
  };
  trustButton?.setAttribute("aria-expanded", "false");
  trustButton?.addEventListener("click", trustClick);

  return {
    close,
    exchangePairing,
    getState: () => state,
    get pairingRequired() { return pairingRequired; },
    open: renderTrustSheet,
    openPairing: renderPairingSheet,
    refresh,
    update,
    wrapApi,
    destroy() {
      if (destroyed) return;
      destroyed = true;
      refreshGeneration += 1;
      close(false);
      trustButton?.removeEventListener("click", trustClick);
    },
  };
}
