(function installNovaFoundationUi(global){
  const NOVA_DEVICE_TOKEN_KEY = 'nova_paired_device_token_v1';
  let foundationJobPollTimer = null;
  let pairingCodeExpiryTimer = null;
  let reliabilityJobPollTimer = null;
  let inMemoryDeviceToken = '';
  let localManagementAvailable = false;
  let deferredNovaInstallPrompt = null;
  let novaDesktopStatus = null;
  let targetVaultBackupId = '';
  let lastReliabilityStatus = null;
  let pairingExchangeInProgress = false;

  function pairedDeviceToken(){
    let value = '';
    try { value = String(localStorage.getItem(NOVA_DEVICE_TOKEN_KEY) || inMemoryDeviceToken || '').trim(); }
    catch(error) { value = inMemoryDeviceToken; }
    return value.startsWith('nova_') ? value : '';
  }

  function authHeaders(extra={}){
    const headers = {...extra};
    const token = pairedDeviceToken();
    if(token) headers.Authorization = 'Bearer ' + token;
    return headers;
  }

  function rememberPairedDeviceToken(token){
    const value = String(token || '').trim();
    if(!value.startsWith('nova_')) throw new Error('Nova returned an invalid device token.');
    inMemoryDeviceToken = value;
    try { localStorage.setItem(NOVA_DEVICE_TOKEN_KEY, value); } catch(error) {}
  }

  function clearPairedDeviceToken(){
    inMemoryDeviceToken = '';
    try { localStorage.removeItem(NOVA_DEVICE_TOKEN_KEY); } catch(error) {}
  }

  function forgetPairedDeviceToken(){
    clearPairedDeviceToken();
  }

  function showPairingRequired(message){
    if(pairingExchangeInProgress) return;
    const state = document.getElementById('pairingProtectionState');
    const note = document.getElementById('pairingMessage');
    if(state) state.textContent = 'Pairing required';
    if(note) note.textContent = message || 'Enter the one-time code shown on Nova\'s desktop.';
    const settingsPanel = document.getElementById('settings-panel');
    if(!settingsPanel?.classList.contains('active')) openPanel('settings-panel');
  }

  function friendlyFoundationTime(value){
    if(!value) return '';
    const date = new Date(value);
    if(Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString([], {dateStyle:'medium', timeStyle:'short'});
  }

  function hidePairingQr(){
    const wrap = document.getElementById('pairingQrWrap');
    const image = document.getElementById('pairingQrImage');
    const phone = document.getElementById('pairingPhoneUrl');
    if(wrap) wrap.hidden = true;
    if(image) image.removeAttribute('src');
    if(phone) phone.textContent = '';
  }

  async function loadFoundationStatus(){
    const protection = document.getElementById('pairingProtectionState');
    const count = document.getElementById('pairedDeviceCount');
    const desktopActions = document.getElementById('pairingDesktopActions');
    const databaseState = document.getElementById('foundationDatabaseState');
    try {
      const [pairing, health] = await Promise.all([
        projectJson('/api/pairing/status'),
        projectJson('/healthz')
      ]);
      if(count) count.textContent = String(pairing.paired_devices || 0);
      if(desktopActions) desktopActions.hidden = !pairing.local_client;
      localManagementAvailable = !!pairing.local_client;
      const reliabilityActions = document.getElementById('reliabilityDesktopActions');
      if(reliabilityActions) reliabilityActions.hidden = !localManagementAvailable;
      if(protection){
        if(!pairing.enabled) protection.textContent = 'Disabled by owner';
        else if(pairing.local_client) protection.textContent = 'Desktop trusted';
        else if(pairing.pairing_required) protection.textContent = 'Pairing required';
        else protection.textContent = 'Paired and protected';
      }
      if(databaseState){
        const foundation = health.foundation || {};
        databaseState.textContent = foundation.ok
          ? `Ready - schema ${foundation.schema_version || 1}, ${String(foundation.journal_mode || 'WAL').toUpperCase()}`
          : 'Needs attention';
      }
      if(pairing.local_client) await loadPairedDevices();
      else {
        const list = document.getElementById('pairedDeviceList');
        if(list){
          list.textContent = '';
          const note = document.createElement('div');
          note.className = 'foundation-note';
          note.textContent = pairing.pairing_required
            ? 'Enter the code from Nova\'s desktop to authorize this device.'
            : 'This device is paired. Device management stays on Nova\'s desktop.';
          list.appendChild(note);
        }
      }
      return !pairing.pairing_required;
    } catch(error) {
      if(protection) protection.textContent = 'Unavailable';
      if(databaseState) databaseState.textContent = 'Unavailable';
      return false;
    }
  }

  async function startPairing(){
    const button = document.getElementById('createPairingCodeBtn');
    const codeEl = document.getElementById('pairingCode');
    const message = document.getElementById('pairingMessage');
    if(button) button.disabled = true;
    if(message) message.textContent = 'Creating a secure one-time code...';
    try {
      const data = await projectJson('/api/pairing/start', {
        method:'POST',
        body:{ttl_seconds:300}
      });
      const pairing = data.pairing || {};
      if(codeEl) codeEl.textContent = pairing.code || '------';
      const qrWrap = document.getElementById('pairingQrWrap');
      const qrImage = document.getElementById('pairingQrImage');
      const phoneUrl = document.getElementById('pairingPhoneUrl');
      if(pairing.qr_url || data.qr_url){
        const qrPath = pairing.qr_url || data.qr_url;
        if(qrImage) qrImage.src = qrPath + '?v=' + encodeURIComponent(pairing.session_id || Date.now());
        if(phoneUrl) phoneUrl.textContent = data.phone_url || '';
        if(qrWrap) qrWrap.hidden = false;
      } else {
        hidePairingQr();
      }
      if(message){
        const qrNote = data.lan_accessible
          ? ' Or scan the QR code with your phone.'
          : ' Start Nova in phone/LAN mode to enable QR scanning.';
        message.textContent = `Use this code once before ${friendlyFoundationTime(pairing.expires_at)}. The code itself is never saved.${qrNote}`;
      }
      if(pairingCodeExpiryTimer) clearTimeout(pairingCodeExpiryTimer);
      pairingCodeExpiryTimer = setTimeout(() => {
        if(codeEl) codeEl.textContent = '------';
        if(message) message.textContent = 'That pairing code expired. Create a new code when you are ready.';
        hidePairingQr();
        pairingCodeExpiryTimer = null;
      }, Math.max(1000, Number(pairing.ttl_seconds || 300) * 1000));
    } catch(error) {
      if(codeEl) codeEl.textContent = '------';
      hidePairingQr();
      if(message) message.textContent = 'Could not create a pairing code: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  async function pairThisDevice(){
    const nameInput = document.getElementById('pairingDeviceName');
    const codeInput = document.getElementById('pairingCodeInput');
    const message = document.getElementById('pairingMessage');
    const code = String(codeInput?.value || '').replace(/\D/g, '');
    const defaultName = /mobile|android|iphone|ipad/i.test(navigator.userAgent) ? 'My phone' : 'My browser';
    if(code.length !== 6){
      if(message) message.textContent = 'Enter the complete six-digit code from Nova\'s desktop.';
      if(codeInput) codeInput.focus();
      return;
    }
    if(pairingExchangeInProgress) return;
    pairingExchangeInProgress = true;
    if(message) message.textContent = 'Pairing this device...';
    try {
      const data = await projectJson('/api/pairing/exchange', {
        method:'POST',
        body:{code, device_name:String(nameInput?.value || '').trim() || defaultName}
      });
      rememberPairedDeviceToken(data.token);
      if(codeInput) codeInput.value = '';
      const displayedCode = document.getElementById('pairingCode');
      if(displayedCode) displayedCode.textContent = '------';
      hidePairingQr();
      if(pairingCodeExpiryTimer){
        clearTimeout(pairingCodeExpiryTimer);
        pairingCodeExpiryTimer = null;
      }
      if(message) message.textContent = 'Paired securely. This device can now use Nova.';
      const authorized = await loadFoundationStatus();
      if(authorized){
        await Promise.allSettled([
          loadFoundationJobs(),
          loadReliabilityStatus(),
          loadDesktopExperience()
        ]);
      }
      const connection = await connectToLiveNova();
      if(connection){
        SERVER_BASE = connection.url;
        setStatus(true);
        const serverButton = document.getElementById('btnServer');
        if(serverButton) serverButton.textContent = 'Connected';
      }
    } catch(error) {
      if(message) message.textContent = 'Pairing failed: ' + error.message;
    } finally {
      pairingExchangeInProgress = false;
    }
  }

  async function loadPairedDevices(){
    const list = document.getElementById('pairedDeviceList');
    if(!list) return;
    try {
      const data = await projectJson('/api/pairing/devices');
      list.textContent = '';
      const devices = Array.isArray(data.devices) ? data.devices : [];
      if(!devices.length){
        const empty = document.createElement('div');
        empty.className = 'foundation-note';
        empty.textContent = 'No network devices are paired yet.';
        list.appendChild(empty);
        return;
      }
      devices.forEach(device => {
        const item = document.createElement('div');
        item.className = 'foundation-item';
        const head = document.createElement('div');
        head.className = 'foundation-item-head';
        const name = document.createElement('strong');
        name.textContent = device.name || 'Nova device';
        const revoke = document.createElement('button');
        revoke.className = 'panel-action';
        revoke.textContent = 'Revoke';
        revoke.onclick = () => revokePairedDevice(device.id);
        const scopes = new Set(Array.isArray(device.scopes) ? device.scopes : []);
        const mediaEnabled = scopes.has('image.generate') && scopes.has('video.generate');
        const media = document.createElement('button');
        media.className = 'panel-action';
        media.textContent = mediaEnabled ? 'Media ON' : 'Enable Media';
        media.title = mediaEnabled
          ? 'Turn off image and video generation for this device.'
          : 'Allow only image and video generation for this paired device.';
        media.onclick = () => setPairedDeviceMediaAccess(device.id, !mediaEnabled);
        const actions = document.createElement('div');
        actions.className = 'foundation-actions';
        actions.append(media, revoke);
        head.append(name, actions);
        const detail = document.createElement('small');
        detail.textContent =
          `Paired ${friendlyFoundationTime(device.created_at)}` +
          `${device.last_seen_at ? ' - last seen ' + friendlyFoundationTime(device.last_seen_at) : ''}` +
          ` - media ${mediaEnabled ? 'enabled' : 'off'}`;
        item.append(head, detail);
        list.appendChild(item);
      });
    } catch(error) {
      list.textContent = 'Device list unavailable: ' + error.message;
    }
  }

  async function revokePairedDevice(deviceId){
    const message = document.getElementById('pairingMessage');
    try {
      await projectJson('/api/pairing/revoke', {
        method:'POST',
        body:{device_id:deviceId}
      });
      if(message) message.textContent = 'Device access revoked immediately.';
      await loadFoundationStatus();
    } catch(error) {
      if(message) message.textContent = 'Could not revoke that device: ' + error.message;
    }
  }

  async function setPairedDeviceMediaAccess(deviceId, enabled){
    const message = document.getElementById('pairingMessage');
    try {
      const data = await projectJson('/api/pairing/scopes', {
        method:'POST',
        body:{
          device_id:deviceId,
          scopes:enabled ? ['image.generate','video.generate'] : []
        }
      });
      if(message){
        message.textContent = enabled
          ? 'Media enabled for that device. Chat, files, robot, and system permissions were not expanded.'
          : 'Media access disabled for that device.';
      }
      await loadPairedDevices();
      return data;
    } catch(error) {
      if(message) message.textContent = 'Could not update media access: ' + error.message;
      return null;
    }
  }

  function renderFoundationJobs(jobs){
    const list = document.getElementById('foundationJobList');
    const message = document.getElementById('foundationJobMessage');
    if(!list) return;
    list.textContent = '';
    const items = Array.isArray(jobs) ? jobs : [];
    if(!items.length){
      const empty = document.createElement('div');
      empty.className = 'foundation-note';
      empty.textContent = 'No background jobs yet.';
      list.appendChild(empty);
      if(message) message.textContent = 'No job is running.';
      return;
    }
    items.slice(0, 8).forEach(job => {
      const item = document.createElement('div');
      item.className = 'foundation-item';
      const head = document.createElement('div');
      head.className = 'foundation-item-head';
      const title = document.createElement('strong');
      const jobLabels = {
        full_training_check:'Nova full self-check',
        reliability_backup:'Verified Nova backup',
        reliability_restore:'Protected Nova restore'
      };
      title.textContent = jobLabels[job.kind] || String(job.kind || 'Background job').replaceAll('_', ' ');
      const state = document.createElement('span');
      state.className = 'foundation-state ' + String(job.status || 'queued');
      state.textContent = job.status || 'queued';
      head.append(title, state);
      const progress = document.createElement('div');
      progress.className = 'foundation-progress';
      const fill = document.createElement('span');
      fill.style.width = `${Math.max(0, Math.min(Number(job.progress || 0), 100))}%`;
      progress.appendChild(fill);
      const detail = document.createElement('small');
      const summary = job.result?.summary;
      const resultText = summary ? ` - ${summary.passed || 0}/${summary.total || 0} checks passed` : '';
      detail.textContent = `${job.message || ''}${resultText} - ${friendlyFoundationTime(job.created_at)}`;
      item.append(head, progress, detail);
      if(job.error){
        const error = document.createElement('small');
        error.textContent = job.error;
        item.appendChild(error);
      }
      if(job.status === 'queued' || job.status === 'running'){
        const actions = document.createElement('div');
        actions.className = 'foundation-actions';
        const cancel = document.createElement('button');
        cancel.className = 'panel-action';
        cancel.textContent = job.cancel_requested ? 'Cancellation requested' : 'Cancel';
        cancel.disabled = !!job.cancel_requested;
        cancel.onclick = () => cancelFoundationJob(job.id);
        actions.appendChild(cancel);
        item.appendChild(actions);
      }
      list.appendChild(item);
    });
    const active = items.find(job => job.status === 'queued' || job.status === 'running');
    if(message) message.textContent = active
      ? `${active.message || 'Working'} - ${active.progress || 0}%`
      : 'All recent jobs are finished.';
  }

  async function loadFoundationJobs(){
    if(foundationJobPollTimer){
      clearTimeout(foundationJobPollTimer);
      foundationJobPollTimer = null;
    }
    try {
      const data = await projectJson('/api/jobs?limit=12');
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];
      renderFoundationJobs(jobs);
      if(jobs.some(job => job.status === 'queued' || job.status === 'running')){
        foundationJobPollTimer = setTimeout(loadFoundationJobs, 1500);
      }
    } catch(error) {
      const message = document.getElementById('foundationJobMessage');
      if(message) message.textContent = 'Job center unavailable: ' + error.message;
    }
  }

  async function startFoundationJob(){
    const button = document.getElementById('runFoundationJobBtn');
    const message = document.getElementById('foundationJobMessage');
    if(button) button.disabled = true;
    if(message) message.textContent = 'Queuing Nova\'s self-check...';
    try {
      await projectJson('/api/jobs/start', {
        method:'POST',
        body:{kind:'full_training_check', payload:{source:'settings'}}
      });
      await loadFoundationJobs();
    } catch(error) {
      if(message) message.textContent = 'Could not start the self-check: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  async function cancelFoundationJob(jobId){
    const message = document.getElementById('foundationJobMessage');
    try {
      await projectJson(`/api/jobs/${encodeURIComponent(jobId)}/cancel`, {method:'POST', body:{}});
      if(message) message.textContent = 'Cancellation requested. Nova will stop at the next safe point.';
      await loadFoundationJobs();
    } catch(error) {
      if(message) message.textContent = 'Could not cancel the job: ' + error.message;
    }
  }

  function formatBackupSize(value){
    const bytes = Number(value || 0);
    if(!Number.isFinite(bytes) || bytes <= 0) return '0 B';
    const units = ['B','KB','MB','GB'];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const amount = bytes / (1024 ** index);
    return `${amount >= 10 || index === 0 ? amount.toFixed(0) : amount.toFixed(1)} ${units[index]}`;
  }

  function renderReliabilityStatus(data){
    lastReliabilityStatus = data || {};
    const diagnostics = data?.diagnostics || {};
    const health = document.getElementById('reliabilityHealthState');
    const automatic = document.getElementById('automaticBackupState');
    const count = document.getElementById('reliabilityBackupCount');
    const latest = document.getElementById('reliabilityLatestBackup');
    const vaultCount = document.getElementById('reliabilityVaultCount');
    const message = document.getElementById('reliabilityMessage');
    if(health) health.textContent = String(diagnostics.overall || 'unknown').replace(/^./, value => value.toUpperCase());
    if(automatic) automatic.textContent = data.automatic_backups ? `On - keeps ${data.retention || 7}` : 'Off';
    if(count) count.textContent = String(data.backup_count || 0);
    if(latest) latest.textContent = data.latest_backup ? friendlyFoundationTime(data.latest_backup.created_at) : 'None yet';
    if(vaultCount) vaultCount.textContent = String(data.vault_count || 0);

    const checks = document.getElementById('reliabilityCheckList');
    if(checks){
      checks.textContent = '';
      (Array.isArray(diagnostics.checks) ? diagnostics.checks : []).forEach(check => {
        const row = document.createElement('div');
        row.className = 'reliability-check ' + String(check.status || 'warning');
        const label = document.createElement('strong');
        label.textContent = check.message || check.id || 'Reliability check';
        const state = document.createElement('span');
        state.textContent = check.status || 'warning';
        row.append(label, state);
        checks.appendChild(row);
      });
    }

    const list = document.getElementById('reliabilityBackupList');
    if(list){
      list.textContent = '';
      const backups = Array.isArray(data.backups) ? data.backups : [];
      if(!backups.length){
        const empty = document.createElement('div');
        empty.className = 'foundation-note';
        empty.textContent = 'No coordinated backup yet. Create one now; Nova also creates one automatically each day.';
        list.appendChild(empty);
      }
      backups.slice(0, 7).forEach(backup => {
        const item = document.createElement('div');
        item.className = 'foundation-item';
        const head = document.createElement('div');
        head.className = 'foundation-item-head';
        const meta = document.createElement('div');
        meta.className = 'reliability-backup-meta';
        const title = document.createElement('strong');
        title.textContent = `${String(backup.reason || 'manual').replaceAll('_', ' ')} backup`;
        const detail = document.createElement('small');
        detail.textContent = `${friendlyFoundationTime(backup.created_at)} - ${backup.file_count || 0} files - ${formatBackupSize(backup.archive_bytes)}`;
        meta.append(title, detail);
        head.appendChild(meta);
        if(localManagementAvailable){
          const actions = document.createElement('div');
          actions.className = 'vault-actions';
          if(data.encryption_available){
            const encrypt = document.createElement('button');
            encrypt.className = 'panel-action';
            encrypt.textContent = 'Encrypt Copy';
            encrypt.onclick = () => openEncryptedBackupVault(backup.backup_id);
            actions.appendChild(encrypt);
          }
          const restore = document.createElement('button');
          restore.className = 'panel-action';
          restore.textContent = 'Restore';
          restore.onclick = () => restoreReliabilityBackup(backup.backup_id);
          actions.appendChild(restore);
          head.appendChild(actions);
        }
        item.appendChild(head);
        list.appendChild(item);
      });
    }

    renderVaultExports(data.vault_exports, data.encryption_available);

    if(message){
      const critical = Number(diagnostics.counts?.critical || 0);
      const warnings = Number(diagnostics.counts?.warning || 0);
      message.textContent = critical
        ? `${critical} critical reliability check${critical === 1 ? '' : 's'} need attention.`
        : warnings
          ? `Core checks passed with ${warnings} warning${warnings === 1 ? '' : 's'}.`
          : 'All reliability checks passed.';
    }
  }

  async function loadReliabilityStatus(){
    const message = document.getElementById('reliabilityMessage');
    try {
      const data = await projectJson('/api/reliability/status');
      renderReliabilityStatus(data);
    } catch(error) {
      if(message) message.textContent = 'Reliability status unavailable: ' + error.message;
    }
  }

  async function pollReliabilityJob(jobId){
    if(reliabilityJobPollTimer){
      clearTimeout(reliabilityJobPollTimer);
      reliabilityJobPollTimer = null;
    }
    const message = document.getElementById('reliabilityMessage');
    try {
      const data = await projectJson(`/api/jobs/${encodeURIComponent(jobId)}`);
      const job = data.job || {};
      if(job.status === 'queued' || job.status === 'running'){
        if(message) message.textContent = `${job.message || 'Working'} - ${job.progress || 0}%`;
        reliabilityJobPollTimer = setTimeout(() => pollReliabilityJob(jobId), 1000);
        return;
      }
      if(message) message.textContent = job.status === 'succeeded'
        ? (job.result?.message || job.message || 'Reliability job completed safely.')
        : (job.error || job.message || 'Reliability job did not complete.');
      await Promise.all([loadReliabilityStatus(), loadFoundationJobs()]);
    } catch(error) {
      if(message) message.textContent = 'Could not check reliability job: ' + error.message;
    }
  }

  async function createReliabilityBackup(){
    const button = document.getElementById('createReliabilityBackupBtn');
    const message = document.getElementById('reliabilityMessage');
    if(button) button.disabled = true;
    if(message) message.textContent = 'Queuing a verified Nova backup...';
    try {
      const data = await projectJson('/api/reliability/backup', {method:'POST', body:{reason:'manual'}});
      await loadFoundationJobs();
      if(data.job?.id) pollReliabilityJob(data.job.id);
    } catch(error) {
      if(message) message.textContent = 'Could not start the backup: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  async function runReliabilityDiagnostics(){
    const button = document.getElementById('runReliabilityDiagnosticsBtn');
    const message = document.getElementById('reliabilityMessage');
    if(button) button.disabled = true;
    if(message) message.textContent = 'Checking Nova\'s storage, memory, brain files, UI, and recovery readiness...';
    try {
      await projectJson('/api/reliability/diagnostics', {method:'POST', body:{}});
      await loadReliabilityStatus();
    } catch(error) {
      if(message) message.textContent = 'Diagnostics could not finish: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  async function restoreReliabilityBackup(backupId){
    const confirmation = global.prompt('Protected restore: type RESTORE to continue. Nova will first create a safety backup and will require a restart.');
    if(confirmation !== 'RESTORE') return;
    const message = document.getElementById('reliabilityMessage');
    if(message) message.textContent = 'Queuing protected restore. Nova is creating a safety backup first...';
    try {
      const data = await projectJson('/api/reliability/restore', {
        method:'POST',
        body:{backup_id:backupId, confirm:'RESTORE'}
      });
      await loadFoundationJobs();
      if(data.job?.id) pollReliabilityJob(data.job.id);
    } catch(error) {
      if(message) message.textContent = 'Restore did not start: ' + error.message;
    }
  }

  function novaRunsStandalone(){
    return !!(global.matchMedia?.('(display-mode: standalone)').matches || global.navigator.standalone);
  }

  function updateNovaInstallState(){
    const state = document.getElementById('novaInstallState');
    const button = document.getElementById('installNovaAppBtn');
    const message = document.getElementById('desktopExperienceMessage');
    const installed = novaRunsStandalone();
    if(state) state.textContent = installed ? 'Installed' : (deferredNovaInstallPrompt ? 'Ready to install' : 'Browser install available');
    if(button){
      button.disabled = installed;
      button.textContent = installed ? 'Nova App Installed' : (deferredNovaInstallPrompt ? 'Install Nova App' : 'Install Instructions');
    }
    if(message && installed) message.textContent = 'Nova is running in its installed app window.';
  }

  async function installNovaApp(){
    const message = document.getElementById('desktopExperienceMessage');
    if(novaRunsStandalone()){
      if(message) message.textContent = 'Nova is already installed as an app on this device.';
      return;
    }
    if(deferredNovaInstallPrompt){
      const promptEvent = deferredNovaInstallPrompt;
      deferredNovaInstallPrompt = null;
      promptEvent.prompt();
      const choice = await promptEvent.userChoice;
      if(message) message.textContent = choice.outcome === 'accepted'
        ? 'Nova app installation accepted.'
        : 'Installation was cancelled; nothing changed.';
      updateNovaInstallState();
      return;
    }
    const appleMobile = /iphone|ipad|ipod/i.test(navigator.userAgent);
    if(message) message.textContent = appleMobile
      ? 'On iPhone or iPad: tap Share, then Add to Home Screen.'
      : 'Open the browser menu and choose Install Nova Creature or Add to Home Screen.';
  }

  function renderVaultExports(exportsList, available){
    const state = document.getElementById('novaVaultState');
    const list = document.getElementById('vaultExportList');
    const exports = Array.isArray(exportsList) ? exportsList : [];
    if(state) state.textContent = available ? `Ready - ${exports.length} encrypted` : 'Unavailable';
    if(!list) return;
    list.textContent = '';
    if(!exports.length){
      const note = document.createElement('div');
      note.className = 'foundation-note';
      note.textContent = available
        ? 'Use Encrypt Copy beside a verified backup to create a password-protected file for USB or private cloud storage.'
        : 'Install Nova runtime requirements to enable encrypted portable copies.';
      list.appendChild(note);
      return;
    }
    exports.slice(0, 5).forEach(vault => {
      const item = document.createElement('div');
      item.className = 'foundation-item';
      const head = document.createElement('div');
      head.className = 'foundation-item-head';
      const meta = document.createElement('div');
      meta.className = 'reliability-backup-meta';
      const title = document.createElement('strong');
      title.textContent = 'AES-256 portable backup';
      const detail = document.createElement('small');
      detail.textContent = `${friendlyFoundationTime(vault.created_at)} - ${formatBackupSize(vault.vault_bytes)}`;
      meta.append(title, detail);
      head.appendChild(meta);
      if(localManagementAvailable){
        const download = document.createElement('a');
        download.className = 'panel-action panel-action-link vault-download';
        download.href = vault.download_url;
        download.download = vault.filename || 'nova-backup.novavault';
        download.textContent = 'Download';
        head.appendChild(download);
      }
      item.appendChild(head);
      list.appendChild(item);
    });
  }

  const remoteMessages = {
    ready: 'Private phone access is ready.',
    tailscale_not_installed: 'Install Tailscale on this PC to use Nova away from Wi-Fi.',
    tailscale_disconnected: 'Open Tailscale on this PC and sign in.',
    https_name_unavailable: 'Tailscale HTTPS is not ready for this PC.',
    serve_not_configured: 'Tailscale is ready; enable Nova remote phone access.',
    https_port_in_use: 'Private port 8443 is already used by another Tailscale service.',
    https_port_public: 'Private port 8443 has public access enabled and Nova will not use it.',
    command_failed: 'Tailscale could not update the private connection.',
    unsupported: 'Private phone access is unavailable on this system.'
  };

  function safeNovaRemoteUrl(value){
    try {
      const parsed = new URL(String(value || ''));
      if(parsed.protocol !== 'https:' || !parsed.hostname.toLowerCase().endsWith('.ts.net')) return '';
      if(parsed.username || parsed.password || parsed.search || parsed.hash) return '';
      return parsed.href.replace(/\/$/, '');
    } catch(error) {
      return '';
    }
  }

  function renderNovaRemoteAccess(remote){
    const details = remote && typeof remote === 'object' ? remote : {};
    const state = document.getElementById('novaRemoteAccessState');
    const link = document.getElementById('novaRemotePhoneUrl');
    const copy = document.getElementById('copyNovaPhoneUrlBtn');
    const toggle = document.getElementById('toggleNovaRemoteAccessBtn');
    const reason = Object.prototype.hasOwnProperty.call(remoteMessages, details.reason)
      ? details.reason
      : 'command_failed';
    if(state) state.textContent = remoteMessages[reason];

    const privateUrl = details.serve_enabled ? safeNovaRemoteUrl(details.private_url) : '';
    if(link){
      link.textContent = privateUrl;
      link.hidden = !privateUrl;
      if(privateUrl) link.href = privateUrl;
      else link.removeAttribute('href');
    }
    if(copy) copy.hidden = !privateUrl;
    if(toggle){
      toggle.hidden = !(localManagementAvailable && details.management_available);
      toggle.disabled = !!details.serve_conflict;
      toggle.textContent = details.serve_enabled ? 'Disable Remote Phone' : 'Enable Remote Phone';
    }
  }

  async function copyNovaPhoneUrl(){
    const link = document.getElementById('novaRemotePhoneUrl');
    const message = document.getElementById('desktopExperienceMessage');
    const privateUrl = safeNovaRemoteUrl(link?.getAttribute('href'));
    if(!privateUrl) return;
    try {
      if(navigator.clipboard?.writeText){
        await navigator.clipboard.writeText(privateUrl);
      } else {
        const temporary = document.createElement('textarea');
        temporary.value = privateUrl;
        temporary.setAttribute('readonly', '');
        temporary.style.position = 'fixed';
        temporary.style.opacity = '0';
        document.body.appendChild(temporary);
        temporary.select();
        document.execCommand('copy');
        temporary.remove();
      }
      if(message) message.textContent = 'Private phone link copied. Open it on a phone signed into your Tailscale network.';
    } catch(error) {
      if(message) message.textContent = 'Could not copy automatically. Press and hold the private address to copy it.';
    }
  }

  async function loadDesktopExperience(){
    updateNovaInstallState();
    const toggle = document.getElementById('toggleNovaAutostartBtn');
    const state = document.getElementById('novaAutostartState');
    if(lastReliabilityStatus){
      renderVaultExports(lastReliabilityStatus.vault_exports, lastReliabilityStatus.encryption_available);
    }
    if(!localManagementAvailable){
      if(toggle) toggle.hidden = true;
      if(state) state.textContent = 'Desktop control only';
      renderNovaRemoteAccess({reason:'unsupported'});
      return;
    }
    try {
      const data = await projectJson('/api/desktop/status');
      novaDesktopStatus = data;
      renderNovaRemoteAccess(data.remote_access);
      if(state) state.textContent = data.autostart_enabled ? 'On' : (data.autostart_available ? 'Off' : 'Unavailable');
      if(toggle){
        toggle.hidden = !data.autostart_available;
        toggle.disabled = !!data.autostart_conflict;
        toggle.textContent = data.autostart_enabled ? 'Disable Start with Windows' : 'Enable Start with Windows';
      }
      const message = document.getElementById('desktopExperienceMessage');
      if(message && data.autostart_conflict){
        message.textContent = 'An unmanaged startup item uses Nova\'s reserved name. Nova left it untouched.';
      } else if(message && novaRunsStandalone()){
        message.textContent = data.autostart_enabled
          ? 'Nova is installed, and Start with Windows is on.'
          : 'Nova is running in its installed app window. Start with Windows remains off.';
      } else if(message){
        message.textContent = data.autostart_enabled
          ? 'Nova will start quietly after Windows sign-in. You can turn this off here anytime.'
          : 'Install Nova as an app anytime. Start with Windows stays off until you enable it.';
      }
    } catch(error) {
      if(state) state.textContent = 'Unavailable';
      if(toggle) toggle.hidden = true;
      renderNovaRemoteAccess({reason:'command_failed'});
    }
  }

  async function toggleNovaRemoteAccess(){
    if(!novaDesktopStatus) return loadDesktopExperience();
    const remote = novaDesktopStatus.remote_access || {};
    const enabling = !remote.serve_enabled;
    const promptText = enabling
      ? 'Enable private remote phone access? Only devices signed into your Tailscale network can reach Nova, and new devices must still pair.'
      : 'Disable remote phone access? Nova will remain available on this PC.';
    if(!global.confirm(promptText)) return;
    const button = document.getElementById('toggleNovaRemoteAccessBtn');
    const message = document.getElementById('desktopExperienceMessage');
    if(button) button.disabled = true;
    try {
      const updated = await projectJson('/api/desktop/remote-access', {
        method:'POST', body:{enabled:enabling}
      });
      novaDesktopStatus = {...novaDesktopStatus, remote_access:updated};
      renderNovaRemoteAccess(updated);
      if(message) message.textContent = enabling
        ? 'Private remote phone access is ready. Copy the link, then create a pairing code for a new phone.'
        : 'Remote phone access is off. Existing paired-device permissions were left unchanged.';
    } catch(error) {
      if(message) message.textContent = 'Nova could not change the private phone connection. Check Tailscale, then try again.';
      await loadDesktopExperience();
    } finally {
      if(button) button.disabled = false;
    }
  }

  async function toggleNovaAutostart(){
    if(!novaDesktopStatus) return loadDesktopExperience();
    const enabling = !novaDesktopStatus.autostart_enabled;
    const promptText = enabling
      ? 'Enable Start with Windows? Nova will start quietly after you sign in. You can turn this off here anytime.'
      : 'Disable Start with Windows? Nova will still start normally from its launcher.';
    if(!global.confirm(promptText)) return;
    const button = document.getElementById('toggleNovaAutostartBtn');
    const message = document.getElementById('desktopExperienceMessage');
    if(button) button.disabled = true;
    try {
      novaDesktopStatus = await projectJson('/api/desktop/autostart', {
        method:'POST', body:{enabled:enabling}
      });
      if(message) message.textContent = novaDesktopStatus.message || 'Desktop startup preference updated.';
      await loadDesktopExperience();
    } catch(error) {
      if(message) message.textContent = 'Could not change Start with Windows: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  function openEncryptedBackupVault(backupId){
    targetVaultBackupId = String(backupId || '');
    const dialog = document.getElementById('novaVaultDialog');
    const passphrase = document.getElementById('novaVaultPassphrase');
    const confirm = document.getElementById('novaVaultPassphraseConfirm');
    const message = document.getElementById('novaVaultDialogMessage');
    if(passphrase) passphrase.value = '';
    if(confirm) confirm.value = '';
    if(message) message.textContent = 'The encrypted copy can be saved to a USB drive or private cloud folder.';
    if(dialog?.showModal) dialog.showModal();
    else if(dialog) dialog.setAttribute('open', '');
    if(passphrase) setTimeout(() => passphrase.focus(), 0);
  }

  function closeVaultDialog(){
    const dialog = document.getElementById('novaVaultDialog');
    const passphrase = document.getElementById('novaVaultPassphrase');
    const confirm = document.getElementById('novaVaultPassphraseConfirm');
    if(passphrase) passphrase.value = '';
    if(confirm) confirm.value = '';
    targetVaultBackupId = '';
    if(dialog?.close) dialog.close();
    else if(dialog) dialog.removeAttribute('open');
  }

  async function submitEncryptedBackupVault(){
    const passphrase = document.getElementById('novaVaultPassphrase');
    const confirm = document.getElementById('novaVaultPassphraseConfirm');
    const message = document.getElementById('novaVaultDialogMessage');
    const button = document.getElementById('novaVaultCreateBtn');
    const first = String(passphrase?.value || '');
    const second = String(confirm?.value || '');
    if(first.length < 12){
      if(message) message.textContent = 'Use at least 12 characters.';
      if(passphrase) passphrase.focus();
      return;
    }
    if(first !== second){
      if(message) message.textContent = 'The two passphrases do not match.';
      if(confirm) confirm.focus();
      return;
    }
    if(!targetVaultBackupId){
      if(message) message.textContent = 'Select a verified backup again.';
      return;
    }
    if(button) button.disabled = true;
    if(message) message.textContent = 'Encrypting the verified backup locally...';
    try {
      const data = await projectJson('/api/reliability/vault', {
        method:'POST', body:{backup_id:targetVaultBackupId, passphrase:first}
      });
      if(passphrase) passphrase.value = '';
      if(confirm) confirm.value = '';
      const link = document.createElement('a');
      link.href = data.vault.download_url;
      link.download = data.vault.filename || 'nova-backup.novavault';
      link.hidden = true;
      document.body.appendChild(link);
      link.click();
      link.remove();
      const desktopMessage = document.getElementById('desktopExperienceMessage');
      if(desktopMessage) desktopMessage.textContent = 'Encrypted backup created and download started. Keep the passphrase safe; Nova did not save it.';
      closeVaultDialog();
      await loadReliabilityStatus();
    } catch(error) {
      if(message) message.textContent = 'Could not create encrypted backup: ' + error.message;
    } finally {
      if(button) button.disabled = false;
    }
  }

  function applyLaunchPanel(){
    let url;
    try { url = new URL(global.location.href); } catch(error) { return; }
    const requested = String(url.searchParams.get('panel') || '').toLowerCase();
    const requestedPanels = {
      "chat": "chat-panel",
      "settings": "settings-panel",
      "display": "display-panel",
      "dream": "dream-studio-panel",
      "agents": "agent-library-panel",
      "builder": "app-builder-panel",
      "memory": "memory-panel",
      "tools": "tools-panel",
      "research": "research-panel",
      "tests": "test-check-panel",
      "projects": "saved-projects-panel",
      "files": "file-manager-panel",
      "logs": "debug-logs-panel"
    };
    if(requestedPanels[requested]) setTimeout(() => openPanel(requestedPanels[requested]), 0);
    if(requested){
      url.searchParams.delete('panel');
      global.history.replaceState(null, '', url.pathname + url.search + url.hash);
    }
  }

  function applyPairingLink(){
    let url;
    try { url = new URL(global.location.href); } catch(error) { return; }
    const code = String(url.searchParams.get('pair') || '').replace(/\D/g, '');
    if(code.length !== 6) return;
    const codeInput = document.getElementById('pairingCodeInput');
    if(codeInput) codeInput.value = code;
    url.searchParams.delete('pair');
    global.history.replaceState(null, '', url.pathname + url.search + url.hash);
    setTimeout(() => {
      openPanel('settings-panel');
      if(codeInput) codeInput.focus();
      const note = document.getElementById('pairingMessage');
      if(note) note.textContent = 'Pairing code filled from the QR scan. Name this phone, then tap Pair This Device.';
    }, 0);
  }

  Object.assign(global, {
    authHeaders,
    cancelFoundationJob,
    closeVaultDialog,
    copyNovaPhoneUrl,
    createReliabilityBackup,
    forgetPairedDeviceToken,
    installNovaApp,
    loadFoundationJobs,
    loadFoundationStatus,
    loadPairedDevices,
    loadDesktopExperience,
    loadReliabilityStatus,
    openEncryptedBackupVault,
    pairedDeviceToken,
    pairThisDevice,
    rememberPairedDeviceToken,
    restoreReliabilityBackup,
    renderNovaRemoteAccess,
    revokePairedDevice,
    setPairedDeviceMediaAccess,
    runReliabilityDiagnostics,
    showPairingRequired,
    startFoundationJob,
    startPairing,
    submitEncryptedBackupVault,
    toggleNovaAutostart,
    toggleNovaRemoteAccess
  });
  global.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    deferredNovaInstallPrompt = event;
    updateNovaInstallState();
  });
  global.addEventListener('appinstalled', () => {
    deferredNovaInstallPrompt = null;
    updateNovaInstallState();
  });
  if('serviceWorker' in navigator){
    navigator.serviceWorker.register('/service-worker.js').catch(() => {});
  }
  const vaultDialog = document.getElementById('novaVaultDialog');
  vaultDialog?.addEventListener('close', () => {
    const passphrase = document.getElementById('novaVaultPassphrase');
    const confirmation = document.getElementById('novaVaultPassphraseConfirm');
    if(passphrase) passphrase.value = '';
    if(confirmation) confirmation.value = '';
    targetVaultBackupId = '';
  });
  applyLaunchPanel();
  applyPairingLink();
})(window);
