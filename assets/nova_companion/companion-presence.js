const PHASE_PRESENTATION = {
  booting: { label: "Nova is connecting", color: "violet", motion: "booting", busy: true },
  submitting: { label: "Nova is sending", color: "cyan", motion: "sending", busy: true },
  thinking: { label: "Nova is thinking", color: "violet", motion: "thinking", busy: true },
  acting: { label: "Nova is acting", color: "cyan", motion: "acting", busy: true },
  responding: { label: "Nova is responding", color: "cyan", motion: "responding", busy: true },
  completed: { label: "Nova is here", color: "success", motion: "resting", busy: false },
  offline: { label: "Nova is offline", color: "warning", motion: "offline", busy: false },
  failed: { label: "Nova could not respond", color: "danger", motion: "error", busy: false },
  cancelled: { label: "Nova stopped responding", color: "text-muted", motion: "resting", busy: false },
};

export function presenceViewModel(state = {}, reducedMotion = false) {
  const voice = state.voice || {};
  const phase = PHASE_PRESENTATION[state.phase] ? state.phase : "booting";
  const presentation = PHASE_PRESENTATION[phase];
  const toolName = state.activeTool?.status === "started" && state.activeTool.name;
  const toolProposed = state.activeTool?.status === "proposed";
  const listening = voice.listening === true;
  const speaking = voice.speaking === true;
  const voicePresentation = listening
    ? { phase: "listening", label: "Nova is listening", color: "cyan", motion: "listening", busy: true }
    : speaking
      ? { phase: "speaking", label: "Nova is speaking", color: "cyan", motion: "responding", busy: true }
      : null;
  const shown = voicePresentation || presentation;
  return Object.freeze({
    phase: voicePresentation?.phase || phase,
    label: voicePresentation?.label || (toolProposed ? "Nova is proposing an action" : toolName ? `Nova is using ${toolName}` : presentation.label),
    color: shown.color,
    motion: reducedMotion ? "none" : shown.motion,
    size: Number(state.conversationTurnCount) > 0 ? "compact" : "full",
    busy: shown.busy,
  });
}

export function renderPresence(elements, viewModel) {
  const { presence, face, greeting, liveStatus } = elements || {};
  if (!presence || !face || !greeting || !viewModel) return;
  presence.dataset.phase = viewModel.phase;
  presence.dataset.presenceSize = viewModel.size;
  presence.setAttribute("aria-busy", String(viewModel.busy));
  face.dataset.motion = viewModel.motion;
  face.dataset.color = viewModel.color;
  greeting.textContent = viewModel.label;
  if (liveStatus) liveStatus.textContent = viewModel.label;
}
