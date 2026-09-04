const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const html = fs.readFileSync(path.join(__dirname, '..', '..', 'nova_chat_web.html'), 'utf8');

function extractFunction(name) {
  const asyncStart = html.indexOf(`async function ${name}(`);
  const start = asyncStart === -1 ? html.indexOf(`function ${name}(`) : asyncStart;
  assert.notEqual(start, -1, `missing ${name}`);
  const brace = html.indexOf('{', start);
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
    if (character === '}') {
      depth -= 1;
      if (depth === 0) return html.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

test('raw-memory trace renders Raw + Memory without a Strong fallback label', () => {
  const messageHtmlSource = extractFunction('messageHtml');
  const render = new Function(
    'linkifyMessageText',
    'escapeHtml',
    'evidenceDrawerHtml',
    `${messageHtmlSource}; return messageHtml;`,
  )(
    text => text,
    text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
    () => '',
  );

  const rendered = render('Raw answer', {
    raw_memory_mode: true,
    optional_model_mode: {
      requested: true,
      mode: 'raw_memory',
      reason: 'raw_adapter_bypass',
    },
    model_residency: {reason: 'requested model unavailable'},
  });

  assert.match(rendered, /Raw \+ Memory/);
  assert.doesNotMatch(rendered, /Strong fallback/);
  assert.doesNotMatch(rendered, /Strong · Qwen 3 8B active/);
});

test('model traces visibly identify the active GPU provider and backend', () => {
  const messageHtmlSource = extractFunction('messageHtml');
  const render = new Function(
    'linkifyMessageText',
    'escapeHtml',
    'evidenceDrawerHtml',
    `${messageHtmlSource}; return messageHtml;`,
  )(
    text => text,
    text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
    () => '',
  );

  const rendered = render('GPU answer', {
    local_llm_provider: 'vllm',
    local_llm_model: 'Qwen/Qwen3-8B',
    gpu_backend: 'vast_gpu',
  });

  assert.match(rendered, /GPU: vllm · vast_gpu/);
});

test('answer traces visibly show measured response time', () => {
  const messageHtmlSource = extractFunction('messageHtml');
  const render = new Function(
    'linkifyMessageText',
    'escapeHtml',
    'evidenceDrawerHtml',
    `${messageHtmlSource}; return messageHtml;`,
  )(
    text => text,
    text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
    () => '',
  );

  const rendered = render('Timed answer', {response_time_ms: 1889.4});

  assert.match(rendered, /⏱ 1889 ms/);
});

test('answer tags can render gateway route-summary model and latency', () => {
  assert.match(html, /routeSummary\.provider/);
  assert.match(html, /routeSummary\.model/);
  assert.match(html, /routeSummary\.latency_ms/);
});

test('companion traces visibly show Nova personality and relationship state', () => {
  const messageHtmlSource = extractFunction('messageHtml');
  const render = new Function(
    'linkifyMessageText',
    'escapeHtml',
    'evidenceDrawerHtml',
    `${messageHtmlSource}; return messageHtml;`,
  )(
    text => text,
    text => String(text).replaceAll('&', '&amp;').replaceAll('<', '&lt;'),
    () => '',
  );

  const rendered = render('Companion answer', {
    companion: {
      primary_mode: 'companionship',
      relationship_stage: 'established',
      social_plan: {tone: 'warm_conversational'},
    },
  });

  assert.match(rendered, /Personality: companion · warm/);
  assert.match(rendered, /Bond: established/);
});

test('stream latency is copied into the trace used by answer tags', () => {
  const source = extractFunction('withResponseLatency');
  const addLatency = new Function(`${source}; return withResponseLatency;`)();

  assert.deepEqual(
    addLatency({source: 'cognitive_os'}, 1889.4),
    {source: 'cognitive_os', response_time_ms: 1889},
  );
});

test('active vision excludes Raw + Memory but remains available to Nova', () => {
  const source = extractFunction('shouldUseActiveVisionContext');
  const build = new Function(
    'currentActiveVisionContext',
    'trainedAdapterOnlyMode',
    'dolphinAdapterOnlyMode',
    'managedModelMode',
    `${source}; return shouldUseActiveVisionContext;`,
  );

  assert.equal(build(() => ({}), false, false, 'raw_memory')('What is in this picture?'), false);
  assert.equal(build(() => ({}), false, false, 'nova')('What is in this picture?'), true);
  assert.equal(build(() => ({}), true, false, 'nova')('What is in this picture?'), false);
});

test('active-vision follow-up holds and releases the transport-independent request lock', async () => {
  const source = extractFunction('send');
  const run = new Function(`
    let activeChatController = null;
    let chatRequestInFlight = false;
    const input = {value: 'What is in this picture?', focus() {}};
    const sendBtn = {disabled: false, textContent: 'Send'};
    const lockUpdates = [];
    let lockDuringRequest = null;
    const openPanel = () => {};
    const shouldUseActiveVisionContext = () => true;
    const setFace = () => {};
    const updateModelControlUi = () => lockUpdates.push(chatRequestInFlight);
    const sendActiveVisionFollowUp = async () => {
      lockDuringRequest = chatRequestInFlight;
      return {response: 'vision answer'};
    };
    ${source}
    return async () => {
      await send();
      return {lockDuringRequest, finalLock: chatRequestInFlight, lockUpdates};
    };
  `)();

  const result = await run();
  assert.equal(result.lockDuringRequest, true);
  assert.equal(result.finalLock, false);
  assert.deepEqual(result.lockUpdates, [true, false]);
});
