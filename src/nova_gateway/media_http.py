"""Scoped studio routes; caller paths and owner IDs are never accepted."""
from dataclasses import asdict
import json
import re
from urllib.parse import parse_qs

from .errors import InvalidRequestError, PermissionDeniedError, ProviderUnavailableError
from .media_assets import contained_path, file_hash
from .media_export import OVERLAY_LABEL


def _length(handler, maximum):
    headers = handler.headers
    if headers.get('Transfer-Encoding') or (hasattr(headers, 'get_all') and len(headers.get_all('Content-Length', [])) != 1):
        raise InvalidRequestError('A single Content-Length without transfer encoding is required.')
    value = headers.get('Content-Length', '')
    if not isinstance(value, str) or not value.isdecimal() or not 0 < int(value) <= maximum:
        raise InvalidRequestError('Missing, invalid or oversized request length.')
    return int(value)


def _public_job(job):
    # No server paths, prompts, external worker IDs or raw manifests in listings.
    outputs = []
    for name in ('video', 'final'):
        item = job.manifest.get(name)
        if isinstance(item, dict) and item.get('relative_path'):
            outputs.append({'id': name, 'download_path': f'/nova/v1/studio/jobs/{job.id}/outputs/{name}'})
    return {'id': job.id, 'stage': job.stage, 'created_at': job.created_at,
            'updated_at': job.updated_at, 'error': job.error, 'cleanup_error': job.cleanup_error,
            'waiting_reason': job.manifest.get('waiting_reason'), 'outputs': outputs,
            'native_width': 384, 'native_height': 480, 'frames': 17, 'fps': 24,
            'duration_seconds': 17/24, 'label': OVERLAY_LABEL if any(job.request.get(key) for key in
                ('audio_asset_id', 'beat_asset_id', 'spoken_text')) else 'generated motion — no audio'}


def handle_studio(parent, handler, parsed, method: str) -> bool:
    if not parsed.path.startswith('/nova/v1/studio/'):
        return False
    if not parent.config.enabled:
        return False
    try:
        auth = parent._authorize(handler, None)
        def require(*scopes):
            missing = set(scopes) - set(auth.scopes)
            # The explicitly enabled local media workflow can ingest its own
            # bounded assets; this grants no generic files.write elsewhere.
            if (missing == {'files.write'} and auth.client_id == 'local-client' and auth.local
                    and parent.config.allow_local_media and 'video.generate' in auth.scopes):
                missing.clear()
            if missing:
                raise PermissionDeniedError('Studio requires scopes: ' + ', '.join(sorted(missing)))
        path = parsed.path[len('/nova/v1/studio/'):]
        if method == 'POST':
            handler.close_connection = True  # unread rejected bodies cannot become another request
        if path == 'assets' and method == 'POST':
            require('files.write')
        elif path == 'jobs' and method == 'POST':
            require('video.generate', 'files.read', 'admin.models')
        elif path.endswith('/cancel') and method == 'POST':
            require('video.generate')
        else:
            require('files.read')
        app = getattr(parent.core, 'studio', None)
        if path == 'status' and method == 'GET':
            parent_scopes = {'video.generate', 'files.read', 'admin.models'}
            handler._send_json({'enabled': app is not None, 'can_submit': app is not None and parent_scopes <= set(auth.scopes),
                                'memory_profile_ready': bool(app and app.required_ram_bytes > 0),
                                'quarantine': app.store.get_quarantine() if app else None,
                                'duration_seconds': 17/24, 'frames': 17, 'fps': 24,
                                'native_width': 384, 'native_height': 480})
            return True
        if app is None:
            raise ProviderUnavailableError('Managed studio is not enabled in this Nova server.')
        if path == 'assets' and method == 'POST':
            query = parse_qs(parsed.query)
            if set(query) != {'kind'} or len(query['kind']) != 1 or query['kind'][0] not in app.assets.LIMITS:
                raise InvalidRequestError('Choose one image or audio upload kind.')
            kind = query['kind'][0]
            length = _length(handler, app.assets.LIMITS[kind])
            if getattr(handler, 'connection', None):
                handler.connection.settimeout(30)
            record = app.assets.ingest(auth.client_id, kind, handler.rfile, length)
            handler._send_json({'id': record.id, 'kind': record.kind, 'size_bytes': record.size_bytes,
                                'sha256': record.sha256, 'metadata': record.metadata}, status=201)
            return True
        if path == 'jobs' and method == 'POST':
            length = _length(handler, 16384)
            if getattr(handler, 'connection', None):
                handler.connection.settimeout(30)
            raw = handler.rfile.read(length)
            if len(raw) != length:
                raise InvalidRequestError('Truncated studio request.')
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise InvalidRequestError('Invalid studio JSON.') from exc
            if not isinstance(payload, dict):
                raise InvalidRequestError('Studio request must be an object.')
            request_key = payload.pop('request_key', None)
            job = app.submit(auth.client_id, request_key, payload)
            handler._send_json(_public_job(job), status=202)
            return True
        if path == 'jobs' and method == 'GET':
            handler._send_json({'data': [_public_job(job) for job in app.store.list_jobs(auth.client_id)[-100:]][::-1]})
            return True
        match = re.fullmatch(r'jobs/([a-zA-Z0-9_-]{1,100})(?:/(cancel|outputs/(?:video|final)))?', path)
        if not match:
            raise InvalidRequestError('Unknown studio route.')
        job_id, action = match.groups()
        job = app.store.get_job(job_id, auth.client_id)
        if action == 'cancel' and method == 'POST':
            handler._send_json({'ok': app.cancel(job_id, auth.client_id)})
        elif action is None and method == 'GET':
            handler._send_json(_public_job(job))
        elif action and action.startswith('outputs/') and method == 'GET':
            item = job.manifest.get(action.split('/')[1])
            if not isinstance(item, dict):
                raise InvalidRequestError('That output is not available yet.')
            output = contained_path(app.assets.root, item['relative_path'])
            if not output.is_file() or output.stat().st_size != item['size_bytes'] or file_hash(output) != item['sha256']:
                raise InvalidRequestError('Saved output is unavailable or has changed.')
            size = output.stat().st_size
            range_header = handler.headers.get('Range')
            selected = parent._parse_range_header(range_header, size)
            if range_header and selected is None:
                handler.send_response(416)
                handler.send_header('Content-Range', f'bytes */{size}')
                handler.send_header('Content-Length', '0')
                handler.end_headers()
                return True
            start, end = selected or (0, size-1)
            handler.send_response(206 if selected else 200)
            handler.send_header('Content-Type', 'video/mp4')
            handler.send_header('Content-Length', str(end-start+1))
            handler.send_header('Accept-Ranges', 'bytes')
            handler.send_header('Cache-Control', 'private, no-store')
            if selected:
                handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            handler._send_cors_headers()
            handler.end_headers()
            with output.open('rb') as stream:
                stream.seek(start)
                remaining = end-start+1
                while remaining:
                    chunk = stream.read(min(65536, remaining))
                    if not chunk or not handler._write_bytes(chunk):
                        break
                    remaining -= len(chunk)
        else:
            raise InvalidRequestError('Unsupported studio route method.')
    except Exception as exc:
        parent._send_error(handler, exc)
    return True
