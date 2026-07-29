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
  maxHeight = 192,
  onSubmit = async () => {},
  onStop = async () => {},
} = {}) {
  if (!form || !input || !sendButton) throw new TypeError("Composer elements are required.");
  let active = false;

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
  const onInput = () => { resize(); };
  const onSendClick = (event) => {
    if (!active) return;
    event.preventDefault();
    void stop();
  };

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
    setTransientText(text) {
      input.value = String(text || "");
      resize();
    },
    restoreFocus({ userInitiated = false } = {}) {
      const target = userInitiated ? input : sendButton;
      target.focus({ preventScroll: true });
    },
    destroy() {
      form.removeEventListener("submit", onFormSubmit);
      input.removeEventListener("keydown", onKeyDown);
      input.removeEventListener("input", onInput);
      sendButton.removeEventListener("click", onSendClick);
    },
  };
}
