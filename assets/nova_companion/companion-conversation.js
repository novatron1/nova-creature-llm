const elementDocuments = new WeakMap();

function documentFor(element) {
  const document = elementDocuments.get(element) || element?.ownerDocument || globalThis.document;
  if (!document?.createElement) throw new TypeError("A document-backed conversation timeline is required.");
  return document;
}

function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : "";
  } catch {
    return "";
  }
}

function appendSafeText(container, text, document) {
  const source = String(text || "");
  const urlPattern = /\bhttps?:\/\/[^\s<>"']+/gi;
  let cursor = 0;
  for (const match of source.matchAll(urlPattern)) {
    const index = match.index ?? 0;
    if (index > cursor) {
      const span = document.createElement("span");
      span.textContent = source.slice(cursor, index);
      container.appendChild(span);
    }
    const href = safeHttpUrl(match[0]);
    if (href) {
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.target = "_blank";
      anchor.rel = "noopener noreferrer";
      anchor.textContent = match[0];
      container.appendChild(anchor);
    } else {
      const span = document.createElement("span");
      span.textContent = match[0];
      container.appendChild(span);
    }
    cursor = index + match[0].length;
  }
  if (cursor < source.length || !source) {
    const span = document.createElement("span");
    span.textContent = source.slice(cursor);
    container.appendChild(span);
  }
}

function renderMessageText(container, text, document) {
  container.textContent = "";
  appendSafeText(container, text, document);
}

function roleLabel(role) {
  return ({ user: "You", assistant: "Nova", tool: "Nova tool", system: "System" })[role] || "Nova";
}

export function appendMessage(timeline, message = {}) {
  const document = documentFor(timeline);
  const role = ["user", "assistant", "tool", "system"].includes(message.role) ? message.role : "assistant";
  const article = document.createElement("article");
  article.className = `companion-message companion-message--${role}`;
  article.dataset.messageId = String(message.id || "");
  article.dataset.role = role;
  article.dataset.status = String(message.status || "completed");

  const label = document.createElement("p");
  label.className = "companion-message__role";
  label.textContent = roleLabel(role);
  article.appendChild(label);

  const body = document.createElement("div");
  body.className = "companion-message__text";
  body.dataset.messageText = "";
  renderMessageText(body, message.text, document);
  article.appendChild(body);

  if (message.answerStatus) {
    const status = document.createElement("p");
    status.className = "companion-message__answer-status";
    status.dataset.answerStatus = "";
    status.textContent = String(message.answerStatus);
    article.appendChild(status);
  }
  timeline.appendChild(article);
  elementDocuments.set(article, document);
  return article;
}

export function beginStreamingMessage(timeline, responseId) {
  return appendMessage(timeline, {
    id: String(responseId || ""), role: "assistant", text: "", status: "streaming", answerStatus: null, artifact: null,
  });
}

export function appendStreamingDelta(element, delta) {
  const document = documentFor(element);
  const body = element?.querySelector?.("[data-message-text]");
  if (!body) return;
  const text = `${element.dataset.rawText || ""}${typeof delta === "string" ? delta : ""}`;
  element.dataset.rawText = text;
  element.dataset.status = "streaming";
  renderMessageText(body, text, document);
}
