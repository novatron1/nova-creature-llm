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
  for(let index = brace; index < html.length; index += 1){
    const character = html[index];
    if(quote){
      if(escaped) escaped = false;
      else if(character === '\\') escaped = true;
      else if(character === quote) quote = null;
      continue;
    }
    if(character === "'" || character === '"' || character === '`'){
      quote = character;
      continue;
    }
    if(character === '{') depth += 1;
    if(character === '}'){
      depth -= 1;
      if(depth === 0) return html.slice(start, index + 1);
    }
  }
  throw new Error(`unterminated ${name}`);
}

test('GPU Hub has a top-level tab and a responsive standalone panel', () => {
  assert.match(html, /<button class="nav-tab" data-panel="gpu-hub-panel">GPU Hub<\/button>/);
  assert.match(html, /<section class="workspace-panel" id="gpu-hub-panel">/);
  assert.match(html, /class="gpu-hub-grid"/);
  assert.match(html, /@media\(max-width:600px\)[\s\S]*?\.gpu-hub-grid/);
});

test('GPU Hub exposes only the four documented compute modes', () => {
  const select = html.match(/<select id="gpuHubMode"[\s\S]*?<\/select>/);
  assert.ok(select, 'gpuHubMode selector is present');
  const modes = [...select[0].matchAll(/<option value="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(modes, ['auto', 'cpu', 'local_gpu', 'vast_gpu']);
});

test('GPU Hub has stable status ids and explicit paid-operation confirmation text', () => {
  for(const id of [
    'gpuHubLocalState', 'gpuHubVastState', 'gpuHubInstances', 'gpuHubEndpoint',
    'gpuHubModeState', 'gpuHubEffectiveState', 'gpuHubAvailabilityState',
    'gpuHubVerificationState', 'gpuHubReasonState', 'gpuHubMessage'
  ]){
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /I understand this may start billed Vast\.ai time\./);
  assert.match(html, /window\.confirm\(/);
});

test('GPU Hub client functions use the documented server routes with bounded timeouts', () => {
  for(const name of [
    'loadGpuHubStatus', 'setGpuHubMode', 'scanGpuHubLocal', 'testGpuHubVast',
    'verifyGpuHubWorker', 'loadGpuHubInstances', 'setGpuHubVastState', 'destroyGpuHubInstance'
  ]) assert.match(html, new RegExp(`(?:async )?function ${name}\\(`));
  for(const route of [
    '/api/gpu-hub/status', '/api/gpu-hub/mode', '/api/gpu-hub/vast/test',
    '/api/gpu-hub/remote-model/test', '/api/gpu-hub/vast/instances',
    '/api/gpu-hub/vast/state', '/api/gpu-hub/vast/destroy'
  ]) assert.match(html, new RegExp(route.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(html, /GPU_HUB_REQUEST_TIMEOUT_MS\s*=\s*\d+/);
  assert.match(html, /AbortController/);
});

test('GPU Hub never places or persists Vast API keys in browser state', () => {
  assert.doesNotMatch(html, /id="[^"\n]*api[^"\n]*key/i);
  assert.doesNotMatch(html, /localStorage\.(?:setItem|getItem)[\s\S]{0,120}(?:vast|gpu).*api[_-]?key/i);
  assert.doesNotMatch(html, /NOVA_VAST_API_KEY/);
});

test('GPU Hub provides responsive worker endpoint, model, and provider verification controls', () => {
  for(const id of ['gpuHubWorkerEndpoint', 'gpuHubWorkerModel', 'gpuHubWorkerProvider', 'gpuHubWorkerVerifyBtn']){
    assert.match(html, new RegExp(`id="${id}"`));
  }
  assert.match(html, /gpu-hub-worker-fields/);
  assert.match(html, /@media\(max-width:600px\)[\s\S]*?\.gpu-hub-worker-fields/);
  assert.doesNotMatch(html, /id="[^"]*(?:api[_-]?key|token|password)[^"]*"/i);
});

test('worker verification payload is trimmed, backend-bound, and contains no browser key', () => {
  const source = extractFunction('gpuHubWorkerVerificationPayload');
  const payloadFor = new Function(`${source}; return gpuHubWorkerVerificationPayload;`)();
  const payload = payloadFor(
    ' https://worker.example/v1 ',
    ' qwen3 ',
    'VLLM',
    'vast_gpu'
  );
  assert.deepEqual(payload, {
    endpoint: 'https://worker.example/v1',
    model: 'qwen3',
    provider: 'vllm',
    backend: 'vast_gpu'
  });
  assert.equal(Object.hasOwn(payload, 'api_key'), false);
});

test('GPU Hub never renders worker endpoint, provider, or model details', () => {
  const source = extractFunction('gpuHubEndpointText');
  const endpointText = new Function(`${source}; return gpuHubEndpointText;`)();
  const rendered = endpointText({
    url: 'https://private-worker.example/v1', provider: 'vllm', model: 'qwen-private'
  });
  assert.equal(rendered, 'Connected (details hidden)');
  assert.doesNotMatch(rendered, /private-worker|vllm|qwen-private/);
});

test('GPU Hub availability message keeps unavailable modes visible and permits only Auto CPU fallback', () => {
  const source = extractFunction('gpuHubAvailabilityMessage');
  const messageFor = new Function(`${source}; return gpuHubAvailabilityMessage;`)();
  assert.match(messageFor({
    mode: 'local_gpu', effective_backend: 'cpu', local: {available: false, reason: 'No compatible local GPU.'}
  }), /Local GPU is unavailable.*No compatible local GPU\./);
  assert.match(messageFor({
    mode: 'vast_gpu', effective_backend: 'cpu', vast: {available: false, reason: 'Vast is not configured.'}
  }), /Vast\.ai GPU is unavailable.*Vast is not configured\./);
  assert.match(messageFor({
    mode: 'auto', effective_backend: 'cpu', local: {available: false, reason: 'No local GPU.'}
  }), /Auto fell back to CPU/);
});

test('GPU Hub availability message trusts controller expiry and Auto-with-Vast truth', () => {
  const source = extractFunction('gpuHubAvailabilityMessage');
  const messageFor = new Function(`${source}; return gpuHubAvailabilityMessage;`)();
  assert.match(messageFor({
    mode: 'local_gpu',
    effective_mode: 'local_gpu',
    available: false,
    reason: 'Local GPU endpoint verification expired.',
    verified: false,
    verification_expired: true,
    local: {available: true, usable: true, reason: 'CUDA GPU detected.'}
  }), /Local GPU is unavailable.*verification expired/i);
  assert.match(messageFor({
    mode: 'auto',
    effective_mode: 'vast_gpu',
    available: true,
    reason: 'Verified GPU endpoint selected automatically.',
    verified: true,
    verification_expired: false,
    vast: {available: true, reason: 'Verified Vast.ai model endpoint is ready.'}
  }), /Auto selected verified Vast\.ai GPU.*selected automatically/i);
});
