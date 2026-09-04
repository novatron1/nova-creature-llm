const test = require('node:test');
const assert = require('node:assert/strict');

const {createNovaConnectionRecovery} = require('../../assets/nova_connection_recovery.js');


class FakeEventTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(name, listener) {
    const listeners = this.listeners.get(name) || [];
    listeners.push(listener);
    this.listeners.set(name, listeners);
  }

  emit(name) {
    for (const listener of this.listeners.get(name) || []) listener();
  }
}


test('a visible tablet page reconnects once when it wakes', async () => {
  const windowObject = new FakeEventTarget();
  const documentObject = new FakeEventTarget();
  documentObject.hidden = true;
  let scheduled = null;
  let reconnectCount = 0;
  const recovery = createNovaConnectionRecovery({
    windowObject,
    documentObject,
    reconnect: async () => { reconnectCount += 1; },
    setTimeoutFn: callback => { scheduled = callback; return 1; },
    clearTimeoutFn: () => {},
    delayMs: 0,
  });

  recovery.start();
  documentObject.hidden = false;
  documentObject.emit('visibilitychange');
  windowObject.emit('focus');
  assert.equal(reconnectCount, 0);

  await scheduled();

  assert.equal(reconnectCount, 1);
});
