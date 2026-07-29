export const NOVA_COMPANION_DRAFT_KEY = "nova_companion_draft_v1";

function defaultStorage() {
  return globalThis.localStorage;
}

function setControlState(sendButton, active) {
  if (!sendButton) return;
  sendButton.type = active ? "button" : "submit";
  sendButton.textContent = active ? "Stop" : "↑";
  sendButton.setAttribute("aria-label", active ? "Stop Nova" : "Send message");
  sendButton.dataset.mode = active ? "stop" : "send";
}

export function createComposerController({
  form,
  input,
  sendButton,
  storage = defaultStorage(),
  draftKey = NOVA_COMPANION_DRAFT_KEY,
  maxHeight = 192,
  onSubmit = async () => {},
  onStop = async () => {},
} = {}) {
  if (!form || !input || !sendButton) throw new TypeError("Composer elements are required.");
  let active = false;

  const persistDraft = () => {
    const draft = String(input.value || "");
    if (draft) storage?.setItem?.(draftKey, draft);
    else storage?.removeItem?.(draftKey);
  };
  const resize = () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(Math.max(Number(input.scrollHeight) || 44, 44), maxHeight)}px`;
  };
  const setRequestActive = (next) => {
    active = Boolean(next);
    input.disabled = active;
    setControlState(sendButton, active);
  };
  const markRequestAccepted = () => {
    storage?.removeItem?.(draftKey);
    input.value = "";
    resize();
  };
  const submit = async () => {
    const text = String(input.value || "").trim();
    if (active || !text) return false;
    setRequestActive(true);
    try {
      await onSubmit(text, { markRequestAccepted });
      return true;
    } finally {
      setRequestActive(false);
    }
  };
  const stop = async () => {
    if (!active) return false;
    await onStop();
    return true;
  };
  const onFormSubmit = (event) => {
    event.preventDefault();
    void submit();
  };
  const onKeyDown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };
  const onInput = () => { persistDraft(); resize(); };
  const onSendClick = (event) => {
    if (!active) return;
    event.preventDefault();
    void stop();
  };

  const draft = storage?.getItem?.(draftKey);
  if (draft && !input.value) input.value = draft;
  resize();
  setControlState(sendButton, false);
  form.addEventListener("submit", onFormSubmit);
  input.addEventListener("keydown", onKeyDown);
  input.addEventListener("input", onInput);
  sendButton.addEventListener("click", onSendClick);

  return {
    submit,
    stop,
    markRequestAccepted,
    setRequestActive,
    resize,
    restoreFocus() { input.focus({ preventScroll: true }); },
    destroy() {
      form.removeEventListener("submit", onFormSubmit);
      input.removeEventListener("keydown", onKeyDown);
      input.removeEventListener("input", onInput);
      sendButton.removeEventListener("click", onSendClick);
    },
  };
}
