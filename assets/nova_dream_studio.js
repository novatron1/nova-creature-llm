(function installNovaDreamStudio(global){
  const DREAM_STUDIO_REQUEST_TIMEOUT_MS = 20000;
  const state = {
    currentJobId: '',
    pollTimer: null,
    objectUrls: [],
    access: null,
    gpu: null,
    imageEngine: null,
    videoEngine: null,
    loading: false
  };

  function element(id){ return document.getElementById(id); }

  function errorMessage(data, response){
    return String(
      data?.error?.message
      || data?.error
      || data?.message
      || ('HTTP ' + response.status)
    );
  }

  async function dreamJson(path, options={}){
    const base = await ensureProjectServer();
    const request = {
      method: options.method || 'GET',
      headers: authHeaders({
        'Accept':'application/json',
        ...(options.body ? {'Content-Type':'application/json'} : {})
      }),
      body: options.body ? JSON.stringify(options.body) : undefined
    };
    let response;
    try {
      response = typeof global.novaFetchWithTimeout === 'function'
        ? await global.novaFetchWithTimeout(
          base + path,
          request,
          DREAM_STUDIO_REQUEST_TIMEOUT_MS
        )
        : await fetch(base + path, request);
    } catch(error){
      if(error?.name === 'AbortError'){
        throw new Error('Dream Studio request timed out. Check the local engine, then refresh.');
      }
      throw error;
    }
    const data = await response.json().catch(() => ({}));
    if(!response.ok) throw new Error(errorMessage(data, response));
    return data;
  }

  function setMessage(message, kind=''){
    const target = element('dreamStudioMessage');
    if(!target) return;
    target.className = 'dream-studio-message' + (kind ? ' ' + kind : '');
    target.textContent = String(message || '');
  }

  function setState(id, value, kind=''){
    const target = element(id);
    if(!target) return;
    target.className = kind;
    target.textContent = String(value || '');
  }

  function updateModeOptions(){
    const video = element('dreamStudioMode')?.value === 'video';
    document.querySelectorAll('[data-dream-video-option]').forEach(item => {
      item.hidden = !video;
    });
    updateGenerateButton();
  }

  function updateGenerateButton(){
    const button = element('dreamStudioGenerateBtn');
    if(!button) return;
    const video = element('dreamStudioMode')?.value === 'video';
    const permitted = video ? !!state.access?.video_generate : !!state.access?.image_generate;
    const health = (video ? state.videoEngine : state.imageEngine)?.health || {};
    const workflowReady = video
      ? !!health.video_workflow_configured
      : !!health.image_workflow_configured;
    button.disabled = !(permitted && health.status === 'ready' && workflowReady);
    button.title = button.disabled
      ? 'A local media engine must be ready and this device must have media access.'
      : 'Queue this local media job through Nova.';
  }

  function renderEngineAndAccess(){
    const imageHealth = state.imageEngine?.health || {};
    const videoHealth = state.videoEngine?.health || {};
    const imageReady = imageHealth.status === 'ready' && !!imageHealth.image_workflow_configured;
    const videoReady = videoHealth.status === 'ready' && !!videoHealth.video_workflow_configured;
    const readyNames = [];
    if(imageReady) readyNames.push('ComfyUI');
    if(videoReady) readyNames.push(state.videoEngine?.engine_id === 'nova-video-lite' ? 'Video Lite' : 'ComfyUI video');
    setState(
      'dreamStudioEngineState',
      readyNames.length ? readyNames.join(' + ') + ' ready' : 'no ready media engine',
      readyNames.length ? 'ready' : 'warning'
    );
    setState(
      'dreamStudioImageWorkflowState',
      imageReady ? 'configured' : 'not ready',
      imageReady ? 'ready' : 'warning'
    );
    setState(
      'dreamStudioVideoWorkflowState',
      videoReady
        ? (state.videoEngine?.engine_id === 'nova-video-lite' ? 'Video Lite ready' : 'ComfyUI configured')
        : (videoHealth.status || 'not ready'),
      videoReady ? 'ready' : 'warning'
    );
    const imageAllowed = !!state.access?.image_generate;
    const videoAllowed = !!state.access?.video_generate;
    setState(
      'dreamStudioAccessState',
      imageAllowed || videoAllowed
        ? `image ${imageAllowed ? 'ON' : 'OFF'} · video ${videoAllowed ? 'ON' : 'OFF'}`
        : 'media permission OFF',
      imageAllowed || videoAllowed ? 'ready' : 'blocked'
    );
    const gpu = state.gpu;
    const gpuReady = !!gpu?.available;
    const gpuLabel = gpuReady
      ? `${gpu.effective_backend || gpu.effective_mode || 'GPU'} ready`
      : (gpu ? 'not ready' : 'not connected');
    setState('dreamStudioGpuState', gpuLabel, gpuReady ? 'ready' : 'warning');
    const gpuNote = element('dreamStudioGpuNote');
    if(gpuNote){
      const model = String(gpu?.endpoint?.model || '').trim();
      const isTextWorker = gpuReady && !!model;
      gpuNote.hidden = !isTextWorker;
      gpuNote.textContent = isTextWorker
        ? `GPU Hub is connected for ${model} text. Dream Studio image/video generation still requires ComfyUI with a media workflow.`
        : '';
    }
    const note = element('dreamStudioAccessNote');
    if(note) note.hidden = imageAllowed || videoAllowed;
    updateGenerateButton();
  }

  async function loadDreamStudio(){
    if(state.loading) return;
    state.loading = true;
    setMessage('Checking Nova media access and local engines...', 'working');
    try {
      const [engines, access, gpu] = await Promise.all([
        dreamJson('/nova/v1/engines'),
        dreamJson('/nova/v1/media/access'),
        dreamJson('/api/gpu-hub/status').catch(() => null)
      ]);
      const available = Array.isArray(engines.data) ? engines.data : [];
      const comfy = available.find(item => item.engine_id === 'comfyui-local') || null;
      const videoLite = available.find(item => item.engine_id === 'nova-video-lite') || null;
      state.imageEngine = comfy;
      state.videoEngine = (
        comfy?.health?.status === 'ready' && comfy?.health?.video_workflow_configured
      ) ? comfy : videoLite;
      state.access = access;
      state.gpu = gpu;
      renderEngineAndAccess();
      await loadDreamStudioJobs();
      const imageReady = state.imageEngine?.health?.status === 'ready'
        && state.imageEngine?.health?.image_workflow_configured;
      const videoReady = state.videoEngine?.health?.status === 'ready'
        && state.videoEngine?.health?.video_workflow_configured;
      if(!state.access.image_generate && !state.access.video_generate){
        setMessage('This device can chat but cannot generate media. On Nova’s desktop, open Settings and enable Media for this paired device.', 'error');
      } else if(!imageReady && !videoReady){
        setMessage('No local media engine is ready. Start ComfyUI and check the configured image workflow.', 'error');
      } else {
        setMessage(
          videoReady
            ? 'Dream Studio is ready for local images and free Video Lite MP4s.'
            : 'Dream Studio is ready for local images. Video is not ready yet.',
          'ready'
        );
      }
    } catch(error) {
      setMessage('Dream Studio check failed: ' + error.message, 'error');
    } finally {
      state.loading = false;
    }
  }

  function numberValue(id, minimum, maximum){
    const raw = String(element(id)?.value || '').trim();
    if(!raw) return undefined;
    const value = Number(raw);
    if(!Number.isInteger(value) || value < minimum || value > maximum){
      throw new Error(`${id.replace('dreamStudio','')} must be between ${minimum} and ${maximum}.`);
    }
    return value;
  }

  function buildGenerationBody(){
    const prompt = String(element('dreamStudioPrompt')?.value || '').trim();
    if(!prompt) throw new Error('Enter a generation prompt first.');
    if(prompt.length > 8000) throw new Error('Prompt exceeds 8000 characters.');
    const negative = String(element('dreamStudioNegative')?.value || '').trim();
    if(negative.length > 4000) throw new Error('Negative prompt exceeds 4000 characters.');
    const body = {
      prompt,
      negative_prompt: negative || undefined,
      seed: numberValue('dreamStudioSeed', 0, Number.MAX_SAFE_INTEGER),
      width: numberValue('dreamStudioWidth', 64, 4096),
      height: numberValue('dreamStudioHeight', 64, 4096),
      steps: numberValue('dreamStudioSteps', 1, 200)
    };
    if(element('dreamStudioMode')?.value === 'video'){
      body.frames = numberValue('dreamStudioFrames', 1, 4096);
      body.fps = numberValue('dreamStudioFps', 1, 120);
      body.motion = String(element('dreamStudioMotion')?.value || 'slow_zoom_in');
    }
    return Object.fromEntries(Object.entries(body).filter(([, value]) => value !== undefined));
  }

  async function generateDreamMedia(){
    const button = element('dreamStudioGenerateBtn');
    try {
      const mode = element('dreamStudioMode')?.value === 'video' ? 'video' : 'image';
      const allowed = mode === 'video' ? state.access?.video_generate : state.access?.image_generate;
      if(!allowed) throw new Error('Media permission is OFF for this device. Enable it from Settings on Nova’s desktop.');
      const body = buildGenerationBody();
      if(button) button.disabled = true;
      setMessage(`Queueing local ${mode} generation through Nova...`, 'working');
      const job = await dreamJson(
        mode === 'video' ? '/nova/v1/videos/generations' : '/nova/v1/images/generations',
        {method:'POST', body}
      );
      state.currentJobId = String(job.job_id || '');
      renderCurrentJob(job);
      setMessage(`Job ${state.currentJobId} queued locally.`, 'working');
      await loadDreamStudioJobs();
      schedulePoll(800);
    } catch(error) {
      setMessage('Generation was not queued: ' + error.message, 'error');
      updateGenerateButton();
    }
  }

  function clearOutputUrls(){
    state.objectUrls.forEach(url => URL.revokeObjectURL(url));
    state.objectUrls = [];
  }

  function clearPreview(message='Generated media will appear here.'){
    clearOutputUrls();
    const preview = element('dreamStudioPreview');
    if(!preview) return;
    preview.className = 'dream-studio-preview empty';
    preview.textContent = message;
  }

  async function renderOutputs(job){
    const outputs = Array.isArray(job.outputs) ? job.outputs : [];
    if(!outputs.length){
      clearPreview('The job completed without a usable media output.');
      return;
    }
    clearOutputUrls();
    const preview = element('dreamStudioPreview');
    if(!preview) return;
    preview.className = 'dream-studio-preview';
    preview.textContent = '';
    for(const output of outputs){
      try {
        const base = await ensureProjectServer();
        const response = await fetch(base + output.download_path, {headers:authHeaders()});
        if(!response.ok) throw new Error('HTTP ' + response.status);
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        state.objectUrls.push(url);
        const wrap = document.createElement('div');
        wrap.className = 'dream-studio-output';
        let media;
        if(blob.type.startsWith('video/')){
          media = document.createElement('video');
          media.controls = true;
          media.playsInline = true;
        } else if(blob.type.startsWith('audio/')){
          media = document.createElement('audio');
          media.controls = true;
        } else {
          media = document.createElement('img');
          media.alt = 'Generated locally by Nova Dream Studio';
          media.loading = 'lazy';
        }
        media.src = url;
        const meta = document.createElement('div');
        meta.className = 'dream-studio-output-meta';
        const filename = document.createElement('span');
        filename.textContent = output.filename || 'Nova output';
        const download = document.createElement('a');
        download.className = 'dream-studio-download';
        download.href = url;
        download.download = output.filename || 'nova-output';
        download.textContent = 'Save';
        meta.append(filename, download);
        wrap.append(media, meta);
        preview.appendChild(wrap);
      } catch(error) {
        const failure = document.createElement('div');
        failure.className = 'dream-studio-message error';
        failure.textContent = 'Output could not be opened: ' + error.message;
        preview.appendChild(failure);
      }
    }
  }

  function renderCurrentJob(job){
    setState('dreamStudioJobId', job.job_id || 'none');
    const status = String(job.status || 'unknown');
    setState(
      'dreamStudioJobState',
      status,
      status === 'completed' ? 'ready' : (status === 'failed' || status === 'cancelled' ? 'blocked' : 'warning')
    );
    const cancel = element('dreamStudioCancelBtn');
    if(cancel) cancel.disabled = !['queued','running'].includes(status);
  }

  async function refreshDreamStudioJob(jobId=state.currentJobId){
    const safeId = String(jobId || '').trim();
    if(!safeId) return;
    state.currentJobId = safeId;
    try {
      const job = await dreamJson('/nova/v1/jobs/' + encodeURIComponent(safeId));
      renderCurrentJob(job);
      if(job.status === 'completed'){
        setMessage('Generation completed locally.', 'ready');
        await renderOutputs(job);
        await loadDreamStudioJobs(false);
      } else if(job.status === 'failed'){
        setMessage('Generation failed: ' + (job.error || 'The local engine returned no usable output.'), 'error');
        clearPreview('Generation failed. Check the local engine status.');
        await loadDreamStudioJobs(false);
      } else if(job.status === 'cancelled'){
        setMessage('Generation cancelled.', 'error');
        clearPreview('This job was cancelled.');
        await loadDreamStudioJobs(false);
      } else {
        setMessage(`Job ${safeId} is ${job.status || 'working'}...`, 'working');
        schedulePoll(1800);
      }
    } catch(error) {
      setMessage('Job status failed: ' + error.message, 'error');
    }
  }

  function schedulePoll(delay){
    if(state.pollTimer) clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(() => {
      state.pollTimer = null;
      refreshDreamStudioJob();
    }, Math.max(500, Number(delay) || 1800));
  }

  async function cancelDreamStudioJob(){
    if(!state.currentJobId) return;
    const button = element('dreamStudioCancelBtn');
    if(button) button.disabled = true;
    try {
      const result = await dreamJson(
        '/nova/v1/jobs/' + encodeURIComponent(state.currentJobId) + '/cancel',
        {method:'POST', body:{}}
      );
      setMessage(result.ok ? 'Cancellation requested.' : 'That job had already finished.', result.ok ? 'working' : '');
      await refreshDreamStudioJob();
    } catch(error) {
      setMessage('Cancellation failed: ' + error.message, 'error');
    }
  }

  function friendlyTime(value){
    const date = new Date(value || '');
    return Number.isNaN(date.getTime()) ? '' : date.toLocaleString([], {dateStyle:'short',timeStyle:'short'});
  }

  function renderJobHistory(jobs){
    const list = element('dreamStudioJobs');
    if(!list) return;
    list.textContent = '';
    if(!jobs.length){
      const empty = document.createElement('div');
      empty.className = 'dream-studio-job';
      empty.textContent = 'No media jobs belong to this device yet.';
      list.appendChild(empty);
      return;
    }
    jobs.forEach(job => {
      const card = document.createElement('div');
      card.className = 'dream-studio-job';
      const head = document.createElement('div');
      head.className = 'dream-studio-job-head';
      const title = document.createElement('strong');
      title.textContent = (job.operation || 'media job').replaceAll('_',' ');
      const status = document.createElement('span');
      status.className = 'foundation-state ' + (job.status || '');
      status.textContent = job.status || 'unknown';
      head.append(title, status);
      const detail = document.createElement('small');
      detail.textContent = `${job.job_id || ''}${job.created_at ? ' · ' + friendlyTime(job.created_at) : ''}`;
      const open = document.createElement('button');
      open.className = 'panel-action';
      open.type = 'button';
      open.textContent = 'Open Job';
      open.onclick = () => refreshDreamStudioJob(job.job_id);
      card.append(head, detail, open);
      list.appendChild(card);
    });
  }

  async function loadDreamStudioJobs(showErrors=true){
    try {
      const jobs = await dreamJson('/nova/v1/jobs?limit=25');
      renderJobHistory(Array.isArray(jobs.data) ? jobs.data : []);
    } catch(error) {
      if(showErrors) setMessage('Job history failed: ' + error.message, 'error');
    }
  }

  global.addEventListener('pagehide', clearOutputUrls);
  Object.assign(global, {
    cancelDreamStudioJob,
    generateDreamMedia,
    loadDreamStudio,
    loadDreamStudioJobs,
    refreshDreamStudioJob,
    updateDreamStudioMode: updateModeOptions
  });
})(window);
