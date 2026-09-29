"""Dedicated Wan studio adapter; never adopts an existing port or kills workers."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from threading import RLock
import time
from urllib.parse import quote, urlencode
from uuid import uuid4

from .comfyui import ComfyUIEngine
from .media_assets import contained_path
from .errors import InvalidRequestError, ProviderUnavailableError
from .media_resources import ReleaseResult, ResourceGate
from .media_store import JobRecord


class WanAdapter:
    backend_id = 'wan_studio_8190'

    def __init__(self, root: Path, runtime: Path, python: Path, gate: ResourceGate):
        self.root = Path(root).resolve()
        self.runtime = Path(runtime).resolve()
        self.python = Path(python).resolve()
        self.gate = gate
        self._process = None
        self._process_created = None
        self._lock = RLock()
        self._submitted: set[str] = set()
        self._saved: set[str] = set()
        self._idle_rss = None
        self._idle_gpu_free = None
        self.release_timeout_seconds = 30

    def _port_open(self) -> bool:
        try:
            with socket.create_connection(('127.0.0.1', 8190), timeout=1):
                return True
        except OSError:
            return False

    def _connection(self):
        return http.client.HTTPConnection('127.0.0.1', 8190, timeout=30)

    def _owns_connection(self, connection) -> bool:
        if self._process is None or self._process.poll() is not None:
            return False
        try:
            import psutil
            process = psutil.Process(self._process.pid)
            if (process.create_time() != self._process_created
                    or Path(process.exe()).resolve() != self.python):
                return False
        except (OSError, ImportError, RuntimeError):
            return False
        except Exception:
            return False
        return ComfyUIEngine._connection_owned_by(connection, self._process)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        connection = self._connection()
        try:
            connection.connect()
            if not self._owns_connection(connection):
                raise ProviderUnavailableError('Wan worker connection ownership could not be verified.')
            connection.auto_open = 0
            body = json.dumps(payload).encode() if payload is not None else None
            connection.request(method, path, body, {'Content-Type': 'application/json'})
            response = connection.getresponse()
            raw = response.read(8*1024**2+1)
            if response.status != 200 or len(raw) > 8*1024**2:
                raise ProviderUnavailableError('Wan returned an invalid or oversized response.')
            result = json.loads(raw or b'{}')
            if not isinstance(result, dict):
                raise ValueError('object response required')
            return result
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise ProviderUnavailableError('Wan request failed; no automatic resubmission.') from exc
        finally:
            connection.close()

    def start(self) -> None:
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                self._request('GET', '/system_stats')
                if self._idle_rss is None:
                    self._idle_rss = self._worker_rss()
                    self._idle_gpu_free = self.gate.snapshot().gpu_free_bytes
                return
            if self._port_open():
                raise ProviderUnavailableError('Port 8190 belongs to an unowned worker; it was not adopted.')
            config = self.root / 'config/extra_model_paths.yaml'
            if not self.python.is_file() or not (self.runtime / 'main.py').is_file() or not config.is_file():
                raise ProviderUnavailableError('The installed Wan runtime or studio configuration is missing.')
            logs = self.root / 'logs'
            logs.mkdir(parents=True, exist_ok=True)
            command = [str(self.python), 'main.py', '--listen', '127.0.0.1', '--port', '8190',
                       '--base-directory', str(self.root), '--database-url',
                       'sqlite:///' + (self.root / 'comfyui-studio.db').as_posix(),
                       '--extra-model-paths-config', str(config)]
            with (logs / 'managed-wan.out.log').open('ab') as out, (logs / 'managed-wan.err.log').open('ab') as err:
                self._process = subprocess.Popen(command, cwd=self.runtime, stdout=out, stderr=err,
                                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            import psutil
            self._process_created = psutil.Process(self._process.pid).create_time()
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and self._process.poll() is None:
            try:
                self._request('GET', '/system_stats')
                self._idle_rss = self._worker_rss()
                self._idle_gpu_free = self.gate.snapshot().gpu_free_bytes
                return
            except ProviderUnavailableError:
                time.sleep(.5)
        raise ProviderUnavailableError('Owned Wan worker did not become ready; inspect managed-wan logs.')

    def _worker_rss(self) -> int | None:
        try:
            import psutil
            if self._process is None or self._process.poll() is not None:
                return None
            process = psutil.Process(self._process.pid)
            if process.create_time() != self._process_created:
                return None
            return process.memory_info().rss + sum(p.memory_info().rss for p in process.children(recursive=True))
        except Exception:
            return None

    def _upload_image(self, path: Path) -> str:
        size = path.stat().st_size
        if not 0 < size <= 25*1024**2 or path.suffix.lower() not in ('.png', '.jpg', '.webp'):
            raise InvalidRequestError('Invalid managed reference image.')
        name = uuid4().hex + path.suffix.lower()
        boundary = 'nova' + uuid4().hex
        prefix = (f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{name}"\r\n'
                  'Content-Type: application/octet-stream\r\n\r\n').encode()
        suffix = f'\r\n--{boundary}--\r\n'.encode()
        def body():
            yield prefix
            with path.open('rb') as source:
                while chunk := source.read(1024*1024):
                    yield chunk
            yield suffix
        connection = self._connection()
        try:
            connection.connect()
            if not self._owns_connection(connection):
                raise ProviderUnavailableError('Cannot verify Wan upload destination ownership.')
            connection.auto_open = 0
            connection.request('POST', '/upload/image', body(),
                               {'Content-Type': 'multipart/form-data; boundary=' + boundary,
                                'Content-Length': str(len(prefix)+size+len(suffix))})
            response = connection.getresponse()
            raw = response.read(65537)
            if response.status != 200 or len(raw) > 65536:
                raise ValueError('upload rejected')
            record = json.loads(raw)
            if record.get('name') != name or record.get('subfolder', '') != '' or record.get('type', 'input') != 'input':
                raise ValueError('unexpected upload path')
            return name
        except (OSError, ValueError, http.client.HTTPException) as exc:
            raise ProviderUnavailableError('Wan image upload failed.') from exc
        finally:
            connection.close()

    def submit(self, job: JobRecord, image: Path) -> str:
        with self._lock:
            graph = self.build_workflow(job, 'reference.png')
            self.validate_workflow(graph, self._request('GET', '/object_info'))
            graph['56']['inputs']['image'] = self._upload_image(image)
            result = self._request('POST', '/prompt', {'prompt': graph, 'client_id': 'nova-managed-' + job.id})
            external_id = result.get('prompt_id')
            if not isinstance(external_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,200}', external_id) or result.get('node_errors'):
                raise ProviderUnavailableError('Wan did not confirm an accepted prompt.')
            self._submitted.add(external_id)
            return external_id

    def poll(self, external_id: str) -> dict:
        if external_id not in self._submitted:
            raise ProviderUnavailableError('Wan prompt custody is unavailable; no job was adopted.')
        history = self._request('GET', '/history/' + quote(external_id, safe=''))
        entry = history.get(external_id)
        if isinstance(entry, dict):
            status = entry.get('status', {})
            if status.get('status_str') == 'error':
                self._saved.add(external_id)  # no output expected for failed execution
                return {'stage': 'failed', 'error': 'Wan execution failed; inspect worker log.'}
            if status.get('completed') and status.get('status_str') == 'success':
                return {'stage': 'completed', 'entry': entry}
        queue = self._request('GET', '/queue')
        for key, stage in (('queue_running', 'running'), ('queue_pending', 'queued')):
            if any(isinstance(item, list) and len(item) > 1 and item[1] == external_id for item in queue.get(key, [])):
                return {'stage': stage}
        return {'stage': 'unknown'}

    def owns_prompt(self, external_id: str) -> bool:
        return external_id in self._submitted and self._process is not None and self._process.poll() is None

    def save_output(self, external_id: str, destination: Path) -> Path:
        if external_id not in self._submitted:
            raise ProviderUnavailableError('Cannot save an unowned Wan output.')
        status = self.poll(external_id)
        if status.get('stage') != 'completed':
            raise ProviderUnavailableError('Wan output is not complete.')
        items = status['entry'].get('outputs', {}).get('58', {}).get('images', [])
        selected = None
        for item in items:
            if (isinstance(item, dict) and re.fullmatch(r'[a-zA-Z0-9_.-]+\.mp4', str(item.get('filename', '')))
                    and item.get('type') == 'output'
                    and re.fullmatch(r'NOVA_MANAGED/[a-zA-Z0-9_-]+', str(item.get('subfolder', '')))):
                selected = {name: item[name] for name in ('filename', 'subfolder', 'type')}
                break
        if selected is None:
            raise ProviderUnavailableError('Wan did not produce a managed MP4 output.')
        try:
            relative = Path(destination).absolute().relative_to(self.root).as_posix()
        except ValueError as exc:
            raise InvalidRequestError('Output destination must be inside the studio.') from exc
        destination = contained_path(self.root, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = contained_path(self.root, relative + '.' + uuid4().hex + '.part')
        connection = self._connection()
        try:
            connection.connect()
            if not self._owns_connection(connection):
                raise ProviderUnavailableError('Cannot verify output worker ownership.')
            connection.auto_open = 0
            connection.request('GET', '/view?' + urlencode(selected))
            response = connection.getresponse()
            if response.status != 200:
                raise ProviderUnavailableError('Wan output download failed.')
            total = 0
            with temporary.open('xb') as output:
                while chunk := response.read(1024*1024):
                    total += len(chunk)
                    if total > 1024**3:
                        raise ProviderUnavailableError('Wan output exceeded the 1 GiB preview limit.')
                    output.write(chunk)
                if total == 0:
                    raise ProviderUnavailableError('Wan output was empty.')
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
            self._saved.add(external_id)
            return destination
        except (OSError, http.client.HTTPException) as exc:
            raise ProviderUnavailableError('Wan output could not be saved; existing copy preserved.') from exc
        finally:
            connection.close()
            temporary.unlink(missing_ok=True)

    def build_workflow(self, job: JobRecord, image_name: str) -> dict:
        allowed = {'image_asset_id', 'prompt', 'seed', 'audio_asset_id', 'audio_kind',
                   'audio_start_seconds', 'beat_asset_id', 'spoken_text', 'export_preset'}
        if job.request.keys() - allowed or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', job.id):
            raise InvalidRequestError('Unsupported Wan job settings.')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,180}', image_name) or '..' in image_name:
            raise InvalidRequestError('Invalid managed reference name.')
        prompt = job.request.get('prompt', '')
        seed = job.request.get('seed', 0)
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
            raise InvalidRequestError('Provide a performance description of 1 to 4000 characters.')
        if type(seed) is not int or not 0 <= seed <= 2**64-1:
            raise InvalidRequestError('Invalid Wan seed.')
        path = self.root / 'workflows/lil_ammo_wan_api.json'
        if path.stat().st_size > 4*1024**2:
            raise InvalidRequestError('Wan workflow is oversized.')
        graph = json.loads(path.read_text(encoding='utf-8'))
        graph['56']['inputs']['image'] = image_name
        graph['6']['inputs']['text'] = prompt
        graph['3']['inputs']['seed'] = seed
        graph['58']['inputs']['filename_prefix'] = 'NOVA_MANAGED/' + job.id + '/video'
        profile = graph['55']['inputs']
        if ((profile['width'], profile['height'], profile['length']) != (384, 480, 17)
                or graph['57']['inputs']['fps'] != 24):
            raise InvalidRequestError('Saved workflow differs from the verified small preview profile.')
        return graph

    @staticmethod
    def validate_workflow(graph: dict, object_info: dict) -> None:
        for node in graph.values():
            info = object_info.get(node.get('class_type'))
            if not isinstance(info, dict):
                raise ProviderUnavailableError('Required Wan node is not installed.')
            inputs = node.get('inputs', {})
            for name in ('unet_name', 'clip_name', 'vae_name'):
                if name in inputs:
                    declaration = info.get('input', {}).get('required', {}).get(name, [])
                    choices = declaration[0] if declaration else None
                    if not isinstance(choices, list) or inputs[name] not in choices:
                        raise ProviderUnavailableError('Required Wan model is not installed: ' + str(inputs[name]))

    def cancel(self, external_id: str) -> bool:
        # Running ComfyUI interruption is global; never use it on a shared queue.
        with self._lock:
            if external_id not in self._submitted or self._process is None or self._process.poll() is not None:
                return False
            queue = self._request('GET', '/queue')
            running, pending = queue.get('queue_running'), queue.get('queue_pending')
            if not isinstance(running, list) or not isinstance(pending, list) or running:
                return False
            if any(not isinstance(item, list) or len(item) < 2 or item[1] != external_id for item in pending):
                return False
            if not pending:
                return False
            self._request('POST', '/queue', {'delete': [external_id]})
            self._saved.add(external_id)  # cancelled before execution: no output to retain
            return True

    def release_owned(self) -> ReleaseResult:
        before = self.gate.snapshot()
        def result(safe=False, requested=False, reason=''):
            return ReleaseResult(safe, requested, False, before, self.gate.snapshot(), reason)
        with self._lock:
            if self._process is None or self._process.poll() is not None:
                return result(reason='Worker custody is absent; no process was changed.')
            if self._submitted - self._saved:
                return result(reason='Job outputs have not been durably saved.')
            try:
                queue = self._request('GET', '/queue')
                if queue.get('queue_running') != [] or queue.get('queue_pending') != []:
                    return result(reason='Worker is busy or queue state is unknown.')
                self._request('POST', '/free', {'unload_models': True, 'free_memory': True})
                # Acknowledgement alone is not proof. Require measured return to
                # startup footprint AND idle queue. Never describe this as all RAM free.
                deadline = time.monotonic() + self.release_timeout_seconds
                while True:
                    after = self.gate.snapshot()
                    rss = self._worker_rss()
                    margin = 256*1024**2
                    if (self._idle_rss is not None and self._idle_gpu_free is not None and rss is not None
                            and after.gpu_free_bytes is not None and rss <= self._idle_rss + margin
                            and after.gpu_free_bytes >= self._idle_gpu_free - margin):
                        queue = self._request('GET', '/queue')
                        if queue.get('queue_running') == [] and queue.get('queue_pending') == []:
                            return ReleaseResult(True, True, False, before, after,
                                                 'Owned worker returned to its measured startup footprint; recheck next-stage admission.')
                    if time.monotonic() >= deadline:
                        return result(requested=True, reason='Unload requested; return to startup memory footprint was not verified.')
                    time.sleep(.5)
            except ProviderUnavailableError as exc:
                return result(reason=str(exc))
