import json
import os

import pytest

from tools.nova_symlink_sandbox_proof import validate
import tools.nova_symlink_sandbox_proof as proof


def evidence():
    return dict(schema_version=1, run_id='run', nonce='nonce', backend='windows_sandbox',
                passed=True, payload_sha256={'nova_release_policy.py': 'source-hash'},
                reparse_tag=0xA000000C, paths=['assets/linked'], classification='ambiguous',
                rule='filesystem_link_requires_boundary_check', sentinel_scanned=False)


def test_real_symlink_evidence_schema():
    result = evidence()
    assert validate(json.dumps(result).encode(), 'run', 'nonce', result['payload_sha256']) == result


@pytest.mark.parametrize('field,value', [
    ('nonce', 'stale'), ('run_id', 'stale'), ('passed', 1), ('backend', 'host'),
    ('reparse_tag', 0xA0000003), ('paths', ['assets/linked/sentinel.txt']),
    ('classification', 'include'), ('sentinel_scanned', True),
    ('payload_sha256', {'nova_release_policy.py': 'changed'}),
])
def test_rejects_stale_or_non_symlink_evidence(field, value):
    result = evidence()
    payload = result['payload_sha256'].copy()
    result[field] = value
    with pytest.raises(ValueError):
        validate(json.dumps(result).encode(), 'run', 'nonce', payload)


def test_rejects_extra_or_duplicate_evidence():
    result = evidence()
    encoded = json.dumps(result)
    for data in (json.dumps(dict(result, extra=True)), encoded.replace('"nonce": "nonce"',
                  '"nonce": "nonce", "nonce": "nonce"')):
        with pytest.raises(ValueError):
            validate(data.encode(), 'run', 'nonce', result['payload_sha256'])


def test_teardown_waits_for_owned_processes_then_mapping_release(monkeypatch):
    from unittest.mock import Mock

    containment = Mock()
    containment.process.poll.return_value = 1
    containment.process.returncode = 1
    containment.terminate_and_verify.return_value = True
    released = Mock(side_effect=[False, True])
    sleep = Mock()
    monkeypatch.setattr(proof, '_files_released', released)
    monkeypatch.setattr(proof.time, 'sleep', sleep)
    result = proof._teardown_and_wait(containment, ('input.dll',), 60)
    containment.terminate_and_verify.assert_called_once()
    assert released.call_count == 2
    assert sleep.call_count == 1
    assert result == dict(method='deliberate_windows_job_teardown', processes_stopped=True,
                          supervisor_exit_code=1, mapped_files_released=True)


def test_teardown_deadline_rejects_locked_mapping(monkeypatch):
    from unittest.mock import Mock

    containment = Mock()
    containment.process.poll.return_value = 1
    containment.terminate_and_verify.return_value = True
    monkeypatch.setattr(proof, '_files_released', lambda paths: False)
    monkeypatch.setattr(proof.time, 'sleep', Mock())
    monkeypatch.setattr(proof.time, 'monotonic', Mock(side_effect=[0, 1, 61]))
    status = dict(method='deliberate_windows_job_teardown',
                  processes_stopped=False, mapped_files_released=False)
    with pytest.raises(TimeoutError, match='mapped files were released'):
        proof._teardown_and_wait(containment, ('input.dll',), 60, status)
    assert status['processes_stopped'] is True
    assert status['mapped_files_released'] is False


@pytest.mark.parametrize('verified,returncode', [(False, 1), (True, None)])
def test_teardown_rejects_unverified_or_still_running_processes(monkeypatch, verified, returncode):
    from unittest.mock import Mock

    containment = Mock()
    containment.terminate_and_verify.return_value = verified
    containment.process.poll.return_value = returncode
    released = Mock()
    monkeypatch.setattr(proof, '_files_released', released)
    with pytest.raises(RuntimeError, match='could not verify stopped processes'):
        proof._teardown_and_wait(containment, (), 60)
    released.assert_not_called()


@pytest.mark.skipif(os.name != 'nt', reason='Windows exclusive file-handle coverage')
def test_release_probe_observes_real_open_handle_without_changing_file(tmp_path):
    path = tmp_path / 'mapped-input.bin'
    path.write_bytes(b'unchanged payload')
    with path.open('rb'):
        assert not proof._files_released((tmp_path, path))
    assert proof._files_released((tmp_path, path))
    assert path.read_bytes() == b'unchanged payload'


@pytest.mark.skipif(os.name != 'nt', reason='Windows exclusive directory-handle coverage')
def test_release_probe_waits_for_mapped_directory_handle(tmp_path):
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(tmp_path), 0x80000000, 7, None, 3, 0x02000000, None)
    assert handle != wintypes.HANDLE(-1).value
    try:
        assert not proof._files_released((tmp_path,))
    finally:
        assert kernel.CloseHandle(handle)
    assert proof._files_released((tmp_path,))
    assert tmp_path.is_dir()


@pytest.mark.parametrize('cleanup_timeout', [False, True])
def test_guest_timeout_waits_for_mapping_cleanup_and_preserves_failure(
    tmp_path, monkeypatch, cleanup_timeout
):
    from unittest.mock import Mock

    python_home = tmp_path / 'minimal-python'
    (python_home / 'DLLs').mkdir(parents=True)
    (python_home / 'Lib').mkdir()
    monkeypatch.setattr(proof.sys, 'base_prefix', str(python_home))
    monkeypatch.setattr(proof, 'find_sandbox', lambda: 'test-only-no-launch')
    containment = Mock()
    containment.process.poll.return_value = None
    containment.process.stdout = containment.process.stderr = None

    def terminate():
        containment.process.poll.return_value = 1
        return True

    containment.terminate_and_verify.side_effect = terminate
    launch = Mock(return_value=containment)
    monkeypatch.setattr(proof, '_launch_contained_process', launch)
    released = Mock(side_effect=[False, True])
    monkeypatch.setattr(proof, '_files_released', released)
    monkeypatch.setattr(proof.time, 'sleep', Mock())
    result = proof.run_proof(tmp_path / 'artifacts', timeout=0,
                             shutdown_timeout=0 if cleanup_timeout else 60)
    assert result['passed'] is False
    assert result['reason'] == 'Sandbox timed out without symlink evidence'
    assert result['teardown']['processes_stopped'] is True
    containment.terminate_and_verify.assert_called_once()
    if cleanup_timeout:
        assert result['teardown']['mapped_files_released'] is False
        assert 'timed out' in result['teardown']['error']
        released.assert_not_called()
    else:
        assert result['teardown']['mapped_files_released'] is True
        assert result['teardown']['input_unchanged'] is True
        assert released.call_count == 2
        assert any(path.name == 'input' for path in released.call_args.args[0])
