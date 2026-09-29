(function installStudioPipeline(global){
  const terminal = new Set(['completed','failed','cancelled','interrupted']);
  const state = {busy:false, timer:null, pending:null, urls:[], status:null};
  const el = id => document.getElementById(id);
  const message = text => { if(el('studioCharacterMessage')) el('studioCharacterMessage').textContent = text; };
  try { state.pending = JSON.parse(global.sessionStorage?.getItem('nova-studio-pending') || 'null'); } catch(_) {}

  function savePending(value){
    state.pending = value;
    try {
      if(value) global.sessionStorage?.setItem('nova-studio-pending',JSON.stringify(value));
      else global.sessionStorage?.removeItem('nova-studio-pending');
    } catch(_) {}
  }

  async function request(path, options={}){
    const base = await ensureProjectServer();
    const init = {...options, headers:authHeaders({'Accept':'application/json',...(options.headers || {})})};
    const response = typeof global.novaFetchWithTimeout === 'function'
      ? await global.novaFetchWithTimeout(base + '/nova/v1/studio/' + path, init, 120000)
      : await fetch(base + '/nova/v1/studio/' + path, init);
    const data = await response.json().catch(()=>({}));
    if(!response.ok){
      const error = new Error(data.error?.message || 'Studio request failed');
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function updateButton(){
    const button = el('studioCharacterGenerate');
    if(!button) return;
    button.disabled = state.busy || !state.status?.can_submit || !state.status?.memory_profile_ready;
    button.textContent = state.busy ? 'Submitting…' : state.pending ? 'Retry pending submission' : 'Generate character preview';
  }

  async function upload(file, kind){
    const maximum = (kind === 'image' ? 25 : 250) * 1024 * 1024;
    if(!file || !file.size || file.size > maximum) throw new Error('Choose a valid '+kind+' within the '+(maximum/1024/1024)+' MiB limit.');
    const result = await request('assets?kind='+kind,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    return result.id;
  }

  async function generateStudioCharacter(){
    if(state.busy) return;
    state.busy = true; updateButton();
    try {
      if(!state.pending){
        const image = el('studioCharacterImage')?.files?.[0];
        const audio = el('studioCharacterAudio')?.files?.[0];
        const beat = el('studioCharacterBeat')?.files?.[0];
        const audioKind = el('studioAudioKind')?.value;
        const spoken = String(el('studioSpokenPreview')?.value || '').trim();
        const prompt = String(el('studioCharacterPrompt')?.value || '').trim();
        if(!image) throw new Error('Choose your character picture first.');
        if(!prompt || prompt.length > 4000) throw new Error('Describe the performance in 1–4000 characters.');
        if(audio && !['clean_vocal','mixed'].includes(audioKind)) throw new Error('Choose clean vocal or mixed music for your recording.');
        if(audio && spoken) throw new Error('Choose your recording OR a stock spoken preview, not both.');
        message('Copying your inputs locally; originals stay unchanged.');
        const payload = {request_key:global.crypto.randomUUID(), image_asset_id:await upload(image,'image'),
          prompt, seed:20260923, export_preset:el('studioExportPreset')?.value || 'source',
          audio_start_seconds:Number(el('studioAudioStart')?.value || 0)};
        if(audio){payload.audio_asset_id=await upload(audio,'audio');payload.audio_kind=audioKind;}
        if(beat) payload.beat_asset_id=await upload(beat,'audio');
        if(spoken) payload.spoken_text=spoken;
        savePending(payload);
      }
      const job = await request('jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(state.pending)});
      savePending(null);
      message('Queued '+job.id+'. The backend will run video, verify release, then prepare audio/export.');
      await loadNovaStudioPipeline();
    } catch(error){
      // A transient rejection does not disprove an earlier accepted submission.
      if([400,404,409,413,422].includes(error.status)) savePending(null);
      message(error.message + (state.pending ? ' Retry pending submission to recover the same request, not create a duplicate.' : ''));
    } finally {state.busy=false;updateButton();}
  }

  async function openOutput(path){
    try {
      if(!/^\/nova\/v1\/studio\/jobs\/[a-zA-Z0-9_-]+\/outputs\/(video|final)$/.test(path)) throw new Error('Invalid output link.');
      const base = await ensureProjectServer();
      const response = await fetch(base+path,{headers:authHeaders({})});
      if(!response.ok) throw new Error('Saved output could not be opened.');
      const length = Number(response.headers.get('Content-Length'));
      if(!Number.isFinite(length) || length <= 0 || length > 100*1024*1024){
        await response.body?.cancel();
        throw new Error('Output is too large for the low-memory browser preview; use its saved local file.');
      }
      for(const url of state.urls) URL.revokeObjectURL(url);
      state.urls=[];
      const url=URL.createObjectURL(await response.blob());state.urls.push(url);
      const video=document.createElement('video');video.controls=true;video.preload='metadata';video.src=url;video.style.maxWidth='100%';
      const link=document.createElement('a');link.href=url;link.download='nova-character.mp4';link.textContent='Save MP4';
      el('studioCharacterPreview')?.replaceChildren(video,link);
    } catch(error){message(error.message);}
  }

  function renderJobs(jobs){
    const target=el('studioCharacterJobs');if(!target)return;
    target.replaceChildren();
    if(!jobs.length){target.textContent='No managed character previews yet.';return;}
    for(const job of jobs){
      const row=document.createElement('div');row.className='dream-studio-job';
      const summary=document.createElement('p');
      summary.textContent=job.id+' — '+job.stage+(job.waiting_reason?' — '+job.waiting_reason:'')+(job.error?' — '+job.error:'')+(job.cleanup_error?' — '+job.cleanup_error:'');
      row.append(summary);
      for(const output of job.outputs || []){
        const button=document.createElement('button');button.type='button';button.className='panel-action';
        button.textContent=output.id==='final'?'Open final MP4':'Open saved motion video';
        button.onclick=()=>openOutput(output.download_path);row.append(button);
      }
      if(!terminal.has(job.stage)){
        const cancel=document.createElement('button');cancel.type='button';cancel.className='panel-action';cancel.textContent='Cancel safely';
        cancel.onclick=async()=>{try {await request('jobs/'+job.id+'/cancel',{method:'POST'});message('Cancellation requested. A running shared worker may need to finish safely.');await loadNovaStudioPipeline();}catch(error){message(error.message);}};
        row.append(cancel);
      }
      target.append(row);
    }
  }

  async function loadNovaStudioPipeline(){
    if(!el('studioCharacterInfo'))return;
    if(state.timer){clearTimeout(state.timer);state.timer=null;}
    el('studioCharacterInfo').textContent='Native preview: 384×480, 17 frames at 24 fps (0.71 seconds). Vertical export is padded to 720×1280. Generated motion + audio overlay — not audio-driven animation or verified lip-sync. Stock speech is not rap.';
    try {
      state.status=await request('status');updateButton();
      if(!state.status.enabled){message('Managed studio is not configured on this server.');return;}
      if(state.status.quarantine) message('Cleanup needs attention: '+state.status.quarantine);
      else if(!state.status.memory_profile_ready) message('Live generation is held until a monitored RAM calibration is approved and recorded.');
      else if(!state.status.can_submit) message('This device lacks the required media or model-management permission.');
      else if(state.pending) message('A prior submission is unresolved. Retry pending submission to recover it safely.');
      const result=await request('jobs');const jobs=Array.isArray(result.data)?result.data:[];renderJobs(jobs);
      if(jobs.some(job=>!terminal.has(job.stage))) state.timer=setTimeout(loadNovaStudioPipeline,3000);
    }catch(error){message(error.message);}
  }

  global.addEventListener('pagehide',()=>{if(state.timer)clearTimeout(state.timer);for(const url of state.urls)URL.revokeObjectURL(url);});
  Object.assign(global,{generateStudioCharacter,loadNovaStudioPipeline});
})(window);
