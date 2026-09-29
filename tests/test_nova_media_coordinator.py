"""Backend scheduling uses real custody/ingestion with external worker doubles."""
from dataclasses import replace
import io
from pathlib import Path
import shutil
import time

from PIL import Image
import pytest
from nova_gateway.media_assets import AssetService
from nova_gateway.media_store import MediaStore, OutputRecord
from nova_gateway.media_resources import ResourceGate, ResourceSnapshot, ReleaseResult


def coordinator(tmp_path, monkeypatch, *, release_safe=True, export_fails=False):
    from nova_gateway.media_coordinator import MediaCoordinator
    store = MediaStore(tmp_path / 'state/media.sqlite3')
    assets = AssetService(tmp_path, store, Path(shutil.which('ffprobe')))
    stream = io.BytesIO()
    Image.new('RGB', (8, 8), 'blue').save(stream, 'PNG')
    image = assets.ingest('alice', 'image', io.BytesIO(stream.getvalue()), len(stream.getvalue()))
    gate = ResourceGate(tmp_path, store)
    snapshot = ResourceSnapshot(8*1024**3, 30*1024**3, 6*1024**3, 'now')
    monkeypatch.setattr(gate, 'snapshot', lambda: snapshot)
    events = []
    class Worker:
        backend_id = 'wan_studio_8190'
        def start(self): events.append('start')
        def submit(self, job, path):
            assert path.is_file()
            events.append('submit')
            return 'worker-' + job.id
        def poll(self, external_id): return {'stage': 'completed'}
        def save_output(self, external_id, destination):
            events.append('save')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'video fixture')
            return destination
        def release_owned(self):
            events.append('release')
            return ReleaseResult(release_safe, True, False, snapshot, snapshot, 'test measurement')
        def cancel(self, external_id): return False
        def owns_prompt(self, external_id): return False
    class Exporter:
        def verify(self, path, expected_audio):
            assert path.read_bytes() == b'video fixture'
            return {'streams': []}
        def export(self, job, video, vocal, beat, **kwargs):
            assert events.index('save') < events.index('release')
            events.append('export')
            if export_fails: raise RuntimeError('encoder failed')
            return OutputRecord('final', 'outputs/final/test.mp4', 'a'*64, 10, {})
    class Voice:
        def render(self, text, destination, **kwargs):
            assert events.index('release') < len(events)
            events.append('voice')
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b'voice fixture')
            return destination
    app = MediaCoordinator(store, assets, gate, Worker(), Exporter(), Voice(),
                           required_ram_bytes=4*1024**3, poll_interval=.01)
    payload = {'image_asset_id': image.id, 'prompt': 'small nod', 'seed': 1}
    return app, payload, events


def wait_terminal(app, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        record = app.store.get_job(job.id, job.owner_id)
        if record.stage in ('completed', 'failed', 'cancelled', 'interrupted'):
            return record
        time.sleep(.01)
    pytest.fail('coordinator did not finish')


def test_browser_free_fifo_execution_and_release_before_audio(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    first = app.submit('alice', 'one', {**payload, 'spoken_text': 'stock preview'})
    assert app.submit('alice', 'one', {**payload, 'spoken_text': 'stock preview'}).id == first.id
    second = app.submit('alice', 'two', payload)
    app.start()
    try:
        assert wait_terminal(app, first).stage == 'completed'
        assert wait_terminal(app, second).stage == 'completed'
        assert events == ['start', 'submit', 'save', 'release', 'voice', 'export', 'start', 'submit', 'save', 'release', 'export']
    finally:
        app.shutdown()
        app.shutdown()


def test_cancel_queued_job_never_submits(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    job = app.submit('alice', 'one', payload)
    assert app.cancel(job.id, 'alice')
    app.start()
    try:
        assert wait_terminal(app, job).stage == 'cancelled'
        assert events == []
    finally: app.shutdown()


def test_uncertain_release_blocks_next_job_and_audio(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch, release_safe=False)
    first = app.submit('alice', 'one', {**payload, 'spoken_text': 'preview'})
    second = app.submit('alice', 'two', payload)
    app.start()
    try:
        result = wait_terminal(app, first)
        assert result.stage == 'interrupted'
        assert result.manifest['video']['relative_path'].endswith('video.mp4')
        assert app.store.get_quarantine()
        assert not app.gate.acquire('another')
        assert app.store.get_job(second.id, 'alice').stage == 'queued'
        assert 'voice' not in events and 'export' not in events
    finally: app.shutdown()


def test_failed_export_retains_generated_video(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch, export_fails=True)
    job = app.submit('alice', 'one', payload)
    app.start()
    try:
        result = wait_terminal(app, job)
        assert result.stage == 'failed' and result.error == 'encoder failed'
        assert (app.assets.root / result.manifest['video']['relative_path']).read_bytes() == b'video fixture'
        assert events.count('release') == 1
    finally: app.shutdown()


@pytest.mark.parametrize('external_id', [None, 'worker-saved'])
def test_crash_window_never_resubmits_or_adopts_lost_worker(tmp_path, monkeypatch, external_id):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    job = app.submit('alice', 'one', payload)
    app.store.transition(job.id, 'queued', 'preparing', backend_id='wan_studio_8190')
    app.store.transition(job.id, 'preparing', 'generating_video', external_id=external_id)
    app.reconcile()
    assert app.store.get_job(job.id, 'alice').stage == 'interrupted'
    assert app.store.get_quarantine()
    assert events == []


def test_existing_lease_prevents_wan_admission(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    assert app.gate.acquire('existing-animatediff')
    job = app.submit('alice', 'one', payload)
    app.start()
    try:
        time.sleep(.1)
        assert app.store.get_job(job.id, 'alice').stage == 'queued'
        assert events == []
        app.gate.release('existing-animatediff')
        assert wait_terminal(app, job).stage == 'completed'
    finally: app.shutdown()


def test_release_exception_quarantines_resources(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    def broken_release(): raise RuntimeError('socket ownership lost')
    app.wan.release_owned = broken_release
    job = app.submit('alice', 'one', payload)
    app.start()
    try:
        assert wait_terminal(app, job).stage == 'failed'
        assert app.store.get_quarantine() == 'socket ownership lost'
        assert 'export' not in events
    finally: app.shutdown()


def test_owned_running_prompt_resumes_monitoring_without_memory_readmission(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    job = app.submit('alice', 'one', payload)
    app.store.transition(job.id, 'queued', 'preparing', backend_id=app.wan.backend_id)
    app.store.transition(job.id, 'preparing', 'generating_video', external_id='known-prompt')
    assert app.gate.acquire(job.id)
    app.wan.owns_prompt = lambda identifier: identifier == 'known-prompt'
    # Loaded model has consumed admission headroom; it still must be monitored.
    monkeypatch.setattr(app.gate, 'admit', lambda *args: (False, 'model currently loaded'))
    app.start()
    try:
        result = wait_terminal(app, job)
        assert result.stage == 'failed'  # later audio admission fails honestly
        assert events == ['save', 'release']
        assert result.manifest['video']
    finally: app.shutdown()


def test_core_legacy_video_cannot_bypass_studio_lease(tmp_path, monkeypatch):
    from nova_gateway.core import NovaGatewayCore
    from nova_gateway.config import GatewayConfig
    from nova_gateway.errors import ProviderUnavailableError
    app, payload, events = coordinator(tmp_path, monkeypatch)
    core = NovaGatewayCore(lambda *args: ('ok', {}), config=GatewayConfig(),
                           register_ollama=False, studio=app)
    class Engine:
        engine_id = 'nova-animatediff-gpu'
        def health_check(self): return {'ok': True}
        def text_to_video(self, prompt, **options):
            raise AssertionError('heavy engine admitted despite occupied lease')
    core.animatediff_gpu = Engine()
    assert app.gate.acquire('wan')
    with pytest.raises(ProviderUnavailableError):
        core.generate_video({'prompt': 'nod', 'engine_id': 'nova-animatediff-gpu'}, client_id='alice')


def test_legacy_job_quarantines_without_verified_cleanup(tmp_path, monkeypatch):
    from threading import Event
    app, payload, events = coordinator(tmp_path, monkeypatch)
    finished = Event()
    class Engine:
        def text_to_video(self, prompt, **options): return {'job_id': 'legacy-1', 'status': 'queued'}
        def job_status(self, job_id, *, owner_id):
            assert job_id == 'legacy-1' and owner_id == 'alice'
            return {'status': 'completed' if finished.is_set() else 'running'}
    result = app.submit_existing(Engine(), 'text_to_video', 'nod', {'owner_id': 'alice'})
    assert result['job_id'] == 'legacy-1'
    assert not app.gate.acquire('wan')
    finished.set()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if app.store.get_quarantine():
            break
        time.sleep(.01)
    else: pytest.fail('terminal legacy job did not quarantine unverified cleanup')
    assert not app.gate.acquire('wan')


def test_ambiguous_legacy_transport_failure_quarantines(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    class Engine:
        def generate_image(self, prompt, **options): raise TimeoutError('ack lost')
    with pytest.raises(TimeoutError):
        app.submit_existing(Engine(), 'generate_image', 'nod', {'owner_id': 'alice'})
    assert app.store.get_quarantine()
    assert not app.gate.acquire('wan')


def test_shutdown_during_release_never_starts_audio_or_export(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    release = app.wan.release_owned
    def stop_then_release():
        app._stop.set()
        return release()
    app.wan.release_owned = stop_then_release
    job = app.submit('alice', 'one', {**payload, 'spoken_text': 'preview'})
    app.gate.acquire(job.id)
    app._run_job(job)
    assert 'voice' not in events and 'export' not in events
    assert app.store.get_job(job.id, 'alice').stage != 'completed'


def test_registered_image_tool_cannot_bypass_lease(tmp_path, monkeypatch):
    from nova_gateway.core import NovaGatewayCore
    from nova_gateway.config import GatewayConfig
    from nova_gateway.errors import ProviderUnavailableError
    from nova_gateway.tools import NovaToolRegistry
    app, payload, events = coordinator(tmp_path, monkeypatch)
    core = NovaGatewayCore(lambda *args: ('ok', {}), config=GatewayConfig(comfyui_enabled=True),
                           register_ollama=False, studio=app, tools=NovaToolRegistry())
    assert app.gate.acquire('wan')
    def forbidden(*args, **kwargs): raise AssertionError('tool bypassed lease')
    monkeypatch.setattr(core.comfyui, 'generate_image', forbidden)
    with pytest.raises(ProviderUnavailableError):
        core.tools.get('nova_generate_image').handler({'prompt': 'nod'})


def test_shutdown_signals_active_owned_child(tmp_path, monkeypatch):
    from threading import Event
    app, payload, events = coordinator(tmp_path, monkeypatch)
    entered = Event()
    def render(text, destination, *, cancel_event=None):
        entered.set()
        assert cancel_event is not None
        assert cancel_event.wait(2), 'shutdown did not cancel owned voice child'
        from nova_gateway.media_export import MediaCancelledError
        raise MediaCancelledError()
    app.voice.render = render
    job = app.submit('alice', 'one', {**payload, 'spoken_text': 'preview'})
    app.start()
    assert entered.wait(2)
    app.shutdown()
    assert app.store.get_job(job.id, 'alice').stage == 'cancelled'
    assert 'export' not in events


def test_resume_cannot_bypass_shared_media_lease(tmp_path, monkeypatch):
    from nova_gateway.core import NovaGatewayCore
    from nova_gateway.config import GatewayConfig
    from nova_gateway.errors import ProviderUnavailableError
    app, payload, events = coordinator(tmp_path, monkeypatch)
    core = NovaGatewayCore(lambda *args: ('ok', {}), config=GatewayConfig(),
                           register_ollama=False, studio=app)
    class Engine:
        def resume_job(self, *args, **kwargs): raise AssertionError('resume bypassed lease')
    monkeypatch.setattr(core, '_media_engine_for_job', lambda _: Engine())
    assert app.gate.acquire('wan')
    with pytest.raises(ProviderUnavailableError):
        core.resume_media_job('legacy-id', client_id='alice')
