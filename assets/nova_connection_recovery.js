(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.createNovaConnectionRecovery = api.createNovaConnectionRecovery;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  function createNovaConnectionRecovery(options = {}) {
    const windowObject = options.windowObject || globalThis.window;
    const documentObject = options.documentObject || globalThis.document;
    const reconnect = options.reconnect;
    const setTimeoutFn = options.setTimeoutFn || globalThis.setTimeout.bind(globalThis);
    const clearTimeoutFn = options.clearTimeoutFn || globalThis.clearTimeout.bind(globalThis);
    const delayMs = Number.isFinite(options.delayMs) ? options.delayMs : 250;
    let timer = null;
    let inFlight = null;
    let started = false;

    async function run(reason) {
      timer = null;
      if (documentObject && documentObject.hidden) return false;
      if (inFlight) return inFlight;
      inFlight = Promise.resolve()
        .then(() => reconnect(reason))
        .catch(() => false)
        .finally(() => { inFlight = null; });
      return inFlight;
    }

    function schedule(reason) {
      if (documentObject && documentObject.hidden) return;
      if (timer !== null) clearTimeoutFn(timer);
      timer = setTimeoutFn(() => run(reason), delayMs);
    }

    function onVisibilityChange() {
      if (!documentObject.hidden) schedule('visibilitychange');
    }

    function start() {
      if (started) return;
      started = true;
      documentObject.addEventListener('visibilitychange', onVisibilityChange);
      windowObject.addEventListener('pageshow', () => schedule('pageshow'));
      windowObject.addEventListener('online', () => schedule('online'));
      windowObject.addEventListener('focus', () => schedule('focus'));
    }

    return {run, schedule, start};
  }

  return {createNovaConnectionRecovery};
});
