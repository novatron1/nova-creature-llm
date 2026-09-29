"""Wan adapter binds the installed graph and refuses destructive worker adoption."""
import json
from pathlib import Path
import shutil

import pytest
from nova_gateway.errors import ProviderUnavailableError, InvalidRequestError
from nova_gateway.media_store import JobRecord, MediaStore
from nova_gateway.media_resources import ResourceGate


def adapter(tmp_path):
    from nova_gateway.media_wan import WanAdapter
    root = tmp_path / 'studio'
    (root / 'workflows').mkdir(parents=True)
    shutil.copyfile(Path('NOVA_LOCAL_VIDEO_STUDIO/workflows/lil_ammo_wan_api.json'),
                    root / 'workflows/lil_ammo_wan_api.json')
    return WanAdapter(root, tmp_path / 'runtime', tmp_path / 'python.exe',
                      ResourceGate(root, MediaStore(tmp_path / 'jobs.db')))


def test_binds_reference_without_changing_profile_or_source(tmp_path):
    app = adapter(tmp_path)
    path = app.root / 'workflows/lil_ammo_wan_api.json'
    original = path.read_bytes()
    job = JobRecord('abc123', 'alice', 'click', {'prompt': 'small nod', 'seed': 91})
    graph = app.build_workflow(job, 'managed.png')
    assert graph['56']['inputs']['image'] == 'managed.png'
    assert graph['6']['inputs']['text'] == 'small nod'
    assert graph['3']['inputs']['seed'] == 91
    assert graph['55']['inputs']['length'] == 17
    assert graph['55']['inputs']['width'] == 384
    assert graph['55']['inputs']['height'] == 480
    assert graph['57']['inputs']['fps'] == 24
    assert graph['58']['inputs']['filename_prefix'] == 'NOVA_MANAGED/abc123/video'
    assert path.read_bytes() == original
    with pytest.raises(InvalidRequestError):
        app.build_workflow(JobRecord('abc', 'a', 'k', {'duration': 5}), 'a.png')


def test_missing_model_prevents_submission(tmp_path):
    app = adapter(tmp_path)
    graph = app.build_workflow(JobRecord('abc', 'a', 'k', {'prompt': 'nod', 'seed': 1}), 'a.png')
    info = {node['class_type']: {'input': {'required': {}}} for node in graph.values()}
    info['UNETLoader']['input']['required']['unet_name'] = [['wrong-model.safetensors']]
    with pytest.raises(ProviderUnavailableError):
        app.validate_workflow(graph, info)


def test_external_or_exited_worker_is_never_adopted_or_released(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    monkeypatch.setattr(app, '_port_open', lambda: True)
    with pytest.raises(ProviderUnavailableError):
        app.start()
    result = app.release_owned()
    assert not result.safe and not result.unload_requested and not result.stopped
    assert app.cancel('foreign') is False


def test_busy_worker_and_unsaved_output_block_release(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    from nova_gateway.media_resources import ResourceSnapshot
    monkeypatch.setattr(app.gate, 'snapshot', lambda: ResourceSnapshot(1, 1, 1, 'now'))
    class Process:
        def poll(self): return None
    app._process = Process()
    app._submitted.add('owned')
    app._request = lambda *args: (_ for _ in ()).throw(AssertionError('unsaved output must block request'))
    assert not app.release_owned().safe
    app._saved.add('owned')
    def busy(method, path, payload=None):
        assert method == 'GET' and path == '/queue', 'mutation of busy worker'
        return {'queue_running': [[0, 'foreign']], 'queue_pending': []}
    app._request = busy
    result = app.release_owned()
    assert not result.safe and not result.unload_requested
    assert not app.cancel('owned')


def test_failed_connection_ownership_refuses_mutation(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    class Process:
        def poll(self): return None
    app._process = Process()
    class Connection:
        auto_open = 1
        def connect(self): pass
        def close(self): pass
        def request(self, *args, **kwargs): raise AssertionError('unverified mutation')
    monkeypatch.setattr(app, '_connection', lambda: Connection())
    monkeypatch.setattr(app, '_owns_connection', lambda conn: False)
    with pytest.raises(ProviderUnavailableError):
        app._request('POST', '/free', {'unload_models': True})


def test_unload_ack_alone_is_not_release_confirmation(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    from nova_gateway.media_resources import ResourceSnapshot
    monkeypatch.setattr(app.gate, 'snapshot', lambda: ResourceSnapshot(1, 1, 1, 'now'))
    class Process:
        def poll(self): return None
    app._process = Process()
    app._request = lambda method, path, payload=None: {'queue_running': [], 'queue_pending': []} if path == '/queue' else {}
    app.release_timeout_seconds = 0
    assert app.release_owned().safe is False
    app._idle_rss = 512*1024**2
    app._idle_gpu_free = 4*1024**3
    monkeypatch.setattr(app, '_worker_rss', lambda: 500*1024**2)
    monkeypatch.setattr(app.gate, 'snapshot', lambda: ResourceSnapshot(6*1024**3, 20*1024**3, 4*1024**3, 'later'))
    result = app.release_owned()
    assert result.safe and result.unload_requested and not result.stopped


def test_submit_and_poll_bind_exact_worker_job(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    image = tmp_path / 'reference.png'
    image.write_bytes(b'image fixture')
    job = JobRecord('abc', 'alice', 'key', {'prompt': 'nod', 'seed': 7})
    base = json.loads((app.root / 'workflows/lil_ammo_wan_api.json').read_text())
    info = {node['class_type']: {'input': {'required': {}}} for node in base.values()}
    for node in base.values():
        for name in ('unet_name', 'clip_name', 'vae_name'):
            if name in node['inputs']:
                info[node['class_type']]['input']['required'][name] = [[node['inputs'][name]]]
    def request(method, path, payload=None):
        if path == '/object_info': return info
        if path == '/prompt':
            assert payload['prompt']['56']['inputs']['image'] == 'uploaded.png'
            assert payload['prompt']['3']['inputs']['seed'] == 7
            return {'prompt_id': 'worker-1', 'number': 0, 'node_errors': {}}
        if path == '/history/worker-1':
            return {'worker-1': {'status': {'completed': True, 'status_str': 'success'},
                                'outputs': {'58': {'images': [{'filename': 'video.mp4', 'subfolder': 'NOVA_MANAGED/abc', 'type': 'output'}]}}}}
        raise AssertionError(path)
    monkeypatch.setattr(app, '_request', request)
    monkeypatch.setattr(app, '_upload_image', lambda path: 'uploaded.png')
    assert app.submit(job, image) == 'worker-1'
    assert app.poll('worker-1')['stage'] == 'completed'
    with pytest.raises(ProviderUnavailableError):
        app.poll('foreign')


def test_first_launch_records_idle_footprint(tmp_path, monkeypatch):
    app = adapter(tmp_path)
    app.python.write_bytes(b'placeholder')
    app.runtime.mkdir()
    (app.runtime / 'main.py').write_text('')
    (app.root / 'config').mkdir()
    (app.root / 'config/extra_model_paths.yaml').write_text('')
    class Process:
        pid = 123
        def poll(self): return None
        def create_time(self): return 12.0
    import nova_gateway.media_wan as module
    import psutil
    from nova_gateway.media_resources import ResourceSnapshot
    monkeypatch.setattr(module.subprocess, 'Popen', lambda *args, **kwargs: Process())
    monkeypatch.setattr(psutil, 'Process', lambda pid: Process())
    monkeypatch.setattr(app, '_port_open', lambda: False)
    monkeypatch.setattr(app, '_request', lambda *args: {})
    monkeypatch.setattr(app, '_worker_rss', lambda: 100)
    monkeypatch.setattr(app.gate, 'snapshot', lambda: ResourceSnapshot(1000, 1000, 900, 'now'))
    app.start()
    assert app._idle_rss == 100 and app._idle_gpu_free == 900


def test_output_copy_is_durable_and_failed_copy_preserves_previous(tmp_path, monkeypatch):
    import io
    app = adapter(tmp_path)
    app._submitted.add('worker-1')
    monkeypatch.setattr(app, 'poll', lambda _: {'stage': 'completed', 'entry': {
        'outputs': {'58': {'images': [{'filename': 'v.mp4', 'subfolder': 'NOVA_MANAGED/abc', 'type': 'output'}]}}}})
    class Response(io.BytesIO):
        status = 200
    class Connection:
        auto_open = 1
        def connect(self): pass
        def close(self): pass
        def request(self, method, path):
            assert method == 'GET' and path.startswith('/view?')
        def getresponse(self): return Response(b'mp4 fixture bytes')
    monkeypatch.setattr(app, '_connection', lambda: Connection())
    monkeypatch.setattr(app, '_owns_connection', lambda _: True)
    destination = app.root / 'outputs/previews/abc/video.mp4'
    assert app.save_output('worker-1', destination).read_bytes() == b'mp4 fixture bytes'
    assert 'worker-1' in app._saved
    monkeypatch.setattr(app, '_owns_connection', lambda _: False)
    with pytest.raises(ProviderUnavailableError):
        app.save_output('worker-1', destination)
    assert destination.read_bytes() == b'mp4 fixture bytes'
    assert not list(destination.parent.glob('*.part'))
