"""Industrial integration evidence. This audit never promotes a release."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET

from nova_release_gates import GateDefinition, GateRunner
from nova_runtime.agent_report import StructuredAgentReport
from nova_platform_coverage import classify_platform_skips

REQUIRED_PHASES = (
    'server_regression', 'runtime_contracts', 'memory_and_conversation',
    'release_rollback', 'unit_suite', 'browser_proof', 'rollback_proof',
    'sandboxed_terminal', 'behavioral_baseline', 'memory_identity_restart',
    'filesystem_symlink',
)
SUITES = {
    'server_regression': ('tests/test_nova_enhanced_server.py', 'tests/test_nova_llm_synthesizer.py'),
    'runtime_contracts': tuple('tests/' + name for name in (
        'test_nova_runtime_contracts.py', 'test_nova_runtime_permissions.py',
        'test_nova_runtime_ledger.py', 'test_nova_runtime_scheduler.py',
        'test_nova_runtime_memory.py', 'test_nova_runtime_agent_report.py',
        'test_nova_runtime_eval_bank.py', 'test_nova_runtime_end_to_end.py',
        'test_nova_runtime_verification_playwright.py', 'test_nova_industrial_gate.py')),
    'memory_and_conversation': ('tests/test_nova_memory_v2.py', 'tests/test_nova_conversation_intelligence.py', 'tests/test_nova_conversation_eval.py'),
    'release_rollback': ('tests/test_nova_release_worktree.py', 'tests/test_nova_release_lock.py'),
    'unit_suite': ('tests',),
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(data) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def source_manifest(root: Path) -> dict:
    """Identify executable source and inputs without copying private content into reports."""
    root = Path(root).resolve()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(root), *args], timeout=30)
    commit = git('rev-parse', 'HEAD').decode().strip()
    paths = git('ls-files', '-z', '--cached', '--others', '--exclude-standard').decode('utf-8').split('\0')
    files = {}
    prefixes = {'src', 'tests', 'tools', 'scripts', 'assets', 'config', '.github', 'autonomous_skills'}
    for relative in sorted(set(paths)):
        if not relative:
            continue
        parts = Path(relative).parts
        if len(parts) > 1 and parts[0] not in prefixes and not relative.startswith('data/evals/'):
            continue
        if '__pycache__' in parts or Path(relative).suffix in {'.pyc', '.log'}:
            continue
        if len(parts) == 1 and Path(relative).suffix not in {'.py', '.html', '.js', '.mjs', '.json', '.toml', '.ini', '.ps1', '.bat', '.sh', '.txt', '.lock', '.webmanifest'} and relative != '.nova_llm_config':
            continue
        path = root / relative
        if not path.exists():
            files[relative] = {'deleted': True}
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError(f'Source link is not an ordinary in-workspace file: {relative}')
        if not path.is_file():
            raise ValueError(f'Source entry is not a regular file: {relative}')
        data = path.read_bytes()
        files[relative] = {'sha256': _digest(data), 'bytes': len(data)}
    return {
        'commit': commit,
        'branch': git('branch', '--show-current').decode().strip(),
        'dirty': bool(git('status', '--porcelain', '--untracked-files=normal').strip()),
        'sha256': _digest(_json_bytes(files)), 'files': files,
        'scope': 'root runtime files; src/tests/tools/scripts/assets/config/.github/autonomous_skills; data/evals; excludes runtime memories, models and generated reports',
    }


def read_junit(path: Path) -> dict:
    try:
        tree = ET.parse(path)
        cases = list(tree.iter('testcase'))
        if not cases:
            raise ValueError('JUnit contains no executed test cases')
        counts = {'total': len(cases), 'passed': 0, 'failed': 0, 'errors': 0, 'skipped': 0}
        for case in cases:
            key = 'errors' if case.find('error') is not None else 'failed' if case.find('failure') is not None else 'skipped' if case.find('skipped') is not None else 'passed'
            counts[key] += 1
        return counts
    except (ET.ParseError, OSError) as error:
        raise ValueError('Missing or malformed JUnit evidence') from error


def summarize_gate(phases: list[dict], *, source_unchanged: bool, dirty: bool) -> dict:
    by_name = {}
    blockers = []
    for phase in phases:
        name = phase['name']
        if name in by_name:
            blockers.append(f'duplicate_phase:{name}')
        by_name[name] = phase
        if phase.get('passed') is not True:
            blockers.append(f'phase_failed:{name}')
    missing = [name for name in REQUIRED_PHASES if name not in by_name]
    blockers.extend(f'missing_evidence:{name}' for name in missing)
    if not source_unchanged:
        blockers.append('source_changed_during_run')
    if dirty:
        blockers.append('workspace_is_not_a_clean_release_commit')
    return {'passed': not blockers, 'promotion_allowed': False,
            'missing_required_phases': missing, 'blockers': blockers,
            'promotion_policy': 'Audit only. Promotion remains the responsibility of the release lock.'}


def resolve_symlink_coverage(phases):
    proof = next((p for p in phases if p['name'] == 'filesystem_symlink'), {})
    if proof.get('passed') is not True:
        return
    for phase in phases:
        coverage = phase.get('skip_applicability', {})
        unresolved = coverage.get('unresolved', [])
        covered = [row for row in unresolved if row['test'] == 'tests.test_nova_release_policy::test_workspace_scan_records_directory_symlink_without_following'
                   and row['reason'].startswith('directory symlinks are not supported for this test user:') and '1314' in row['reason']]
        if covered:
            coverage['covered_in_windows_sandbox'] = covered
            coverage['unresolved'] = [row for row in unresolved if row not in covered]
            counts = phase['tests']
            phase['passed'] = phase.get('process_passed') is True and counts['passed'] > 0 and not counts['failed'] and not counts['errors'] and not coverage['unresolved']


def archive_proof_evidence(source: Path, target: Path) -> None:
    """Keep partial evidence too, without following links out of the proof output."""
    proof = source / 'proof.json'
    if proof.is_file() and not proof.is_symlink():
        shutil.copyfile(proof, target / 'proof.json')
    artifacts = source / 'proof-artifacts'
    if artifacts.is_dir():
        if artifacts.is_symlink() or not artifacts.resolve().is_relative_to(source.resolve()):
            raise ValueError('Linked proof root rejected')
        for path in artifacts.rglob('*'):
            if path.is_symlink() or not path.resolve().is_relative_to(artifacts.resolve()):
                raise ValueError('Linked proof artifact rejected')
            destination = target / 'proof-artifacts' / path.relative_to(artifacts)
            if path.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)


def read_proof_verdict(path: Path, *, process_passed: bool) -> dict:
    try:
        if path.is_symlink():
            raise ValueError('Linked proof report rejected')
        raw = path.read_bytes()
        payload = json.loads(raw.decode('utf-8'))
        if not isinstance(payload, dict):
            raise ValueError('Proof report must be an object')
        return {'passed': process_passed and payload.get('passed') is True,
                'evidence': payload, 'evidence_sha256': _digest(raw)}
    except (OSError, ValueError) as error:
        return {'passed': False, 'reason': str(error)}


def run_gate(root: Path, output: Path, *, scope: str = 'full', timeout_seconds: int = 600) -> dict:
    if scope not in {'full', 'focused'} or timeout_seconds < 1:
        raise ValueError('Invalid scope or timeout')
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError('Use a fresh evidence directory for every run')
    output.mkdir(parents=True)
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
    phases = []
    try:
        before = source_manifest(root)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        before = {'commit': None, 'sha256': None, 'dirty': True, 'files': {}, 'error': str(error)}
        phases.append({'name': 'source_scan', 'passed': False, 'reason': str(error)})
    _write(output / 'source-before.json', before)
    env = dict(os.environ)
    env['NOVA_AGENT_ALLOW_SHELL'] = 'false'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONPATH'] = str(root / 'src')
    # Keep report outputs outside the candidate while subprocesses run.
    try:
        if before.get('error'):
            raise ValueError('Initial source identity could not be established')
        with tempfile.TemporaryDirectory(prefix='nova-industrial-') as temporary:
            evidence = Path(temporary)
            runner = GateRunner(root, evidence, base_environment=env)
            try:
                for name, tests in SUITES.items():
                    if name == 'unit_suite' and scope == 'focused':
                        continue
                    print(f'Industrial Gate: {name}', flush=True)
                    junit = evidence / (name + '.xml')
                    command = (sys.executable, '-m', 'pytest', *tests, '-q', '--disable-warnings', '--tb=short', '-o', 'faulthandler_timeout=60', '--junitxml=' + str(junit))
                    result = runner.run(GateDefinition(name=name, argv=command, timeout_seconds=timeout_seconds))
                    record = asdict(result)
                    record['evidence_kind'] = 'unit_tests_on_host'
                    (output / (name + '.stdout.txt')).write_text(result.stdout_tail, encoding='utf-8')
                    (output / (name + '.stderr.txt')).write_text(result.stderr_tail, encoding='utf-8')
                    try:
                        record['tests'] = read_junit(junit)
                        record['process_passed'] = result.passed
                        record['skip_applicability'] = classify_platform_skips(ET.parse(junit).iter('testcase'), target_platform='windows', host_platform=sys.platform)
                        record['passed'] = result.passed and record['tests']['passed'] > 0 and not any(record['tests'][key] for key in ('failed', 'errors')) and not record['skip_applicability']['unresolved']
                        if junit.is_symlink():
                            raise ValueError('JUnit link is not accepted')
                        shutil.copyfile(junit, output / (name + '.xml'))
                        record['junit_sha256'] = _digest(junit.read_bytes())
                    except (OSError, ValueError) as error:
                        record['passed'] = False
                        record['evidence_error'] = str(error)
                    phases.append(record)
                    _write(output / 'phases.json', phases)
                # A real browser and an intentional verification failure exercise both paths.
                print('Industrial Gate: real browser and rollback proof', flush=True)
                proof_path = evidence / 'proof.json'
                result = runner.run(GateDefinition(
                    name='proof_job', argv=(sys.executable, 'tools/nova_industrial_proof.py', '--output', str(proof_path)),
                    timeout_seconds=timeout_seconds))
                (output / 'proof.stdout.txt').write_text(result.stdout_tail, encoding='utf-8')
                (output / 'proof.stderr.txt').write_text(result.stderr_tail, encoding='utf-8')
                _write(output / 'proof-process.json', asdict(result))
                try:
                    proof = json.loads(proof_path.read_text(encoding='utf-8'))
                    if not result.passed:
                        raise ValueError('Proof process failed')
                    for name in ('browser_proof', 'rollback_proof'):
                        phases.append({'name': name, 'passed': proof[name]['passed'] is True,
                                       'evidence': proof[name], 'evidence_kind': 'real_playwright_fixture'})
                except (OSError, ValueError, KeyError, TypeError) as error:
                    phases.append({'name': 'browser_proof', 'passed': False, 'reason': str(error)})
                for name, script in (
                    ('sandboxed_terminal', 'nova_sandbox_proof.py'),
                    ('behavioral_baseline', 'nova_behavior_proof.py'),
                    ('memory_identity_restart', 'nova_identity_proof.py'),
                    ('filesystem_symlink', 'nova_symlink_sandbox_proof.py'),
                ):
                    print('Industrial Gate: ' + name, flush=True)
                    phase_dir = evidence / name
                    phase_dir.mkdir()
                    proof_path = phase_dir / 'report.json'
                    result = runner.run(GateDefinition(
                        name=name, argv=(sys.executable, 'tools/' + script, '--output', str(proof_path)),
                        timeout_seconds=timeout_seconds))
                    record = {'name': name, 'command': list(result.command) if hasattr(result, 'command') else [sys.executable, 'tools/' + script],
                              'archived_evidence_directory': name,
                              **read_proof_verdict(proof_path, process_passed=result.passed)}
                    phases.append(record)
                    _write(output / (name + '-process.json'), asdict(result))
                    # Preserve partial evidence even for an unsuccessful proof process.
                    shutil.copytree(phase_dir, output / name, symlinks=True)
                    _write(output / 'phases.json', phases)
                resolve_symlink_coverage(phases)
                _write(output / 'phases.json', phases)
            finally:
                # GateRunner pins its evidence directory; release the pin before temp cleanup.
                try:
                    archive_proof_evidence(evidence, output)
                finally:
                    runner._safe_report_directory.close()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        phases.append({'name': 'audit_error', 'passed': False, 'reason': str(error)})
    try:
        after = source_manifest(root)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        after = {'commit': None, 'sha256': None, 'dirty': True, 'error': str(error)}
        phases.append({'name': 'final_source_scan', 'passed': False, 'reason': str(error)})
    _write(output / 'source-after.json', after)
    source_unchanged = before['sha256'] is not None and before['sha256'] == after['sha256'] and before['commit'] == after['commit']
    verdict = summarize_gate(phases, source_unchanged=source_unchanged, dirty=before['dirty'] or after['dirty'])
    report = StructuredAgentReport(
        goal='Verify Nova Industrial Gate v1 against an identified source state.',
        plan=['Record source hashes', 'Run required suites', 'Run real browser and rollback fixtures', 'Require complete release evidence'],
        tools_used=['pytest', 'playwright', 'git'], files_changed=[],
        tests_executed=[subprocess.list2cmdline(phase['command']) if phase.get('command') else phase['name'] for phase in phases],
        browser_evidence={p['name']: p for p in phases if p['name'] in {'browser_proof', 'rollback_proof'}},
        failures_and_retries=[p for p in phases if not p.get('passed')],
        final_verification=verdict, unresolved_blockers=verdict['blockers'],
        rollback_information={'promotion_attempted': False, 'source_unchanged_observed': source_unchanged, 'source_change_attribution': 'unknown' if not source_unchanged else 'none_observed'},
    ).to_dict()
    report.update(schema_version='nova-industrial-gate-1', run_id=run_id, scope=scope,
                  target_platform='windows',
                  source_commit=before['commit'], source_sha256=before['sha256'],
                  phases=phases, runtime={'python': sys.version, 'executable': sys.executable},
                  limitations={'promotion': 'Audit only; each proof records its own execution scope and limitations.'})
    _write(output / 'report.json', report)
    return report
