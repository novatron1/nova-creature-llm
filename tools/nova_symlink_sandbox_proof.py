"""Prove the product directory-symlink scan in a disposable Windows Sandbox."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nova_windows_sandbox import build_config, find_sandbox, _read_result, _unique
from nova_release_gates import _launch_contained_process, _sanitized_environment

GUEST = r'''import hashlib, json, os, pathlib, stat, sys, tempfile
sys.path.insert(0, r'C:\NovaInput')
from nova_release_policy import SnapshotPolicy, SnapshotClass, scan_workspace
base = pathlib.Path(r'C:\NovaInput')
plan = json.loads((base / 'plan.json').read_text())
result = dict(schema_version=1, run_id=plan['run_id'], nonce=plan['nonce'],
              backend='windows_sandbox', passed=False)
try:
    hashes = {name: hashlib.sha256((base / name).read_bytes()).hexdigest()
              for name in plan['payload_sha256']}
    assert hashes == plan['payload_sha256'], 'guest payload hashes differ'
    with tempfile.TemporaryDirectory(prefix='nova-symlink-') as temp:
        temp = pathlib.Path(temp)
        repo = temp / 'repo'
        assets = repo / 'assets'
        assets.mkdir(parents=True)
        external = temp / 'external'
        external.mkdir()
        (external / 'sentinel.txt').write_text('must not be scanned', encoding='utf-8')
        link = assets / 'linked'
        link.symlink_to(external, target_is_directory=True)
        tag = link.lstat().st_reparse_tag
        assert os.name == 'nt' and tag == stat.IO_REPARSE_TAG_SYMLINK
        assert link.is_symlink() and link.is_dir()
        policy = SnapshotPolicy.load(base / 'policy.json')
        report = scan_workspace(repo, policy, tracked_paths=set(), deleted_paths=set())
        paths = [item.path for item in report.decisions]
        assert paths == ['assets/linked'], paths
        assert report.decisions[0].classification is SnapshotClass.AMBIGUOUS
        assert report.decisions[0].rule == 'filesystem_link_requires_boundary_check'
        assert 'assets/linked/sentinel.txt' not in paths
        result.update(passed=True, payload_sha256=hashes, reparse_tag=tag,
                      paths=paths, classification=report.decisions[0].classification.value,
                      rule=report.decisions[0].rule, sentinel_scanned=False)
except Exception as exc:
    result['error'] = repr(exc)
out = pathlib.Path(r'C:\NovaOutput')
(out / 'result.tmp').write_text(json.dumps(result), encoding='utf-8')
(out / 'result.tmp').replace(out / 'result.json')
'''

BOOTSTRAP = r'''$ErrorActionPreference = 'Stop'
try {
 $diagnostic = @(& C:\NovaInput\python\python.exe -I -S C:\NovaInput\guest.py 2>&1)
 if ($LASTEXITCODE -ne 0) { throw ('Python exit ' + $LASTEXITCODE + ': ' + ($diagnostic -join "`n")) }
} catch {
 [IO.File]::WriteAllText('C:\NovaOutput\bootstrap-error.txt', $_.ToString())
}
shutdown.exe /s /t 0
'''


def hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


def validate(data, run_id, nonce, payload):
    result = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique)
    expected = dict(schema_version=1, run_id=run_id, nonce=nonce,
                    backend='windows_sandbox', passed=True, payload_sha256=payload,
                    reparse_tag=0xA000000C, paths=['assets/linked'], classification='ambiguous',
                    rule='filesystem_link_requires_boundary_check', sentinel_scanned=False)
    if not isinstance(result, dict) or result.keys() != expected.keys():
        raise ValueError('invalid guest evidence: ' + repr(result))
    if any(type(result[k]) is not type(v) or result[k] != v for k, v in expected.items()):
        raise ValueError('guest evidence mismatch')
    return result


def _files_released(paths):
    """Probe exclusive read handles without changing or deleting the inputs."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                       wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = (wintypes.HANDLE,)
    close.restype = wintypes.BOOL
    handles = []
    try:
        for path in paths:
            flags = 0x02000000 if path.is_dir() else 0x80  # BACKUP_SEMANTICS for directory handles.
            handle = create(str(path), 0x80000000, 0, None, 3, flags, None)
            if handle == wintypes.HANDLE(-1).value:
                error = ctypes.get_last_error()
                if error in (32, 33):  # Sharing or lock violation during teardown.
                    return False
                raise ctypes.WinError(error)
            handles.append(handle)
        return True
    finally:
        for handle in handles:
            close(handle)


def _teardown_and_wait(containment, paths, timeout, status=None):
    deadline = time.monotonic() + timeout
    if status is None:
        status = dict(method='deliberate_windows_job_teardown',
                      processes_stopped=False, mapped_files_released=False)
    # The pinned Job was assigned before the supervisor launched Sandbox. Its
    # descendants are deliberately stopped; exit zero is not a guest guarantee.
    verified = containment.terminate_and_verify()
    code = containment.process.poll()
    status.update(processes_stopped=bool(verified and code is not None),
                  supervisor_exit_code=code)
    if not status['processes_stopped']:
        raise RuntimeError('Sandbox owned Job teardown could not verify stopped processes')
    while time.monotonic() < deadline:
        if _files_released(paths):
            status['mapped_files_released'] = True
            return status
        time.sleep(0.25)
    raise TimeoutError('Sandbox teardown timed out before mapped files were released')


def run_proof(artifact_root, timeout=180, shutdown_timeout=60):
    report = dict(passed=False, backend='windows_sandbox', os_sandbox=False,
                  teardown=dict(method='deliberate_windows_job_teardown',
                                processes_stopped=False, mapped_files_released=False))
    executable = find_sandbox()
    if not executable:
        return dict(report, reason='Windows Sandbox unavailable')
    run_id, nonce = secrets.token_hex(16), secrets.token_hex(32)
    run = artifact_root.resolve() / run_id
    input_dir, output_dir = run / 'input', run / 'output'
    runtime = input_dir / 'python'
    runtime.mkdir(parents=True)
    output_dir.mkdir()
    # Only interpreter binaries and standard-library sources; no site packages,
    # user profile, environment, repository mount, or application data.
    python_home = Path(sys.base_prefix)
    for pattern in ('python.exe', 'python3*.dll', 'vcruntime*.dll'):
        for p in python_home.glob(pattern):
            shutil.copy2(p, runtime / p.name)
    (runtime / 'DLLs').mkdir()
    for p in (python_home / 'DLLs').iterdir():
        if p.suffix.lower() in ('.dll', '.pyd'):
            shutil.copy2(p, runtime / 'DLLs' / p.name)
    stdlib = python_home / 'Lib'
    with zipfile.ZipFile(runtime / f'python{sys.version_info.major}{sys.version_info.minor}.zip',
                         'w', zipfile.ZIP_DEFLATED) as bundle:
        for directory, subdirs, files in os.walk(stdlib):
            subdirs[:] = [name for name in subdirs if name not in
                          {'site-packages', '__pycache__', 'test', 'tests', 'idlelib', 'tkinter'}]
            for name in files:
                if name.endswith('.py'):
                    p = Path(directory) / name
                    bundle.write(p, p.relative_to(stdlib).as_posix())
    (runtime / 'Lib').mkdir()
    shutil.copy2(ROOT / 'src/nova_release_policy.py', input_dir / 'nova_release_policy.py')
    shutil.copy2(ROOT / 'config/nova_release_snapshot_policy.json', input_dir / 'policy.json')
    (input_dir / 'guest.py').write_text(GUEST, encoding='utf-8')
    (input_dir / 'bootstrap.ps1').write_text(BOOTSTRAP, encoding='utf-8')
    payload = hashes(input_dir)
    (input_dir / 'plan.json').write_text(json.dumps(dict(run_id=run_id, nonce=nonce,
                                                       payload_sha256=payload)), encoding='utf-8')
    before = hashes(input_dir)
    config = run / 'proof.wsb'
    config.write_text(build_config(input_dir, output_dir), encoding='utf-8')
    report.update(run_id=run_id, artifact_dir=str(run), input_sha256=before)
    containment = None
    teardown_attempted = False
    try:
        deadline = time.monotonic() + timeout
        containment = _launch_contained_process([executable, str(config)], cwd=run,
                                               environment=_sanitized_environment(ROOT, None),
                                               deadline=deadline)
        process = containment.process
        report['supervisor_pid'] = process.pid
        result_path = output_dir / 'result.json'
        while not result_path.exists():
            diagnostic = output_dir / 'bootstrap-error.txt'
            if diagnostic.exists():
                raise RuntimeError('Guest bootstrap failed: ' + _read_result(diagnostic).decode('utf-8-sig'))
            if process.poll() not in (None, 0):
                raise RuntimeError(f'Sandbox launcher failed: {process.returncode}')
            if time.monotonic() >= deadline:
                raise TimeoutError('Sandbox timed out without symlink evidence')
            time.sleep(0.25)
        if {p.name for p in output_dir.iterdir()} != {'result.json'}:
            raise ValueError('unexpected guest output files')
        data = _read_result(result_path)
        evidence = validate(data, run_id, nonce, payload)
        report.update(evidence=evidence, result_sha256=hashlib.sha256(data).hexdigest())
        if hashes(input_dir) != before:
            raise ValueError('host input changed')
        teardown_attempted = True
        report['teardown'] = _teardown_and_wait(
            containment, (run, *run.rglob('*')), shutdown_timeout,
            report['teardown'])
        if hashes(input_dir) != before:
            raise ValueError('host input changed during teardown')
        report.update(passed=True, os_sandbox=True)
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        report['reason'] = str(exc)
    finally:
        if containment is not None:
            if not teardown_attempted:
                try:
                    _teardown_and_wait(containment, (run, *run.rglob('*')), shutdown_timeout,
                                       report['teardown'])
                    report['teardown']['input_unchanged'] = hashes(input_dir) == before
                    if not report['teardown']['input_unchanged']:
                        report['teardown']['error'] = 'host input changed during failure cleanup'
                except (OSError, ValueError, RuntimeError, TimeoutError) as cleanup_error:
                    report['teardown']['error'] = str(cleanup_error)
            for stream in (containment.process.stdout, containment.process.stderr):
                if stream is not None:
                    stream.close()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = run_proof(args.output.parent / 'symlink-sandbox-artifacts', args.timeout)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'input_sha256'}, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
