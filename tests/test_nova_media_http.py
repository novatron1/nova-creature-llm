"""Scoped studio HTTP requests through the actual gateway controller."""
import io
import json
from types import SimpleNamespace
from urllib.parse import urlsplit
import sys
from pathlib import Path

from PIL import Image
import pytest
from nova_gateway.auth import NovaAuthenticator, NovaClientRegistry
from nova_gateway.config import GatewayConfig
from nova_gateway.http import NovaGatewayHttpController
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_nova_media_coordinator import coordinator


class Handler:
    client_address = ('127.0.0.1', 4444)
    def __init__(self, body=b'', headers=None):
        self.headers = {'Content-Length': str(len(body)), **(headers or {})}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.response_headers = {}
        self.status = None
        self.close_connection = False
    def _send_json(self, value, status=200):
        self.status = status
        self.value = value
    def send_response(self, status): self.status = status
    def send_header(self, name, value): self.response_headers[name] = value
    def end_headers(self): pass
    def _send_cors_headers(self): pass
    def _write_bytes(self, value): self.wfile.write(value); return True


def controller(tmp_path, monkeypatch):
    app, payload, events = coordinator(tmp_path, monkeypatch)
    config = GatewayConfig(rate_limit_enabled=False, allow_local_no_auth=False)
    registry = NovaClientRegistry()
    registry.add_client('alice', 'Alice', 'test-alice', {'files.read', 'files.write', 'video.generate', 'admin.models'}, persist=False)
    registry.add_client('bob', 'Bob', 'test-bob', {'files.read', 'files.write', 'video.generate'}, persist=False)
    return app, payload, NovaGatewayHttpController(SimpleNamespace(studio=app), NovaAuthenticator(config, registry, env={}), config)


def call(api, method, path, payload=None, key='test-alice', raw=None, headers=None):
    body = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else b'')
    handler = Handler(body, {'Authorization': 'Bearer ' + key, **(headers or {})})
    assert api.recognizes(urlsplit(path).path)
    assert getattr(api, 'handle_' + method.lower())(handler, urlsplit(path))
    return handler


def test_auth_before_body_and_scope_before_job_submission(tmp_path, monkeypatch):
    app, payload, api = controller(tmp_path, monkeypatch)
    response = call(api, 'POST', '/nova/v1/studio/assets?kind=image', raw=b'do not read', key='invalid')
    assert response.status == 401 and response.rfile.tell() == 0
    response = call(api, 'POST', '/nova/v1/studio/jobs', {'request_key': 'one', **payload}, key='test-bob')
    assert response.status == 403 and not app.store.list_jobs('bob')


def test_upload_limits_and_forged_fields_rejected(tmp_path, monkeypatch):
    app, payload, api = controller(tmp_path, monkeypatch)
    for headers in ({'Content-Length': str(25*1024**2+1)}, {'Transfer-Encoding': 'chunked'}, {'Content-Length': ''}):
        result = call(api, 'POST', '/nova/v1/studio/assets?kind=image', raw=b'not read', headers=headers)
        assert result.status in (400, 413, 411) and result.rfile.tell() == 0
    response = call(api, 'POST', '/nova/v1/studio/jobs', {'request_key': 'one', **payload, 'owner_id': 'bob'})
    assert response.status == 400


def test_uploaded_asset_and_duplicate_job_are_owner_scoped(tmp_path, monkeypatch):
    app, payload, api = controller(tmp_path, monkeypatch)
    image = io.BytesIO()
    Image.new('RGB', (8, 8)).save(image, 'PNG')
    upload = call(api, 'POST', '/nova/v1/studio/assets?kind=image', raw=image.getvalue())
    assert upload.status == 201
    assert 'relative_path' not in upload.value
    request = {**payload, 'image_asset_id': upload.value['id'], 'request_key': 'one'}
    first = call(api, 'POST', '/nova/v1/studio/jobs', request)
    second = call(api, 'POST', '/nova/v1/studio/jobs', request)
    assert first.status == second.status == 202 and first.value['id'] == second.value['id']
    foreign = call(api, 'GET', '/nova/v1/studio/jobs/' + first.value['id'], key='test-bob')
    assert foreign.status == 403


def test_download_range_survives_worker_absence(tmp_path, monkeypatch):
    from nova_gateway.media_assets import file_hash
    app, payload, api = controller(tmp_path, monkeypatch)
    job = app.submit('alice', 'one', payload)
    artifact = tmp_path / 'outputs/previews/video.mp4'
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b'0123456789')
    app.store.transition(job.id, 'queued', 'queued', manifest={'video': {
        'relative_path': 'outputs/previews/video.mp4', 'sha256': file_hash(artifact), 'size_bytes': 10}})
    result = call(api, 'GET', f'/nova/v1/studio/jobs/{job.id}/outputs/video', headers={'Range': 'bytes=2-5'})
    assert result.status == 206 and result.wfile.getvalue() == b'2345'
    assert result.response_headers['Content-Range'] == 'bytes 2-5/10'


def test_paired_device_does_not_inherit_model_admin(tmp_path, monkeypatch):
    app, payload, api = controller(tmp_path, monkeypatch)
    handler = Handler(json.dumps({'request_key': 'one', **payload}).encode())
    handler._paired_device = {'device_id': 'phone', 'scopes': ['video.generate']}
    handler._paired_device_local = False
    assert api.handle_post(handler, urlsplit('/nova/v1/studio/jobs'))
    assert handler.status == 403


def test_pipeline_script_is_served_by_real_static_controller():
    from nova_foundation_http import FoundationHttpController
    root = Path(__file__).resolve().parents[1]
    controller = FoundationHttpController(lambda: None, root)
    handler = Handler()
    assert controller.handle_get(handler, urlsplit('/assets/nova_studio_pipeline.js'))
    assert handler.status == 200
    assert handler.response_headers['Content-Type'].startswith('application/javascript')
    assert handler.wfile.getvalue() == (root / 'assets/nova_studio_pipeline.js').read_bytes()
@pytest.mark.parametrize('payload,has_audio', [({}, False), ({'audio_asset_id': 'recording'}, True), ({'spoken_text': 'preview'}, True)])
def test_public_job_label_matches_audio_selection(payload, has_audio):
    from nova_gateway.media_http import _public_job
    from nova_gateway.media_store import JobRecord
    label = _public_job(JobRecord('job', 'alice', 'key', payload))['label']
    assert ('audio overlay' in label) == has_audio
