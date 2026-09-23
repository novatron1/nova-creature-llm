const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', '..', 'nova_chat_web.html'), 'utf8');

function extractFunction(name) {
  const match = new RegExp(`(?:async )?function ${name}\\(`).exec(html);
  assert.ok(match, `missing ${name}`);
  const start = match.index;
  const brace = html.indexOf('{', html.indexOf(')', start));
  let depth = 0;
  let quote = null;
  let escaped = false;
  for (let index = brace; index < html.length; index += 1) {
    const character = html[index];
    if (quote) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === quote) quote = null;
      continue;
    }
    if (character === "'" || character === '"' || character === '`') {
      quote = character;
      continue;
    }
    if (character === '{') depth += 1;
    if (character === '}' && --depth === 0) return html.slice(start, index + 1);
  }
  throw new Error(`unterminated ${name}`);
}

function composer() {
  const listeners = {};
  const requests = [];
  const controller = new AbortController();
  const context = vm.createContext({
    input: {value: 'My next thought', addEventListener: (name, fn) => { listeners[name] = fn; }},
    sendBtn: {disabled: false, textContent: 'Stop'},
    activeChatController: controller,
    chatRequestInFlight: true,
    activeChatStopping: false,
    activeChatRequestId: '',
    activeChatAbortTimer: null,
    SERVER_BASE: 'http://localhost:3000',
    clearTimeout,
    authHeaders: headers => headers,
    fetch: async (...args) => { requests.push(args); return {}; },
  });
  vm.runInContext(extractFunction('send') + '\n' + extractFunction('cancelActiveChat'), context);
  const start = html.indexOf("input.addEventListener('keydown'");
  vm.runInContext(html.slice(start, html.indexOf('if(botChatInput)', start)), context);
  return {context, listeners, controller, requests};
}

test('Enter during a reply preserves the draft and does not stop the response', async () => {
  const {context, listeners, controller} = composer();
  context.activeChatRequestId = 'reply-1';
  let prevented = false;
  await listeners.keydown({key: 'Enter', preventDefault() { prevented = true; }});
  assert.equal(controller.signal.aborted, false);
  assert.equal(context.input.value, 'My next thought');
  assert.equal(context.activeChatStopping, false);
  assert.equal(prevented, true);
});

test('explicit Stop works while the request is still connecting and keeps the draft', async () => {
  const {context, controller, requests} = composer();
  await context.sendBtn.onclick();
  assert.equal(controller.signal.aborted, true);
  assert.equal(context.activeChatStopping, true);
  assert.equal(context.input.value, 'My next thought');
  assert.equal(requests.length, 0);
});

test('explicit Stop also cancels an assigned server request', async () => {
  const {context, controller, requests} = composer();
  context.activeChatRequestId = 'reply-1';
  await context.sendBtn.onclick();
  assert.equal(controller.signal.aborted, true);
  assert.equal(requests.length, 1);
  assert.equal(requests[0][0], 'http://localhost:3000/nova/v1/cancel/reply-1');
});

test('in-flight non-streaming work keeps a newly submitted draft', async () => {
  const {context} = composer();
  context.activeChatController = null;
  await context.send();
  assert.equal(context.input.value, 'My next thought');
});

test('two fast submissions cannot overlap while a local command is being checked', async () => {
  const {context} = composer();
  let resolveCommand;
  const pendingCommand = new Promise(resolve => { resolveCommand = resolve; });
  let commandChecks = 0;
  let requests = 0;
  Object.assign(context, {
    chatRequestInFlight: false,
    activeChatController: null,
    openPanel() {},
    updateModelControlUi() {},
    handleLocalUiCommand: () => { commandChecks += 1; return pendingCommand; },
    shouldUseActiveVisionContext: () => true,
    setFace() {},
    sendActiveVisionFollowUp: async () => { requests += 1; return {}; },
  });
  context.input.focus = () => {};
  const first = context.send();
  const second = context.send();
  resolveCommand(false);
  await Promise.all([first, second]);
  assert.equal(commandChecks, 1);
  assert.equal(requests, 1);
  assert.equal(context.chatRequestInFlight, false);
});

test('handled and rejected local commands release the composer lock', async () => {
  const {context} = composer();
  Object.assign(context, {
    chatRequestInFlight: false,
    activeChatController: null,
    openPanel() {},
    updateModelControlUi() {},
    handleLocalUiCommand: async () => true,
  });
  await context.send();
  assert.equal(context.chatRequestInFlight, false);
  context.input.value = 'Another local command';
  context.handleLocalUiCommand = async () => { throw new Error('command failed'); };
  await assert.rejects(context.send(), /command failed/);
  assert.equal(context.chatRequestInFlight, false);
});

test('opening the GPU Hub navigates locally before any model call and consumes the command', async () => {
  const {context} = composer();
  const panels = [];
  const replies = [];
  Object.assign(context, {
    chatRequestInFlight: false,
    activeChatController: null,
    openPanel: panel => panels.push(panel),
    updateModelControlUi() {},
    addMsg: (role, text) => replies.push(text),
    speakNova() {},
    sensoryState: {},
    shouldUseActiveVisionContext: () => { throw new Error('A navigation command must not reach model routing'); },
  });
  vm.runInContext(extractFunction('handleLocalUiCommand'), context);
  context.input.value = 'OPEN THE GPU HUB';
  await context.send();
  assert.equal(panels.at(-1), 'gpu-hub-panel');
  assert.deepEqual(replies, ['Opened GPU Hub.']);
  assert.equal(context.input.value, '');
  assert.equal(context.chatRequestInFlight, false);
});

test('local navigation accepts existing menu titles and rejects arbitrary destinations', async () => {
  const panels = [];
  const context = vm.createContext({openPanel: panel => panels.push(panel), addMsg() {}, speakNova() {}, sensoryState: {}});
  vm.runInContext(extractFunction('handleLocalUiCommand'), context);
  for (const [command, panel] of [
    ['Please open the GPU Hub page.', 'gpu-hub-panel'],
    ['go to Home', 'home-panel'],
    ['show the Tools tab', 'tools-panel'],
    ['navigate to App Builder', 'app-builder-panel'],
    ['open Test/Check', 'test-check-panel'],
    ['open Scheduler', 'scheduler-panel'],
    ['take me to Display please', 'display-panel'],
  ]) {
    assert.equal(await context.handleLocalUiCommand(command), true, command);
    assert.equal(panels.at(-1), panel);
    assert.match(html, new RegExp(`data-panel="${panel}"`));
  }
  const previousCount = panels.length;
  for (const command of ['open https://example.com', 'open javascript:alert(1)', 'open the GPU Hub and delete files', 'open Notepad']) {
    assert.equal(await context.handleLocalUiCommand(command), false, command);
  }
  assert.equal(panels.length, previousCount);
});

class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.hidden = false; this.attributes = {}; this.events = {}; this.textContent = ''; }
  appendChild(child) {
    if (child.parent) child.parent.children = child.parent.children.filter(item => item !== child);
    child.parent = this;
    this.children.push(child);
    return child;
  }
  append(...children) { children.forEach(child => this.appendChild(child)); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, fn) { this.events[name] = fn; }
  querySelector(selector) {
    for (const child of this.children) {
      if (child.className === selector.slice(1)) return child;
      const nested = child.querySelector(selector);
      if (nested) return nested;
    }
    return null;
  }
}

function visibleText(element) {
  if (element.hidden) return '';
  return [element.textContent, ...element.children.map(visibleText)].join(' ');
}

function statusContext() {
  const context = vm.createContext({document: {createElement: tag => new Element(tag)}});
  vm.runInContext(['formatSafetyStatus', 'buildAnswerStatus', 'attachAnswerStatus'].map(extractFunction).join('\n'), context);
  return context;
}

test('answer status shows only the actual model until Details is opened', () => {
  const context = statusContext();
  const node = context.buildAnswerStatus({model: 'qwen2.5:1.5b', personality: 'warm', intent: 'social', memory: '2 recalled', safety: 'not_checked'});
  assert.match(visibleText(node), /qwen2.5:1.5b/);
  assert.doesNotMatch(visibleText(node), /Brain:|Personality:|Intent:|Memory:|Safety:|Vision:/);
  const toggle = node.querySelector('.answer-status-toggle');
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  toggle.events.click();
  assert.match(visibleText(node), /Personality: warm/);
  assert.match(visibleText(node), /Safety: not checked/);
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  toggle.events.click();
  assert.doesNotMatch(visibleText(node), /Memory:/);
});

test('legacy route diagnostics also live inside one closed Details drawer', () => {
  const context = statusContext();
  const message = new Element('div');
  const diagnostics = new Element('div');
  diagnostics.className = 'meta';
  diagnostics.hidden = true;
  diagnostics.textContent = 'memory_transformer confidence 96%';
  message.appendChild(diagnostics);
  context.attachAnswerStatus(message, null);
  const toggle = message.querySelector('.answer-status-toggle');
  assert.ok(toggle);
  assert.doesNotMatch(visibleText(message), /memory_transformer/);
  toggle.events.click();
  assert.match(visibleText(message), /memory_transformer/);
  assert.equal(diagnostics.parent.className, 'answer-status-details');
});

test('pending progress does not claim a hardcoded model or expose routing stages', () => {
  const context = vm.createContext({});
  vm.runInContext(extractFunction('streamProgressLabel'), context);
  for (const stage of ['nova_core', 'strong_local_model', 'direct_middle_route', 'larger_local_review', 'deep_local_review']) {
    const label = context.streamProgressLabel({stage, elapsed_seconds: 4});
    assert.doesNotMatch(label, /Qwen|8B|routing|routed|reviewer|small-model|larger free local model/i);
    assert.match(label, /Nova/);
  }
});
