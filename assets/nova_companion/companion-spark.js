const CLASSIC_PANELS = new Set([
  "chat", "settings", "display", "dream", "agents", "builder", "memory",
  "tools", "research", "tests", "projects", "files", "logs",
]);

const GROUP_LABELS = Object.freeze({
  see: "See",
  speak: "Speak",
  create: "Create",
  remember: "Remember",
  work: "Work",
  system: "System",
});

const capability = (item) => Object.freeze(item);

export const COMPANION_CAPABILITIES = Object.freeze([
  capability({ id: "chat", group: "speak", label: "Chat with Nova", description: "Start a conversation with Nova.", icon: "✦", mode: "classic", panel: "chat", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "vision", group: "see", label: "See with camera", description: "Let Nova inspect a picture or live frame.", icon: "◉", mode: "companion", panel: "display", requiredCapability: "vision.image_input", requiredTool: "vision.observe", requiredPermission: "camera" }),
  capability({ id: "voice", group: "speak", label: "Speak out loud", description: "Talk with Nova using this device's microphone.", icon: "◌", mode: "companion", panel: "chat", requiredCapability: "audio.input", requiredPermission: "microphone" }),
  capability({ id: "dream", group: "create", label: "Dream Studio", description: "Create a visual idea in Nova Classic.", icon: "✎", mode: "classic", panel: "dream", requiredCapability: "dream_studio.ui_panel", requiredPermission: "none" }),
  capability({ id: "builder", group: "create", label: "Build an app", description: "Open Nova's app builder.", icon: "▣", mode: "classic", panel: "builder", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "memory", group: "remember", label: "Memory", description: "Review what Nova has saved.", icon: "⌁", mode: "classic", panel: "memory", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "agents", group: "work", label: "Agents", description: "Browse Nova's agent library.", icon: "◫", mode: "classic", panel: "agents", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "tools", group: "work", label: "Tools", description: "Review available Nova tools.", icon: "⚒", mode: "classic", panel: "tools", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "research", group: "work", label: "Research", description: "Open Nova's research workspace.", icon: "⌕", mode: "classic", panel: "research", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "projects", group: "work", label: "Projects", description: "Open your saved Nova projects.", icon: "▤", mode: "classic", panel: "projects", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "files", group: "work", label: "Files", description: "Open Nova's file manager.", icon: "▱", mode: "classic", panel: "files", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "settings", group: "system", label: "Settings", description: "Open Nova Classic settings.", icon: "⚙", mode: "classic", panel: "settings", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "tests", group: "system", label: "Checks", description: "Open Nova's test checks.", icon: "✓", mode: "classic", panel: "tests", requiredCapability: "", requiredPermission: "none" }),
  capability({ id: "logs", group: "system", label: "Logs", description: "Open Nova's debug logs.", icon: "≡", mode: "classic", panel: "logs", requiredCapability: "", requiredPermission: "none" }),
]);

function valueAtPath(source, path) {
  return String(path || "").split(".").filter(Boolean).reduce((value, key) => {
    if (!value || typeof value !== "object") return undefined;
    return value[key];
  }, source);
}

function capabilityIsAvailable(value) {
  if (typeof value === "boolean") return value;
  if (!value || typeof value !== "object") return false;
  if (typeof value.available === "boolean") return value.available;
  if (typeof value.enabled === "boolean") return value.enabled;
  if (typeof value.status === "string") return /^(full|available|ready|enabled)$/i.test(value.status);
  return false;
}

function unavailableReason(item) {
  if (item.id === "vision") return "Vision is not available on this Nova server.";
  if (item.id === "voice") return "Voice input is not available on this Nova server.";
  return `${item.label} is not available on this Nova server.`;
}

function serverItemFor(item, serverState) {
  const items = serverState?.items;
  const key = item.requiredTool || item.id;
  return items?.get?.(key) || items?.[key];
}

function toolAvailability(item, serverItem) {
  if (!serverItem || typeof serverItem !== "object") return null;
  if (typeof serverItem.available === "boolean") {
    return { available: serverItem.available, reason: serverItem.reason || (serverItem.available ? "" : unavailableReason(item)) };
  }
  const status = String(serverItem.availability_status || "").toLowerCase();
  const available = status === "available" || (item.id === "vision" && status === "requires_live_input");
  const reason = serverItem.reason || (available ? "" : unavailableReason(item));
  return { available, reason };
}

export function resolveCapabilityAvailability(capabilityItem, serverState = {}) {
  const item = { ...capabilityItem };
  const toolState = toolAvailability(item, serverItemFor(item, serverState));
  if (!item.requiredCapability) return toolState ? { ...item, ...toolState } : { ...item, available: true, reason: "" };
  const capabilityValue = valueAtPath(serverState?.capabilities || serverState, item.requiredCapability);
  const available = capabilityIsAvailable(capabilityValue);
  const reason = typeof capabilityValue?.reason === "string" ? capabilityValue.reason : unavailableReason(item);
  if (capabilityValue !== undefined && !available) return { ...item, available: false, reason };
  if (toolState) return { ...item, ...toolState };
  return { ...item, available, reason: available ? "" : reason };
}

export function resolveSparkActions(serverItems, registry = COMPANION_CAPABILITIES) {
  const items = Array.isArray(serverItems) ? serverItems : [];
  const known = new Map((registry || []).map((item) => [item.id, item]));
  const knownTools = new Map((registry || []).filter((item) => item.requiredTool).map((item) => [item.requiredTool, item]));
  if (!items.length) return [...known.values()];
  return items.flatMap((serverItem) => {
    const registered = knownTools.get(String(serverItem?.name || "")) || known.get(String(serverItem?.id || ""));
    if (!registered) return [];
    const key = registered.requiredTool || registered.id;
    return [resolveCapabilityAvailability(registered, { items: new Map([[key, serverItem]]) })];
  });
}

export function classicPanelUrl(panelName) {
  const panel = String(panelName || "").toLowerCase();
  return CLASSIC_PANELS.has(panel) ? `/classic?panel=${encodeURIComponent(panel)}` : "/classic";
}

function focusableElements(host) {
  if (!host?.querySelectorAll) return [];
  return [...host.querySelectorAll("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])")];
}

export function createSparkController({
  document = globalThis.document,
  button = document?.getElementById("novaSparkButton"),
  host = document?.getElementById("companionSheetHost"),
  backdrop = document?.getElementById("companionSheetBackdrop"),
  registry = COMPANION_CAPABILITIES,
  loadServerState = async () => ({}),
  onCompanionAction = async () => false,
  navigate = (url) => globalThis.location?.assign?.(url),
  voiceCommand = "open nova spark",
} = {}) {
  if (!button || !host || !backdrop) return null;
  let isOpen = false;
  let serverState = {};
  let openCount = 0;
  let hintDismissed = false;
  let destroyed = false;

  const keydown = (event) => {
    if (!isOpen) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key !== "Tab") return;
    const items = focusableElements(host);
    if (!items.length) return;
    const first = items[0];
    const last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const actionFor = (id) => registry.find((item) => item.id === id);
  const activate = async (id) => {
    if (destroyed) return false;
    const action = actionFor(id);
    if (!action) return false;
    const available = resolveCapabilityAvailability(action, serverState);
    if (!available.available) return false;
    try {
      if (available.mode === "classic") {
        const result = await navigate(classicPanelUrl(available.panel));
        if (result === false) return false;
      } else if (await onCompanionAction(available) === false) {
        return false;
      }
    } catch {
      return false;
    }
    if (destroyed) return false;
    close();
    return true;
  };

  const render = () => {
    host.replaceChildren();
    const title = document.createElement("h2");
    title.id = "companionSparkTitle";
    title.textContent = "Nova Spark";
    host.setAttribute("aria-labelledby", title.id);
    host.appendChild(title);
    if (openCount <= 3 && !hintDismissed) {
      const hint = document.createElement("p");
      hint.className = "companion-spark__hint";
      hint.textContent = "Spark opens Nova's available capabilities. You can close it any time with Escape.";
      const dismiss = document.createElement("button");
      dismiss.type = "button";
      dismiss.className = "companion-spark__dismiss";
      dismiss.textContent = "Got it";
      dismiss.addEventListener("click", () => { hintDismissed = true; render(); });
      hint.appendChild(document.createTextNode(" "));
      hint.appendChild(dismiss);
      host.appendChild(hint);
    }
    for (const group of Object.keys(GROUP_LABELS)) {
      const actions = registry.filter((item) => item.group === group).map((item) => resolveCapabilityAvailability(item, serverState));
      if (!actions.length) continue;
      const section = document.createElement("section");
      section.className = "companion-spark__group";
      const heading = document.createElement("h3");
      heading.textContent = GROUP_LABELS[group];
      section.appendChild(heading);
      for (const action of actions) {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "companion-spark__action";
        item.disabled = !action.available;
        item.dataset.sparkAction = action.id;
        const icon = document.createElement("span");
        icon.className = "companion-spark__icon";
        icon.setAttribute("aria-hidden", "true");
        icon.textContent = action.icon;
        const text = document.createElement("span");
        text.className = "companion-spark__text";
        const label = document.createElement("strong");
        label.textContent = action.label;
        const description = document.createElement("small");
        description.textContent = action.available ? action.description : action.reason;
        text.append(label, description);
        item.append(icon, text);
        item.addEventListener("click", () => { void activate(action.id); });
        section.appendChild(item);
      }
      host.appendChild(section);
    }
  };

  const close = () => {
    if (!isOpen) return;
    isOpen = false;
    host.hidden = true;
    backdrop.hidden = true;
    button.setAttribute("aria-expanded", "false");
    document.removeEventListener?.("keydown", keydown);
    button.focus?.({ preventScroll: true });
  };

  const focusFirstSheetControl = () => {
    if (!isOpen || destroyed) return;
    focusableElements(host)[0]?.focus?.({ preventScroll: true });
  };

  const open = async () => {
    if (destroyed || isOpen) return false;
    isOpen = true;
    openCount += 1;
    host.hidden = false;
    backdrop.hidden = false;
    button.setAttribute("aria-expanded", "true");
    document.addEventListener?.("keydown", keydown);
    render();
    focusFirstSheetControl();
    try {
      const loadedState = await loadServerState();
      if (!isOpen || destroyed) return false;
      serverState = loadedState;
      render();
      focusFirstSheetControl();
    } catch {
      if (!isOpen || destroyed) return false;
      render();
      focusFirstSheetControl();
    }
    return true;
  };

  const triggerKeydown = (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      void open();
    }
  };
  const handleVoiceCommand = (command) => {
    if (destroyed) return false;
    if (String(command || "").trim().toLowerCase() !== String(voiceCommand).trim().toLowerCase()) return false;
    void open();
    return true;
  };

  const triggerClick = () => { void open(); };
  button.addEventListener("click", triggerClick);
  button.addEventListener("keydown", triggerKeydown);
  backdrop.addEventListener("click", close);
  return {
    open,
    close,
    activate,
    handleVoiceCommand,
    get isOpen() { return isOpen; },
    destroy() {
      if (destroyed) return;
      destroyed = true;
      close();
      button.removeEventListener("click", triggerClick);
      button.removeEventListener("keydown", triggerKeydown);
      backdrop.removeEventListener("click", close);
    },
  };
}
