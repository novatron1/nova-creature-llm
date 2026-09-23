(function (root) {
  'use strict';

  const STORAGE_KEY = 'nova_saved_conversations_v1';
  const SCHEMA_VERSION = 1;
  const MAX_RECORDS = 60;
  const MAX_MESSAGES = 48;
  const MAX_CONTENT = 4000;
  const MAX_TITLE = 100;

  function text(value, limit) {
    return String(value == null ? '' : value).replace(/\s+/g, ' ').trim().slice(0, limit);
  }

  function iso(value, fallback) {
    const candidate = String(value || '').trim();
    if (candidate && !Number.isNaN(Date.parse(candidate))) return candidate;
    return fallback || new Date().toISOString();
  }

  function validMessages(value) {
    if (!Array.isArray(value)) return [];
    return value
      .filter((item) => item && (item.role === 'user' || item.role === 'assistant') && typeof item.content === 'string')
      .map((item) => ({ role: item.role, content: item.content.trim().slice(0, MAX_CONTENT) }))
      .filter((item) => item.content)
      .slice(-MAX_MESSAGES);
  }

  function titleFrom(messages, fallback) {
    const firstUser = messages.find((item) => item.role === 'user');
    return text(fallback || firstUser?.content || 'New conversation', MAX_TITLE) || 'New conversation';
  }

  function normalize(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
    const conversationId = text(value.conversation_id || value.id, 160);
    if (!conversationId) return null;
    const messages = validMessages(value.messages);
    const now = new Date().toISOString();
    const title = titleFrom(messages, value.title);
    const firstUser = messages.find((item) => item.role === 'user');
    return {
      schema_version: SCHEMA_VERSION,
      conversation_id: conversationId,
      title,
      preview: text(value.preview || firstUser?.content || 'No messages yet', 180),
      created_at: iso(value.created_at, now),
      updated_at: iso(value.updated_at, now),
      saved: value.saved === true,
      archived: value.archived === true,
      summary: value.summary && typeof value.summary === 'object' && !Array.isArray(value.summary) ? value.summary : null,
      messages,
      message_count: messages.length,
    };
  }

  function load(storage) {
    try {
      const raw = storage?.getItem(STORAGE_KEY);
      if (!raw) return [];
      const payload = JSON.parse(raw);
      const rows = Array.isArray(payload) ? payload : payload?.conversations;
      if (!Array.isArray(rows)) return [];
      return rows.map(normalize).filter(Boolean)
        .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
    } catch (_error) {
      return [];
    }
  }

  function write(storage, records) {
    const normalized = (Array.isArray(records) ? records : [])
      .map(normalize)
      .filter(Boolean)
      .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at))
      .slice(0, MAX_RECORDS);
    try {
      if (!normalized.length) storage?.removeItem(STORAGE_KEY);
      else storage?.setItem(STORAGE_KEY, JSON.stringify({ schema_version: SCHEMA_VERSION, conversations: normalized }));
    } catch (_error) {
      // Browser storage can be unavailable or full; the active conversation still works.
    }
    return normalized;
  }

  function upsert(storage, value) {
    const incoming = normalize(value);
    if (!incoming) return load(storage);
    const existing = load(storage).find((item) => item.conversation_id === incoming.conversation_id);
    if (existing) {
      incoming.created_at = existing.created_at;
      incoming.saved = existing.saved || incoming.saved;
      incoming.archived = existing.archived || incoming.archived;
      if (!value.title && existing.title) incoming.title = existing.title;
    }
    return write(storage, [incoming, ...load(storage).filter((item) => item.conversation_id !== incoming.conversation_id)]);
  }

  function remove(storage, conversationId) {
    const id = text(conversationId, 160);
    const records = load(storage);
    const remaining = records.filter((item) => item.conversation_id !== id);
    if (remaining.length === records.length) return false;
    write(storage, remaining);
    return true;
  }

  function setArchived(storage, conversationId, archived) {
    const id = text(conversationId, 160);
    const records = load(storage);
    const record = records.find((item) => item.conversation_id === id);
    if (!record) return false;
    record.archived = !!archived;
    record.updated_at = new Date().toISOString();
    write(storage, records);
    return true;
  }

  function exportRecord(value) {
    const record = normalize(value);
    if (!record) throw new Error('Cannot export an invalid conversation.');
    return JSON.stringify({ nova_chat_export: SCHEMA_VERSION, conversation: record }, null, 2);
  }

  function parseExport(raw) {
    const payload = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return normalize(payload?.conversation || payload);
  }

  root.NovaChatHistory = {
    STORAGE_KEY,
    MAX_RECORDS,
    MAX_MESSAGES,
    normalize,
    load,
    write,
    upsert,
    remove,
    archive: (storage, conversationId) => setArchived(storage, conversationId, true),
    restore: (storage, conversationId) => setArchived(storage, conversationId, false),
    exportRecord,
    parseExport,
  };
})(typeof window !== 'undefined' ? window : globalThis);
