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

test('Research panel exposes a usable query and result workspace', () => {
  assert.match(html, /<section class="workspace-panel" id="research-panel">/);
  for(const id of [
    'researchPrompt',
    'researchRunBtn',
    'researchStatus',
    'researchCurrentResult',
    'researchHistory'
  ]) assert.match(html, new RegExp(`id="${id}"`));
  assert.match(html, /class="research-panel-grid"/);
  assert.match(html, /@media\(max-width:600px\)[\s\S]*?\.research-panel-grid/);
});

test('Research panel has live-run and rendering functions', () => {
  for(const name of [
    'runResearchPanel',
    'renderResearchResult',
    'renderResearchHistory',
    'researchSourceCard'
  ]) assert.match(html, new RegExp(`(?:async )?function ${name}\\(`));
  assert.match(html, /onclick="runResearchPanel\(\)"/);
  assert.match(html, /source_retrieval/);
  assert.match(html, /source_consensus/);
});

test('Research forces the web-enabled Nova route without changing the selected raw mode', () => {
  assert.match(html, /Research needs Nova's web-enabled route/);
  assert.match(html, /callAPI\(requestText, \{skipSync:true\}\)/);
  assert.match(html, /const previousDolphinAdapterOnly = dolphinAdapterOnlyMode/);
});

test('researchSourceCard renders safe source metadata and status', () => {
  const source = extractFunction('researchSourceCard');
  const cardFor = new Function(
    'escapeHtml',
    'safeEvidenceUrl',
    `${source}; return researchSourceCard;`
  )(
    value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    value => /^https:\/\//.test(String(value)) ? String(value) : ''
  );
  const rendered = cardFor({
    title: 'Official vLLM docs <safe>',
    url: 'https://docs.vllm.ai/example',
    status: 200,
    snippet: 'OpenAI-compatible server endpoint.'
  });
  assert.match(rendered, /Official vLLM docs &lt;safe&gt;/);
  assert.match(rendered, /HTTP 200/);
  assert.match(rendered, /OpenAI-compatible server endpoint/);
  assert.match(rendered, /https:\/\/docs\.vllm\.ai\/example/);
});
