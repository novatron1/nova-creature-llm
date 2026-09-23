import json
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from src.nova_windows_sandbox import build_config, validate_result, run_proof, FIXTURE_HASH, EDITED_HASH, _read_result


def valid():
    return dict(schema_version=1, run_id='run', nonce='nonce', candidate_before=FIXTURE_HASH,
                candidate_after=FIXTURE_HASH, edited_sha256=EDITED_HASH,
                terminal_exit_code=0, terminal_output='hello, nova',
                backend='windows_sandbox', passed=True)


def test_config_minimal_mounts(tmp_path):
    root = ET.fromstring(build_config(tmp_path / 'input', tmp_path / 'output'))
    for name in ('Networking', 'ClipboardRedirection', 'PrinterRedirection', 'AudioInput', 'VideoInput', 'vGPU'):
        assert root.findtext(name) == 'Disable'
    assert root.findtext('ProtectedClient') == 'Enable'
    mounts = root.findall('MappedFolders/MappedFolder')
    assert len(mounts) == 2
    assert [m.findtext('ReadOnly') for m in mounts] == ['true', 'false']


@pytest.mark.parametrize('field,value', [('nonce','old'), ('run_id','old'), ('candidate_after','bad'),
    ('candidate_before','bad'), ('edited_sha256','bad'), ('terminal_exit_code',1),
    ('terminal_exit_code',False), ('passed',1), ('terminal_output','wrong'), ('backend','host')])
def test_reject_invalid_evidence(field, value):
    payload = valid()
    payload[field] = value
    with pytest.raises(ValueError):
        validate_result(json.dumps(payload).encode(), run_id='run', nonce='nonce')


def test_strict_and_bounded_schema():
    assert validate_result(json.dumps(valid()).encode(), run_id='run', nonce='nonce')['passed']
    for data in (b'{}', b'broken', b' '*65537, json.dumps(dict(valid(), path='C:/host')).encode(),
                 json.dumps(valid()).replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1').encode()):
        with pytest.raises(ValueError):
            validate_result(data, run_id='run', nonce='nonce')


def test_unavailable_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setattr('src.nova_windows_sandbox.find_sandbox', lambda: None)
    report = run_proof(tmp_path)
    assert report['passed'] is False
    assert report['reason'] == 'Windows Sandbox unavailable'


def test_result_rejects_hardlinks(tmp_path):
    import os
    target = tmp_path / 'target'
    target.write_text('{}')
    link = tmp_path / 'result.json'
    os.link(target, link)
    with pytest.raises(ValueError, match='unsafe'):
        _read_result(link)


@pytest.mark.parametrize('mode', ['timeout', 'malformed', 'input_changed', 'extra_file'])
def test_provider_failures(tmp_path, monkeypatch, mode):
    import src.nova_windows_sandbox as sandbox
    monkeypatch.setattr(sandbox, 'find_sandbox', lambda: 'test-only-provider')

    class FakeProcess:
        returncode = None

        def __init__(self, command, **kwargs):
            run = Path(command[1]).parent
            if mode == 'timeout':
                return
            plan = json.loads((run / 'input/plan.json').read_text())
            result = dict(valid(), **plan)
            (run / 'output/result.json').write_text('broken' if mode == 'malformed' else json.dumps(result))
            if mode == 'input_changed':
                (run / 'input/candidate.ps1').write_text('changed')
            if mode == 'extra_file':
                (run / 'output/unexpected').write_text('extra')

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = 1

        def wait(self, **kwargs):
            return self.returncode

    monkeypatch.setattr(sandbox.subprocess, 'Popen', FakeProcess)
    report = run_proof(tmp_path, timeout=0)
    assert report['passed'] is False
    assert report['os_sandbox'] is False
    assert report['reason']
