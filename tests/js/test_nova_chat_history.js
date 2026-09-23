const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const modulePath = path.join(__dirname, '..', '..', 'assets', 'nova_chat_history.js');
const source = fs.readFileSync(modulePath, 'utf8');
const sandbox = { window: {}, console };
vm.runInNewContext(source, sandbox, { filename: modulePath });
const history = sandbox.window.NovaChatHistory;

function storage(seed) {
  const values = new Map(Object.entries(seed || {}));
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
    raw(key) { return values.get(key); },
  };
}

test('chat history exposes a stable storage key and starts empty on corrupt data', () => {
  const store = storage({ [history.STORAGE_KEY]: '{not json' });
  assert.equal(history.load(store).length, 0);
  assert.equal(typeof history.STORAGE_KEY, 'string');
});

test('upsert keeps a bounded normalized record and preserves an explicit save', () => {
  const store = storage();
  history.upsert(store, {
    conversation_id: 'conv-1',
    title: '  First chat  ',
    messages: [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there' },
    ],
    saved: true,
  });
  history.upsert(store, {
    conversation_id: 'conv-1',
    title: '',
    messages: [{ role: 'user', content: 'Updated' }],
    saved: false,
  });
  const records = history.load(store);
  assert.equal(records.length, 1);
  assert.equal(records[0].title, 'First chat');
  assert.equal(records[0].saved, true);
  assert.deepEqual(Array.from(records[0].messages, (item) => item.content), ['Updated']);
  assert.equal(records[0].message_count, 1);
});

test('delete removes only the requested conversation', () => {
  const store = storage();
  history.upsert(store, { conversation_id: 'one', messages: [{ role: 'user', content: 'One' }] });
  history.upsert(store, { conversation_id: 'two', messages: [{ role: 'user', content: 'Two' }] });
  assert.equal(history.remove(store, 'one'), true);
  assert.deepEqual(Array.from(history.load(store), (item) => item.conversation_id), ['two']);
  assert.equal(history.remove(store, 'missing'), false);
});

test('archive and restore hide a conversation without deleting it', () => {
  const store = storage();
  history.upsert(store, { conversation_id: 'archived', messages: [{ role: 'user', content: 'Keep this' }] });
  assert.equal(history.archive(store, 'archived'), true);
  assert.equal(history.load(store)[0].archived, true);
  assert.equal(history.restore(store, 'archived'), true);
  assert.equal(history.load(store)[0].archived, false);
});

test('export and import round-trip a saved conversation without executable content', () => {
  const record = history.normalize({
    conversation_id: 'conv-export',
    title: 'Export me',
    messages: [{ role: 'assistant', content: '<script>alert(1)</script>' }],
    saved: true,
  });
  const imported = history.parseExport(history.exportRecord(record));
  assert.equal(imported.conversation_id, 'conv-export');
  assert.equal(imported.messages[0].content, '<script>alert(1)</script>');
  assert.equal(imported.saved, true);
});

test('chat page exposes history controls and handlers', () => {
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'nova_chat_web.html'), 'utf8');
  for (const marker of [
    'chatHistoryBtn',
    'saveCurrentConversation',
    'openSavedConversation',
    'deleteSavedConversation',
    'exportCurrentConversation',
    'Confirm delete',
    'New chat name',
    'Archive',
    'Show archived',
  ]) {
    assert.match(html, new RegExp(marker));
  }
});
