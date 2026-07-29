const safeOrigin = () => globalThis.window?.location?.origin || "";
const TIMEOUT_REASON = "nova_timeout";
const CANCELLED_REASON = "nova_cancelled";

export function createRequestId() {
  if (globalThis.crypto?.randomUUID) return `req_${globalThis.crypto.randomUUID()}`;
  return `req_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 12)}`;
}

export function parseSseBlock(block) {
  const data = String(block || "")
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n")
    .trim();
  if (!data || data === "[DONE]") return null;
  return JSON.parse(data);
}

export class NovaApiError extends Error {
  constructor(message = "Nova could not complete that request.", {
    status = 0,
    code = "request_failed",
    partialText = "",
    requestId = "",
  } = {}) {
    super(message);
    this.name = "NovaApiError";
    this.status = Number(status) || 0;
    this.code = String(code || "request_failed");
    this.partialText = String(partialText || "");
    this.requestId = String(requestId || "");
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      status: this.status,
      code: this.code,
      partialText: this.partialText,
      requestId: this.requestId,
    };
  }
}

const messageFor = (code, status) => {
  if (code === "pairing_required") return "Pair this device before using Nova.";
  if (code === "cancelled") return "The Nova request was cancelled.";
  if (code === "timeout") return "Nova request timed out.";
  if (code === "stream_incomplete") return "Nova's response stream ended before completion.";
  if (status === 401) return "This device is not authorized to use Nova.";
  if (status >= 500) return "Nova is temporarily unavailable.";
  return "Nova could not complete that request.";
};

const eventType = (event) => String(event?.event_type || event?.type || "");
const deltaFor = (event) => {
  if (typeof event?.delta === "string") return event.delta;
  if (typeof event?.response?.output_text?.delta === "string") return event.response.output_text.delta;
  return "";
};

export class NovaCompanionApi {
  constructor({
    baseUrl = safeOrigin(),
    fetchImpl = globalThis.fetch?.bind(globalThis),
    authHeaders = globalThis.authHeaders || ((extra) => ({ ...extra })),
    requestTimeoutMs = 120000,
  } = {}) {
    if (typeof fetchImpl !== "function") throw new TypeError("A fetch implementation is required.");
    this.baseUrl = String(baseUrl || "").replace(/\/$/, "");
    this.fetchImpl = fetchImpl;
    this.authHeaders = authHeaders;
    this.requestTimeoutMs = requestTimeoutMs;
    this.activeStreams = new Map();
  }

  getStatus({ signal } = {}) { return this.getJson("/status", { signal }); }
  getHealth({ signal } = {}) { return this.getJson("/healthz", { signal }); }
  chat(body, { signal } = {}) { return this.postJson("/nova/v1/chat", body, { signal }); }
  postPermissionCommand(text, { signal } = {}) { return this.postJson("/api/chat", { text: String(text || "") }, { signal }); }
  postVision(body, { signal } = {}) { return this.postJson("/api/vision", body, { signal }); }
  postTts(text, { signal, force = false } = {}) { return this.postJson("/api/tts", { text, force: Boolean(force) }, { signal }); }

  async getJson(path, { signal } = {}) {
    try {
      const response = await this._fetch(path, { method: "GET", signal });
      return await this._jsonResponse(response);
    } catch (error) {
      throw this._safeTransportError(error, signal);
    }
  }

  async postJson(path, body, { signal } = {}) {
    try {
      const response = await this._fetch(path, {
        method: "POST",
        body: JSON.stringify(body),
        signal,
      });
      return await this._jsonResponse(response);
    } catch (error) {
      throw this._safeTransportError(error, signal);
    }
  }

  async cancel(requestId) {
    const id = String(requestId || "");
    if (!id) throw new NovaApiError("A Nova request ID is required.", { code: "invalid_request" });
    const controller = this.activeStreams.get(id);
    try {
      return await this.postJson(`/nova/v1/cancel/${encodeURIComponent(id)}`, {});
    } finally {
      controller?.abort(CANCELLED_REASON);
    }
  }

  async streamChat({ text, requestId = createRequestId(), clientId, conversationId, sessionId, history = [] }, callbacks = {}) {
    const id = String(requestId || createRequestId());
    const controller = new AbortController();
    const detachExternalAbort = this._forwardAbort(callbacks.signal, controller);
    const timeout = this._startTimeout(controller);
    const body = {
      model: "nova",
      text,
      stream: true,
      request_id: id,
      client_id: clientId,
      conversation_id: conversationId,
      session_id: sessionId,
      conversation_history: history,
    };
    let textSoFar = "";
    let completed = false;
    let reader = null;
    const seenDeltaEvents = new Set();
    this.activeStreams.set(id, controller);
    try {
      const response = await this._fetch("/nova/v1/chat", {
        method: "POST",
        body: JSON.stringify(body),
        signal: controller.signal,
        timeout: false,
      });
      if (!response.ok) await this._throwResponseError(response, { requestId: id });
      if (!response.body?.getReader) throw new NovaApiError(messageFor("stream_incomplete"), {
        code: "stream_incomplete", requestId: id,
      });

      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let trace = {};
      const consumeBlock = (block) => {
        if (completed) return;
        const event = parseSseBlock(block);
        if (!event) return;
        callbacks.onEvent?.(event);
        const type = eventType(event);
        if (type === "error" || event.error) {
          const error = event.error || {};
          throw new NovaApiError(messageFor(error.code || error.type || "request_failed"), {
            code: error.code || error.type || "request_failed", partialText: textSoFar, requestId: id,
          });
        }
        const delta = deltaFor(event);
        const sequence = event.sequence ?? event.sequence_number;
        const eventKey = sequence === undefined || sequence === null
          ? ""
          : `${event.response_id || event.response?.id || id}:${sequence}`;
        if (delta && (!eventKey || !seenDeltaEvents.has(eventKey))) {
          if (eventKey) seenDeltaEvents.add(eventKey);
          textSoFar += delta;
          callbacks.onDelta?.(delta, event);
        }
        if (event.done === true && !completed) {
          completed = true;
          trace = event.metadata?.trace || event.trace || {};
          callbacks.onDone?.(event);
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = buffer.replace(/\r\n/g, "\n");
        let boundary;
        while ((boundary = buffer.indexOf("\n\n")) !== -1) {
          const block = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          consumeBlock(block);
        }
      }
      buffer += decoder.decode();
      buffer = buffer.replace(/\r\n/g, "\n");
      if (buffer.trim()) consumeBlock(buffer);
      if (!completed) throw new NovaApiError(messageFor("stream_incomplete"), {
        code: "stream_incomplete", partialText: textSoFar, requestId: id,
      });
      return { text: textSoFar, trace };
    } catch (error) {
      if (error instanceof NovaApiError) throw error;
      const code = controller.signal.reason === TIMEOUT_REASON
        ? "timeout"
        : (controller.signal.aborted ? "cancelled" : "stream_interrupted");
      throw new NovaApiError(messageFor(code), { code, partialText: textSoFar, requestId: id });
    } finally {
      if (reader) {
        try { await reader.cancel(); } catch { /* preserve the primary result or error */ }
      }
      clearTimeout(timeout);
      detachExternalAbort();
      if (this.activeStreams.get(id) === controller) this.activeStreams.delete(id);
    }
  }

  _url(path) { return `${this.baseUrl}${path}`; }

  _startTimeout(controller) {
    return setTimeout(() => controller.abort(TIMEOUT_REASON), this.requestTimeoutMs);
  }

  _forwardAbort(signal, controller) {
    if (!signal) return () => {};
    const abort = () => controller.abort(CANCELLED_REASON);
    if (signal.aborted) abort();
    else signal.addEventListener("abort", abort, { once: true });
    return () => signal.removeEventListener("abort", abort);
  }

  async _fetch(path, { method, body, signal, timeout = true }) {
    const controller = timeout ? new AbortController() : null;
    const activeSignal = controller?.signal || signal;
    const detach = controller ? this._forwardAbort(signal, controller) : () => {};
    const timeoutId = controller ? this._startTimeout(controller) : null;
    try {
      const headers = this.authHeaders({
        Accept: "application/json",
        ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      });
      return await this.fetchImpl(this._url(path), { method, headers, ...(body === undefined ? {} : { body }), signal: activeSignal });
    } catch (error) {
      if (controller?.signal.reason === TIMEOUT_REASON) {
        throw new NovaApiError(messageFor("timeout"), { code: "timeout" });
      }
      if (controller?.signal.aborted) {
        throw new NovaApiError(messageFor("cancelled"), { code: "cancelled" });
      }
      throw error;
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      detach();
    }
  }

  async _jsonResponse(response) {
    if (!response.ok) await this._throwResponseError(response);
    try {
      return await response.json();
    } catch {
      throw new NovaApiError("Nova returned an invalid response.", { code: "invalid_response" });
    }
  }

  _safeTransportError(error, signal) {
    if (error instanceof NovaApiError) return error;
    const code = signal?.aborted ? "cancelled" : "network_error";
    return new NovaApiError(messageFor(code), { code });
  }

  async _throwResponseError(response, { requestId = "", partialText = "" } = {}) {
    let payload = {};
    try { payload = await response.json(); } catch { /* the HTTP status is enough */ }
    const detail = payload?.error && typeof payload.error === "object" ? payload.error : payload;
    const code = String(detail?.code || payload?.code || "request_failed");
    throw new NovaApiError(messageFor(code, response.status), {
      status: response.status, code, partialText, requestId,
    });
  }
}
