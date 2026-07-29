import assert from "node:assert/strict";
import test from "node:test";
import { readFile } from "node:fs/promises";

const source = (path) => new URL(path, import.meta.url);
const importModule = async (path) => {
  const code = await readFile(source(path), "utf8");
  return import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
};

const apiModule = await importModule("../../assets/nova_companion/companion-api.js");
const { NovaApiError, NovaCompanionApi, parseSseBlock } = apiModule;

const encoder = new TextEncoder();
const makeResponse = ({ status = 200, body, json = {}, headers = {} } = {}) => ({
  ok: status >= 200 && status < 300,
  status,
  body,
  headers: { get: (name) => headers[name.toLowerCase()] || headers[name] || null },
  json: async () => json,
});

const makeStreamingFetch = (chunks, { status = 200 } = {}) => async () => {
  let index = 0;
  return makeResponse({
    status,
    body: {
      getReader: () => ({
        read: async () => index < chunks.length
          ? { value: encoder.encode(chunks[index++]), done: false }
          : { value: undefined, done: true },
        cancel: async () => {},
      }),
    },
  });
};

const makeJsonFetch = (status, json) => async () => makeResponse({ status, json });

test("SSE parsing ignores heartbeats and returns deltas exactly once across CRLF fragments", async () => {
  const fetchImpl = makeStreamingFetch([
    'event: response.heartbeat\r\ndata: {"event_type":"response.heartbeat"}\r\n\r\n',
    'event: response.delta\r\ndata: {"event_type":"response.delta","response_id":"resp-1","sequence":1,"delta":"Hel',
    'lo "}\r\n\r\nevent: response.delta\r\ndata: {"event_type":"response.delta","response_id":"resp-1","sequence":1,"delta":"Hello "}\r\n\r\nevent: response.delta\r\ndata: {"event_type":"response.delta","delta":"there"}\r\n\r\n',
    'event: response.completed\r\ndata: {"event_type":"response.completed","done":true,"metadata":{"trace":{"source":"nova_core"}}}\r\n\r\n',
    "data: [DONE]\r\n\r\n",
  ]);
  const deltas = [];
  const api = new NovaCompanionApi({ fetchImpl, authHeaders: (extra) => extra });

  const result = await api.streamChat(
    { text: "Hi", requestId: "req-1" },
    { onDelta: (value) => deltas.push(value) },
  );

  assert.deepEqual(deltas, ["Hello ", "there"]);
  assert.equal(result.text, "Hello there");
  assert.equal(result.trace.source, "nova_core");
});

test("stream chat sends only the native Companion request fields", async () => {
  const calls = [];
  const api = new NovaCompanionApi({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return makeResponse({ body: { getReader: () => ({ read: async () => ({ done: true }), cancel: async () => {} }) } });
    },
    authHeaders: (extra) => extra,
  });

  await assert.rejects(
    () => api.streamChat({ text: "Hi", requestId: "req-2", clientId: "client", conversationId: "conv", sessionId: "session", history: [{ role: "user", content: "Earlier" }] }),
    (error) => error.code === "stream_incomplete",
  );
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    model: "nova", text: "Hi", stream: true, request_id: "req-2", client_id: "client",
    conversation_id: "conv", session_id: "session", recent_messages: [{ role: "user", content: "Earlier" }],
  });
});

test("one SSE block returns one parsed event", () => {
  assert.deepEqual(
    parseSseBlock('event: response.delta\ndata: {"event_type":"response.delta","delta":"Hi"}'),
    { event_type: "response.delta", delta: "Hi" },
  );
  assert.equal(parseSseBlock("data: [DONE]"), null);
});

test("pairing errors retain a machine-readable code", async () => {
  const api = new NovaCompanionApi({
    fetchImpl: makeJsonFetch(401, { code: "pairing_required", error: "Pair first" }),
    authHeaders: (extra) => extra,
  });
  await assert.rejects(() => api.getStatus(), (error) => error.code === "pairing_required" && error.status === 401);
});

test("camera permission commands use the authenticated legacy /api/chat route", async () => {
  const calls = [];
  const api = new NovaCompanionApi({
    fetchImpl: async (url, options) => {
      calls.push({ url, options });
      return makeResponse({ json: { ok: true } });
    },
    authHeaders: (extra) => ({ ...extra, Authorization: "Bearer paired-device" }),
  });
  await api.postPermissionCommand("allow camera");
  assert.equal(calls[0].url, "/api/chat");
  assert.equal(calls[0].options.headers.Authorization, "Bearer paired-device");
  assert.deepEqual(JSON.parse(calls[0].options.body), { text: "allow camera" });
});

test("transport failures from JSON endpoints are serialized without request secrets", async () => {
  const secret = "Bearer no-leak prompt-image-base64";
  const api = new NovaCompanionApi({
    fetchImpl: async () => { throw new Error(secret); },
    authHeaders: () => ({ Authorization: secret }),
  });

  await assert.rejects(() => api.getHealth(), (error) => {
    assert.ok(error instanceof NovaApiError);
    assert.equal(error.code, "network_error");
    assert.equal(JSON.stringify(error).includes(secret), false);
    return true;
  });
});

test("the final unterminated SSE block is consumed once", async () => {
  const deltas = [];
  const api = new NovaCompanionApi({
    fetchImpl: makeStreamingFetch([
      'event: response.delta\ndata: {"event_type":"response.delta","delta":"final"}\n\n',
      'event: response.completed\ndata: {"event_type":"response.completed","done":true,"metadata":{"trace":{"route":"native"}}}',
    ]),
    authHeaders: (extra) => extra,
  });

  const result = await api.streamChat({ text: "Hi", requestId: "req-final" }, { onDelta: (value) => deltas.push(value) });
  assert.deepEqual(deltas, ["final"]);
  assert.equal(result.text, "final");
  assert.equal(result.trace.route, "native");
});

test("SSE framing survives a CRLF delimiter split across chunks", async () => {
  const deltas = [];
  const api = new NovaCompanionApi({
    fetchImpl: makeStreamingFetch([
      'data: {"event_type":"response.delta","delta":"split"}\r',
      "\n\r",
      "\n",
      'data: {"event_type":"response.completed","done":true}\r\n\r\n',
    ]),
    authHeaders: (extra) => extra,
  });

  const result = await api.streamChat({ text: "Hi", requestId: "req-crlf" }, { onDelta: (value) => deltas.push(value) });
  assert.deepEqual(deltas, ["split"]);
  assert.equal(result.text, "split");
});

test("JSON request deadline expiry has a safe timeout code", async () => {
  const api = new NovaCompanionApi({
    requestTimeoutMs: 5,
    fetchImpl: async (_url, options) => new Promise((_, reject) => {
      options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    }),
    authHeaders: (extra) => extra,
  });

  await assert.rejects(
    () => api.getHealth(),
    (error) => error.code === "timeout" && error.message === "Nova request timed out.",
  );
});

test("stream deadline expiry has a safe timeout code and preserves partial text", async () => {
  const api = new NovaCompanionApi({
    requestTimeoutMs: 5,
    fetchImpl: async (_url, options) => makeResponse({ body: { getReader: () => ({
      read: () => new Promise((_, reject) => {
        options.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      }),
      cancel: async () => {},
    }) } }),
    authHeaders: (extra) => extra,
  });

  await assert.rejects(
    () => api.streamChat({ text: "Hi", requestId: "req-timeout" }),
    (error) => error.code === "timeout" && error.partialText === "" && error.requestId === "req-timeout",
  );
});

test("stream reader is cancelled when SSE parsing fails", async () => {
  let cancelled = 0;
  const api = new NovaCompanionApi({
    fetchImpl: async () => makeResponse({ body: { getReader: () => ({
      read: async () => ({ value: encoder.encode("data: not-json\n\n"), done: false }),
      cancel: async () => { cancelled += 1; },
    }) } }),
    authHeaders: (extra) => extra,
  });

  await assert.rejects(() => api.streamChat({ text: "Hi", requestId: "req-parser" }));
  assert.equal(cancelled, 1);
});

test("stream reader is cancelled when a delta callback fails", async () => {
  let cancelled = 0;
  const api = new NovaCompanionApi({
    fetchImpl: async () => makeResponse({ body: { getReader: () => ({
      read: async () => ({ value: encoder.encode('data: {"event_type":"response.delta","delta":"Hi"}\n\n'), done: false }),
      cancel: async () => { cancelled += 1; },
    }) } }),
    authHeaders: (extra) => extra,
  });

  await assert.rejects(() => api.streamChat({ text: "Hi", requestId: "req-callback" }, { onDelta: () => { throw new Error("callback failure"); } }));
  assert.equal(cancelled, 1);
});

test("stream reader is cancelled when read fails", async () => {
  let cancelled = 0;
  const api = new NovaCompanionApi({
    fetchImpl: async () => makeResponse({ body: { getReader: () => ({
      read: async () => { throw new Error("read failure"); },
      cancel: async () => { cancelled += 1; },
    }) } }),
    authHeaders: (extra) => extra,
  });

  await assert.rejects(() => api.streamChat({ text: "Hi", requestId: "req-read" }));
  assert.equal(cancelled, 1);
});

test("terminal done permits no further delta text or done callbacks", async () => {
  const deltas = [];
  let doneCalls = 0;
  const api = new NovaCompanionApi({
    fetchImpl: makeStreamingFetch([
      'data: {"event_type":"response.delta","delta":"before"}\n\n',
      'data: {"event_type":"response.completed","done":true}\n\n',
      'data: {"event_type":"response.delta","delta":"after"}\n\n',
      'data: {"event_type":"response.completed","done":true}\n\n',
    ]),
    authHeaders: (extra) => extra,
  });

  const result = await api.streamChat({ text: "Hi", requestId: "req-terminal" }, {
    onDelta: (value) => deltas.push(value),
    onDone: () => { doneCalls += 1; },
  });
  assert.equal(result.text, "before");
  assert.deepEqual(deltas, ["before"]);
  assert.equal(doneCalls, 1);
});

test("a stream without a final done event fails without automatically retrying", async () => {
  let calls = 0;
  const api = new NovaCompanionApi({
    fetchImpl: async () => {
      calls += 1;
      return makeResponse({ body: { getReader: () => ({ read: async () => ({ done: true }), cancel: async () => {} }) } });
    },
    authHeaders: (extra) => extra,
  });

  await assert.rejects(
    () => api.streamChat({ text: "Hi", requestId: "req-incomplete" }),
    (error) => error instanceof NovaApiError && error.code === "stream_incomplete" && error.requestId === "req-incomplete",
  );
  assert.equal(calls, 1);
});

test("stream errors preserve partial text while serializing only safe error details", async () => {
  const secret = "Bearer never-expose-this prompt:image-base64";
  let reads = 0;
  const api = new NovaCompanionApi({
    fetchImpl: async () => makeResponse({
      body: { getReader: () => ({
        read: async () => {
          reads += 1;
          if (reads === 1) return { value: encoder.encode('data: {"event_type":"response.delta","delta":"partial"}\n\n'), done: false };
          throw new Error(secret);
        },
        cancel: async () => {},
      }) },
    }),
    authHeaders: () => ({ Authorization: secret }),
  });

  await assert.rejects(
    () => api.streamChat({ text: secret, requestId: "req-safe" }),
    (error) => {
      assert.equal(error.partialText, "partial");
      assert.equal(error.requestId, "req-safe");
      const serialized = JSON.stringify(error);
      assert.equal(serialized.includes(secret), false);
      assert.equal(serialized.includes("stack"), false);
      assert.equal(serialized.includes("partial"), true);
      return true;
    },
  );
});

test("cancel posts the server request id before locally aborting its active stream", async () => {
  const events = [];
  let rejectRead;
  const api = new NovaCompanionApi({
    fetchImpl: async (url, options) => {
      events.push(url);
      if (url.endsWith("/nova/v1/chat")) {
        options.signal.addEventListener("abort", () => {
          events.push("aborted");
          rejectRead(new DOMException("Aborted", "AbortError"));
        }, { once: true });
        return makeResponse({ body: { getReader: () => ({
          read: () => new Promise((_, reject) => { rejectRead = reject; }),
          cancel: async () => {},
        }) } });
      }
      return makeResponse({ json: { ok: true, request_id: "req-22" } });
    },
    authHeaders: (extra) => extra,
  });
  const stream = api.streamChat({ text: "Hi", requestId: "req-22" });
  await new Promise((resolve) => setImmediate(resolve));
  await api.cancel("req-22");
  await assert.rejects(stream, (error) => error.code === "cancelled" && error.requestId === "req-22");
  assert.deepEqual(events, ["/nova/v1/chat", "/nova/v1/cancel/req-22", "aborted"]);
});
