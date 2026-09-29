import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

function harness() {
  const elements = new Map();
  const node = () => ({value:'',textContent:'',disabled:false,hidden:false,files:[],children:[],
    append(...items){this.children.push(...items);},appendChild(item){this.children.push(item);},
    replaceChildren(...items){this.children=items;},addEventListener(){},click(){},remove(){}});
  const element = id => {if(!elements.has(id)) elements.set(id,node()); return elements.get(id);};
  element('studioCharacterImage').files = [{name:'reference.jpg',size:100}];
  element('studioCharacterAudio').files = [{name:'recording.mp3',size:100}];
  element('studioAudioKind').value = 'mixed';
  element('studioCharacterPrompt').value = 'restrained nod';
  element('studioExportPreset').value = 'vertical';
  const calls = [], timers = [], jobs = [];
  let releaseUpload;
  let uploadGate = Promise.resolve();
  let sequence = 0;
  const replies = [];
  const window = {addEventListener(){}, crypto:{randomUUID:()=> 'request-'+(++sequence)}};
  const fetch = async(url, options={}) => {
    const path = url.replace('http://local','');
    calls.push({path,options});
    let data;
    if (path.includes('/assets?')) {await uploadGate; data={id:path.endsWith('image')?'image-id':'audio-id'};}
    else if(path.endsWith('/status')) data={enabled:true,can_submit:true,memory_profile_ready:true};
    else if(path.endsWith('/jobs') && options.method==='POST') {
      const reply = replies.shift();
      if(reply === 'lost') throw new Error('ack lost');
      if(reply === 429) return {ok:false,status:429,json:async()=>({})};
      data={id:'job-1',stage:'queued',outputs:[]};
    }
    else if(path.endsWith('/jobs')) data={data:jobs};
    else data=jobs[0] || {id:'job-1',stage:'queued',waiting_reason:'Waiting for memory',outputs:[]};
    return {ok:true,json:async()=>data};
  };
  vm.runInNewContext(fs.readFileSync(new URL('../../assets/nova_studio_pipeline.js',import.meta.url),'utf8'), {
    window, document:{getElementById:element, createElement:node}, fetch,
    ensureProjectServer:async()=> 'http://local',authHeaders:extra=>extra,
    setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
    URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}}, console,
  });
  return {window,element,calls,jobs,timers,replies, pauseUpload(){uploadGate=new Promise(r=>{releaseUpload=r;});},releaseUpload(){releaseUpload();}};
}

test('uploads reference/audio, preserves classification and prevents duplicate submission',async()=>{
  const h=harness();
  h.pauseUpload();
  const first=h.window.generateStudioCharacter();
  const second=h.window.generateStudioCharacter();
  h.releaseUpload();
  await Promise.all([first,second]);
  const submissions=h.calls.filter(c=>c.options.method==='POST' && c.path.endsWith('/jobs'));
  assert.equal(submissions.length,1);
  const body=JSON.parse(submissions[0].options.body);
  assert.equal(body.image_asset_id,'image-id');
  assert.equal(body.audio_asset_id,'audio-id');
  assert.equal(body.audio_kind,'mixed');
  assert.equal(body.export_preset,'vertical');
  assert.equal(h.calls.some(c=>c.path.endsWith('/release')),false);
});

test('history reports failed audio with preserved video and honest preview duration',async()=>{
  const h=harness();
  h.jobs.push({id:'job-1',stage:'failed',error:'Audio export failed',outputs:[{id:'video',download_path:'/nova/v1/studio/jobs/job-1/outputs/video'}]});
  await h.window.loadNovaStudioPipeline();
  assert.match(h.element('studioCharacterInfo').textContent,/17 frames.*24 fps.*0\.71/);
  assert.match(h.element('studioCharacterInfo').textContent,/not.*lip.sync/i);
  const text = n => [n.textContent,...n.children.map(text)].join(' ');
  assert.match(text(h.element('studioCharacterJobs')),/Audio export failed/);
  assert.match(text(h.element('studioCharacterJobs')),/video/i);
});

test('unclassified audio is rejected before uploading',async()=>{
  const h=harness();h.element('studioAudioKind').value='';
  await h.window.generateStudioCharacter();
  assert.equal(h.calls.filter(c=>c.options.method==='POST').length,0);
  assert.match(h.element('studioCharacterMessage').textContent,/clean vocal|mixed/i);
});

test('lost acknowledgement then rate limit preserves submission identity',async()=>{
  const h=harness();h.replies.push('lost',429);
  await h.window.generateStudioCharacter();
  await h.window.generateStudioCharacter();
  await h.window.generateStudioCharacter();
  const bodies=h.calls.filter(c=>c.options.method==='POST' && c.path.endsWith('/jobs')).map(c=>c.options.body);
  assert.equal(bodies.length,3);
  assert.equal(new Set(bodies).size,1);
});
