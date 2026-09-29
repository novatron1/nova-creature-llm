import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import './nova_dream_lifecycle.test.mjs';
import './nova_studio_pipeline.test.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const html = fs.readFileSync(path.join(root, 'nova_chat_web.html'), 'utf8');
const js = fs.readFileSync(path.join(root, 'assets/nova_dream_studio.js'), 'utf8');

test('Dream Studio exposes explicit video engine selection', () => {
  assert.match(html, /dreamStudioVideoEngine/);
  assert.match(js, /engine_id/);
  assert.match(js, /dreamStudioVideoEngine/);
});

test('Dream Studio exposes checkpoint resume controls', () => {
  assert.match(html, /dreamStudioResumeBtn/);
  assert.match(js, /resumeDreamStudioJob/);
  assert.match(js, /\/resume/);
});

test('Dream Studio distinguishes a configured workflow from an offline engine', () => {
  const start = js.indexOf('  function renderEngineAndAccess(){');
  const end = js.indexOf('\n  async function loadDreamStudio()', start);
  assert.ok(start >= 0 && end > start);
  const state = {imageEngine: {health: {status: 'offline', image_workflow_configured: true}}};
  const values = new Map();
  const render = new Function('state', 'element', 'setState', 'updateGenerateButton',
    js.slice(start, end) + '; return renderEngineAndAccess;'
  )(state, () => null, (id, text) => values.set(id, text), () => {});
  render();
  assert.match(values.get('dreamStudioImageWorkflowState'), /^configured\b.*\bengine offline$/);
  state.imageEngine.health.status = 'ready';
  render();
  assert.equal(values.get('dreamStudioImageWorkflowState'), 'configured');
  state.imageEngine.health.image_workflow_configured = false;
  render();
  assert.equal(values.get('dreamStudioImageWorkflowState'), 'not configured');
  assert.match(js, /Image workflow is configured, but ComfyUI is offline/);
});

test('Dream Studio exposes a dedicated image workflow reconnect control', () => {
  assert.match(html, /dreamStudioReconnectImageBtn/);
  assert.match(html, /Reconnect Image Workflow/);
  assert.match(js, /reconnectDreamStudioImageWorkflow/);
});

test('Dream Studio reconnect flow launches local ComfyUI before refreshing', () => {
  assert.match(js, /\/nova\/v1\/engines\/comfyui-local\/launch/);
  assert.match(js, /launching the local image workflow/i);
  assert.match(js, /ComfyUI is still offline/i);
});

test('Dream Studio defaults to quality-oriented CPU settings and offers prompt improvement', () => {
  assert.match(html, /id="dreamStudioSteps"[^>]*value="24"/);
  assert.match(html, /Improve Prompt/);
    assert.match(js, /improveDreamPrompt/);
    assert.match(js, /single main subject/);
    assert.match(js, /extra people/);
    assert.match(js, /garbled text/);
  });

test('Dream Studio labels audio-overlay output honestly', () => {
  assert.match(js, /Audio was added after motion; this is not verified lip-sync/);
  assert.match(js, /job\.audio_overlay === true/);
});
