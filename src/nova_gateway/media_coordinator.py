"""Backend-owned FIFO pipeline; HTTP polling does not drive its lifecycle."""
from __future__ import annotations

from dataclasses import asdict
import math
from threading import Event, RLock, Thread
import time
from uuid import uuid4

from .errors import InvalidRequestError, ProviderUnavailableError
from .media_assets import AssetService, file_hash
from .media_export import MediaCancelledError, MediaExporter, StockVoice
from .media_resources import ResourceGate
from .media_store import JobRecord, MediaConflictError, MediaStore, TERMINAL
from .media_wan import WanAdapter


class MediaCoordinator:
    def __init__(self, store: MediaStore, assets: AssetService, gate: ResourceGate,
                 wan: WanAdapter, exporter: MediaExporter, voice: StockVoice, *,
                 required_ram_bytes: int = 0, poll_interval: float = 1):
        self.store, self.assets, self.gate = store, assets, gate
        self.wan, self.exporter, self.voice = wan, exporter, voice
        self.required_ram_bytes = required_ram_bytes
        self.poll_interval = max(.01, poll_interval)
        self._lock = RLock()
        self._stop = Event()
        self._thread = None
        self._cancel: dict[str, Event] = {}
        self.last_error = None

    def submit(self, owner_id: str, request_key: str, request: dict) -> JobRecord:
        allowed = {'image_asset_id', 'prompt', 'seed', 'audio_asset_id', 'audio_kind',
                   'audio_start_seconds', 'beat_asset_id', 'spoken_text', 'export_preset'}
        if not isinstance(request, dict) or request.keys() - allowed:
            raise InvalidRequestError('Unsupported media request fields.')
        prompt = request.get('prompt')
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise InvalidRequestError('Provide a performance description of 1 to 4000 characters.')
        if request.get('audio_asset_id') and request.get('spoken_text'):
            raise InvalidRequestError('Choose a recording or a spoken preview, not both.')
        if request.get('audio_asset_id') and request.get('audio_kind') not in ('clean_vocal', 'mixed'):
            raise InvalidRequestError('Identify the recording as clean vocal or mixed music.')
        for name, kind in (('image_asset_id', 'image'), ('audio_asset_id', 'audio'), ('beat_asset_id', 'audio')):
            value = request.get(name)
            if name == 'image_asset_id' or value:
                record = self.store.get_asset(value, owner_id)
                if record.kind != kind:
                    raise InvalidRequestError('Selected asset has the wrong media type.')
                self.assets.resolve(value, owner_id)
        if request.get('export_preset', 'source') not in ('source', 'vertical'):
            raise InvalidRequestError('Unsupported export preset.')
        seed = request.get('seed', 0)
        if type(seed) is not int or not 0 <= seed <= 2**64-1:
            raise InvalidRequestError('Invalid generation seed.')
        try:
            segment = float(request.get('audio_start_seconds', 0))
            if not math.isfinite(segment) or segment < 0:
                raise ValueError('segment')
        except (ValueError, TypeError) as exc:
            raise InvalidRequestError('Invalid audio segment start.') from exc
        if request.get('spoken_text') is not None:
            text = request['spoken_text']
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise InvalidRequestError('Provide 1 to 2000 characters of spoken-preview text.')
        return self.store.create_job(owner_id, request_key, request)

    def cancel(self, job_id: str, owner_id: str) -> bool:
        with self._lock:
            job = self.store.get_job(job_id, owner_id)
            if job.stage in TERMINAL:
                return False
            event = self._cancel.setdefault(job_id, Event())
            event.set()
            if job.stage == 'queued':
                try:
                    self.store.transition(job.id, 'queued', 'cancelled')
                except MediaConflictError:
                    pass  # scheduler acquired it; event requests stage-safe cancellation
            return True

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self.reconcile()
            self._stop.clear()
            self._thread = Thread(target=self._loop, name='nova-media-coordinator', daemon=True)
            self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            for event in self._cancel.values():
                event.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)

    def submit_existing(self, engine, operation: str, prompt: str, options: dict) -> dict:
        """Lease legacy gateway media without moving its historical outputs."""
        lease = 'legacy-' + uuid4().hex
        if not self.gate.acquire(lease):
            raise ProviderUnavailableError('Another media job or unresolved cleanup owns the resources.')
        try:
            result = getattr(engine, operation)(prompt, **options)
        except Exception:
            self.store.set_quarantine('Legacy submission acknowledgement failed; worker acceptance is unknown.')
            self.gate.release(lease)
            raise
        job_id = result.get('job_id') if isinstance(result, dict) else None
        if not job_id:
            self.store.set_quarantine('Legacy engine did not return a monitorable job identity.')
            self.gate.release(lease)
            raise ProviderUnavailableError('Legacy job submission state is unknown.')
        def monitor():
            try:
                deadline = time.monotonic() + 7200
                while not self._stop.is_set() and time.monotonic() < deadline:
                    status = engine.job_status(job_id, owner_id=options['owner_id'])
                    if status.get('status') in ('completed', 'failed', 'cancelled'):
                        # Legacy engines do not yet provide measured reclamation.
                        # An unload acknowledgement is not proof of free memory.
                        cleanup = getattr(engine, 'release_local_server', None)
                        if callable(cleanup):
                            cleanup()
                        raise ProviderUnavailableError('Legacy job ended; resource reclamation needs verified reconciliation.')
                    self._stop.wait(max(.05, self.poll_interval))
                raise ProviderUnavailableError('Legacy job monitoring interrupted before terminal state.')
            except Exception as exc:
                self.store.set_quarantine(str(exc))
            finally:
                self.gate.release(lease)
        Thread(target=monitor, name='nova-media-legacy-monitor', daemon=True).start()
        return result

    def reconcile(self) -> None:
        for job in self.store.recovery_jobs():
            if job.stage == 'queued':
                continue
            if (job.stage == 'generating_video' and job.external_id and job.backend_id == self.wan.backend_id
                    and self.wan.owns_prompt(job.external_id)):
                continue
            if job.stage in ('preparing', 'generating_video', 'saving_video', 'releasing_video'):
                self.store.set_quarantine('Interrupted worker custody needs reconciliation; no prompt was resubmitted.')
            self.store.transition(job.id, job.stage, 'interrupted',
                                  error='Interrupted stage; preserved artifacts available. Explicit retry required.')

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                jobs = self.store.recovery_jobs()
                if jobs:
                    job = jobs[0]
                    resuming = (job.stage == 'generating_video' and job.external_id
                                and self.wan.owns_prompt(job.external_id))
                    admitted, reason = ((True, 'Monitoring existing worker') if resuming else
                                        self.gate.admit(1024**3, self.required_ram_bytes))
                    retained_lease = resuming and self.store.lease_owner() == job.id and not self.store.get_quarantine()
                    if admitted and (retained_lease or self.gate.acquire(job.id)):
                        self._run_job(job)
                    elif job.stage == 'queued':
                        if admitted:
                            reason = 'Waiting for another Nova media job to release resources.'
                        if job.manifest.get('waiting_reason') != reason:
                            self.store.transition(job.id, 'queued', 'queued',
                                                  manifest={**job.manifest, 'waiting_reason': reason})
            except MediaConflictError:
                pass  # cancellation or a competing state transition won
            except Exception as exc:
                self.last_error = str(exc)
                self.store.set_quarantine('Coordinator stopped after an unexpected state error.')
            self._stop.wait(self.poll_interval)

    def _run_job(self, original: JobRecord) -> None:
        job = original
        with self._lock:
            cancel = self._cancel.setdefault(job.id, Event())
        started = False
        released = False
        release_attempted = False
        def advance(stage, **fields):
            nonlocal job
            job = self.store.transition(job.id, job.stage, stage, **fields)
        def release():
            nonlocal released, release_attempted, job
            release_attempted = True
            try:
                report = self.wan.release_owned()
            except Exception as exc:
                self.store.set_quarantine(str(exc))
                raise
            released = report.safe
            advance(job.stage, manifest={**job.manifest, 'release': asdict(report)})
            if not released:
                self.store.set_quarantine(report.reason)
            return report
        try:
            if cancel.is_set() or self._stop.is_set():
                raise MediaCancelledError()
            if job.stage == 'queued':
                advance('preparing', backend_id=self.wan.backend_id, manifest={})
                image = self.assets.resolve(job.request['image_asset_id'], job.owner_id)
                started = True  # startup failure can leave an owned process
                self.wan.start()
                if cancel.is_set() or self._stop.is_set():
                    raise MediaCancelledError()
                advance('generating_video')  # persist uncertain submission window first
                external_id = self.wan.submit(job, image)
                advance('generating_video', external_id=external_id)
            elif job.stage == 'generating_video' and self.wan.owns_prompt(job.external_id):
                started = True
            else:
                raise ProviderUnavailableError('Cannot safely resume this stage.')
            deadline = time.monotonic() + 3600
            while True:
                if self._stop.is_set():
                    raise ProviderUnavailableError('Nova shutdown interrupted worker monitoring.')
                if cancel.is_set() and self.wan.cancel(job.external_id):
                    raise MediaCancelledError()
                status = self.wan.poll(job.external_id)
                if status['stage'] == 'completed':
                    break
                if status['stage'] in ('failed', 'unknown'):
                    raise ProviderUnavailableError(status.get('error', 'Worker job state became unknown.'))
                if time.monotonic() >= deadline:
                    raise ProviderUnavailableError('Wan preview exceeded its one-hour deadline.')
                self._stop.wait(self.poll_interval)
            advance('saving_video')
            video = self.assets.root / 'outputs/previews' / job.id / 'video.mp4'
            self.wan.save_output(job.external_id, video)
            verified = self.exporter.verify(video, expected_audio=False)
            manifest = {**job.manifest, 'video': {'relative_path': video.relative_to(self.assets.root).as_posix(),
                        'sha256': file_hash(video), 'size_bytes': video.stat().st_size, 'metadata': verified}}
            advance('releasing_video', manifest=manifest)
            report = release()
            if not report.safe:
                advance('interrupted', cleanup_error=report.reason)
                return
            if cancel.is_set() or self._stop.is_set():
                raise MediaCancelledError()
            admitted, reason = self.gate.admit(1024**3, self.required_ram_bytes)
            if not admitted:
                raise ProviderUnavailableError('Next stage blocked: ' + reason)
            advance('preparing_audio')
            vocal = self.assets.resolve(job.request['audio_asset_id'], job.owner_id) if job.request.get('audio_asset_id') else None
            beat = self.assets.resolve(job.request['beat_asset_id'], job.owner_id) if job.request.get('beat_asset_id') else None
            if job.request.get('spoken_text'):
                vocal = self.voice.render(job.request['spoken_text'], self.assets.root / 'inputs/audio' / (job.id + '-spoken.wav'), cancel_event=cancel)
            if cancel.is_set() or self._stop.is_set():
                raise MediaCancelledError()
            advance('exporting')
            output = self.exporter.export(job, video, vocal, beat, cancel_event=cancel)
            advance('verifying', manifest={**job.manifest, 'final': asdict(output)})
            advance('completed')
        except Exception as exc:
            cleanup_error = None
            if started and not release_attempted:
                try:
                    report = release()
                    if not report.safe:
                        cleanup_error = report.reason
                except Exception as cleanup:
                    cleanup_error = str(cleanup)
                    self.store.set_quarantine(cleanup_error)
            if job.stage not in TERMINAL:
                advance('cancelled' if isinstance(exc, MediaCancelledError) else 'failed',
                        error=str(exc), cleanup_error=cleanup_error)
        finally:
            self.gate.release(job.id)
            with self._lock:
                self._cancel.pop(job.id, None)
