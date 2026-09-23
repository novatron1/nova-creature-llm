"""A real Windows Sandbox terminal fixture proof; never falls back to host execution.

This proves the isolated terminal capability, not the whole product/release suite.
Only a generated fixture/bootstrap is shared, never the repository or user profile.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import time
import xml.etree.ElementTree as ET

FIXTURE = b'Write-Output "hello"\r\n'
EDITED = b'Write-Output "hello, nova"\r\n'
FIXTURE_HASH = hashlib.sha256(FIXTURE).hexdigest()
EDITED_HASH = hashlib.sha256(EDITED).hexdigest()
MAX_RESULT = 65536


def find_sandbox():
    return shutil.which('WindowsSandbox.exe') if os.name == 'nt' else None


def build_config(input_dir: Path, output_dir: Path) -> str:
    root = ET.Element('Configuration')
    for name in ('Networking', 'ClipboardRedirection', 'PrinterRedirection', 'AudioInput', 'VideoInput', 'vGPU'):
        ET.SubElement(root, name).text = 'Disable'
    ET.SubElement(root, 'ProtectedClient').text = 'Enable'
    ET.SubElement(root, 'MemoryInMB').text = '2048'
    mounts = ET.SubElement(root, 'MappedFolders')
    for host, guest, readonly in ((input_dir, r'C:\NovaInput', 'true'), (output_dir, r'C:\NovaOutput', 'false')):
        folder = ET.SubElement(mounts, 'MappedFolder')
        ET.SubElement(folder, 'HostFolder').text = str(host.resolve())
        ET.SubElement(folder, 'SandboxFolder').text = guest
        ET.SubElement(folder, 'ReadOnly').text = readonly
    command = ET.SubElement(root, 'LogonCommand')
    ET.SubElement(command, 'Command').text = r'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File C:\NovaInput\bootstrap.ps1'
    return ET.tostring(root, encoding='unicode')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate result field')
        result[key] = value
    return result


def validate_result(data: bytes, *, run_id: str, nonce: str) -> dict:
    if len(data) > MAX_RESULT:
        raise ValueError('oversized sandbox result')
    try:
        result = json.loads(data.decode('utf-8-sig'), object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('malformed sandbox result') from exc
    expected = dict(schema_version=1, run_id=run_id, nonce=nonce,
                    candidate_before=FIXTURE_HASH, candidate_after=FIXTURE_HASH,
                    edited_sha256=EDITED_HASH, terminal_exit_code=0,
                    terminal_output='hello, nova', backend='windows_sandbox', passed=True)
    if not isinstance(result, dict) or set(result) != set(expected):
        raise ValueError('invalid sandbox result fields')
    for key, value in expected.items():
        if type(result[key]) is not type(value) or result[key] != value:
            raise ValueError('sandbox result mismatch: ' + key)
    return result


BOOTSTRAP = r'''$ErrorActionPreference = 'Stop'
$plan = Get-Content -LiteralPath C:\NovaInput\plan.json -Raw | ConvertFrom-Json
$before = (Get-FileHash C:\NovaInput\candidate.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
$work = Join-Path $env:TEMP ('nova-' + $plan.run_id)
New-Item -ItemType Directory -Path $work | Out-Null
$candidate = Join-Path $work 'candidate.ps1'
Copy-Item -LiteralPath C:\NovaInput\candidate.ps1 -Destination $candidate
$text = [IO.File]::ReadAllText($candidate).Replace('hello', 'hello, nova')
[IO.File]::WriteAllText($candidate, $text, [Text.UTF8Encoding]::new($false))
$terminal = @(& powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $candidate)
$terminalCode = $LASTEXITCODE
$after = (Get-FileHash C:\NovaInput\candidate.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
$edited = (Get-FileHash $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
$result = @{
 schema_version=1; run_id=$plan.run_id; nonce=$plan.nonce;
 candidate_before=$before; candidate_after=$after; edited_sha256=$edited;
 terminal_exit_code=$terminalCode; terminal_output=($terminal -join "`n");
 backend='windows_sandbox'; passed=($terminalCode -eq 0 -and ($terminal -join "`n") -ceq 'hello, nova')
}
[IO.File]::WriteAllText('C:\NovaOutput\result.tmp', ($result | ConvertTo-Json -Compress), [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath C:\NovaOutput\result.tmp -Destination C:\NovaOutput\result.json
shutdown.exe /s /t 0
'''


def _read_result(path: Path) -> bytes:
    """Bounded, handle-pinned read; reject links/reparse points and concurrent edits."""
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or getattr(before, 'st_file_attributes', 0) & 0x400:
        raise ValueError('unsafe sandbox result path')
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('sandbox result path changed')
        data = stream.read(MAX_RESULT + 1)
        after = os.fstat(stream.fileno())
    if (opened.st_size, opened.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('sandbox result changed while reading')
    return data


def run_proof(artifact_root: Path, *, timeout: float = 180) -> dict:
    report = dict(passed=False, backend='windows_sandbox', os_sandbox=False)
    executable = find_sandbox()
    if not executable:
        return dict(report, reason='Windows Sandbox unavailable')
    run_id, nonce = secrets.token_hex(16), secrets.token_hex(32)
    run = artifact_root.resolve() / run_id
    input_dir, output_dir = run / 'input', run / 'output'
    input_dir.mkdir(parents=True, exist_ok=False)
    output_dir.mkdir()
    (input_dir / 'candidate.ps1').write_bytes(FIXTURE)
    (input_dir / 'bootstrap.ps1').write_text(BOOTSTRAP, encoding='utf-8')
    (input_dir / 'plan.json').write_text(json.dumps(dict(run_id=run_id, nonce=nonce)), encoding='utf-8')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in input_dir.iterdir()}
    config = run / 'proof.wsb'
    config.write_text(build_config(input_dir, output_dir), encoding='utf-8')
    report.update(run_id=run_id, artifact_dir=str(run), input_sha256=hashes)
    process = None
    try:
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        process = subprocess.Popen([executable, str(config)], startupinfo=startup,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + timeout
        result_path = output_dir / 'result.json'
        while not result_path.exists():
            if process.poll() not in (None, 0):
                raise RuntimeError(f'Windows Sandbox launcher failed (exit {process.returncode})')
            if time.monotonic() >= deadline:
                raise TimeoutError('Windows Sandbox timed out without guest evidence')
            time.sleep(0.25)
        if {p.name for p in output_dir.iterdir()} != {'result.json'}:
            raise ValueError('unexpected sandbox output artifacts')
        data = _read_result(result_path)
        evidence = validate_result(data, run_id=run_id, nonce=nonce)
        if {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in input_dir.iterdir()} != hashes:
            raise ValueError('host input bundle changed')
        report.update(passed=True, os_sandbox=True, evidence=evidence,
                      result_sha256=hashlib.sha256(data).hexdigest())
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        report['reason'] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
    return report
