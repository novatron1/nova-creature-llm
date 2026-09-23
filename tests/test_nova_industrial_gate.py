from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nova_industrial_gate import read_junit, summarize_gate, source_manifest


@pytest.mark.parametrize('proof_passed,expected', [(False, False), (True, True)])
def test_symlink_skip_needs_actual_successful_guest_proof(proof_passed, expected):
    from nova_industrial_gate import resolve_symlink_coverage
    phase = {'name': 'unit_suite', 'passed': False, 'process_passed': True,
             'tests': {'passed': 20, 'failed': 0, 'errors': 0, 'skipped': 1},
             'skip_applicability': {'unresolved': [{'test': 'tests.test_nova_release_policy::test_workspace_scan_records_directory_symlink_without_following', 'reason': 'directory symlinks are not supported for this test user: [WinError 1314]'}]}}
    resolve_symlink_coverage([phase, {'name': 'filesystem_symlink', 'passed': proof_passed}])
    assert phase['passed'] is expected
    assert phase['tests']['skipped'] == 1


@pytest.mark.parametrize('exit_passed,payload,expected', [
    (True, {'passed': True}, True),
    (False, {'passed': True}, False),
    (True, {'passed': 'true'}, False),
    (True, {}, False),
])
def test_external_proof_requires_successful_process_and_explicit_verdict(tmp_path, exit_passed, payload, expected):
    import json
    from nova_industrial_gate import read_proof_verdict
    path = tmp_path / 'proof.json'
    path.write_text(json.dumps(payload))
    assert read_proof_verdict(path, process_passed=exit_passed)['passed'] is expected


def test_external_proof_missing_evidence_fails_closed(tmp_path):
    from nova_industrial_gate import read_proof_verdict
    assert read_proof_verdict(tmp_path / 'missing.json', process_passed=True)['passed'] is False


def test_junit_counts_failures_errors_and_skips(tmp_path):
    report = tmp_path / 'tests.xml'
    report.write_text('<testsuites><testsuite><testcase/><testcase><failure/></testcase><testcase><error/></testcase><testcase><skipped/></testcase></testsuite></testsuites>')
    assert read_junit(report) == {'total': 4, 'passed': 1, 'failed': 1, 'errors': 1, 'skipped': 1}


@pytest.mark.parametrize('text', ['<testsuites/>', '<broken', '<testsuites><testsuite tests="1"/></testsuites>'])
def test_empty_or_malformed_junit_cannot_pass(tmp_path, text):
    report = tmp_path / 'tests.xml'
    report.write_text(text)
    with pytest.raises(ValueError):
        read_junit(report)


def test_missing_required_phases_block_even_when_present_phases_pass():
    report = summarize_gate([{'name': 'server_regression', 'passed': True}], source_unchanged=True, dirty=False)
    assert report['passed'] is False
    assert 'sandboxed_terminal' in report['missing_required_phases']
    assert 'behavioral_baseline' in report['missing_required_phases']
    assert report['promotion_allowed'] is False


def test_modified_source_blocks_gate():
    report = summarize_gate([], source_unchanged=False, dirty=False)
    assert 'source_changed_during_run' in report['blockers']


def test_duplicate_phase_cannot_overwrite_failure():
    report = summarize_gate([{'name': 'server_regression', 'passed': False}, {'name': 'server_regression', 'passed': True}], source_unchanged=True, dirty=False)
    assert 'duplicate_phase:server_regression' in report['blockers']


def test_source_manifest_identifies_dirty_code_and_ignores_generated_reports(tmp_path):
    import subprocess
    def git(*args):
        return subprocess.run(['git', '-C', str(tmp_path), *args], check=True, capture_output=True)
    git('init')
    (tmp_path / 'app.py').write_text('print(1)')
    git('add', 'app.py')
    git('-c', 'user.name=Gate Test', '-c', 'user.email=gate@example.invalid', 'commit', '-m', 'fixture')
    first = source_manifest(tmp_path)
    (tmp_path / 'reports').mkdir()
    (tmp_path / 'reports' / 'output.json').write_text('{}')
    assert source_manifest(tmp_path)['sha256'] == first['sha256']
    (tmp_path / 'app.py').write_text('print(2)')
    second = source_manifest(tmp_path)
    assert second['sha256'] != first['sha256']
    assert second['commit'] == first['commit']
    assert second['dirty'] is True


def test_release_gate_requires_industrial_evidence(tmp_path):
    from nova_release_gates import default_gate_definitions, _sanitized_environment
    gates = {gate.name: gate for gate in default_gate_definitions(tmp_path / 'candidate', tmp_path / 'reports')}
    assert 'industrial_gate' in gates
    assert gates['industrial_gate'].required is True
    assert '--scope' not in gates['industrial_gate'].argv  # Full audit is mandatory.
    assert _sanitized_environment(tmp_path, {'NOVA_AGENT_ALLOW_SHELL': 'true'})['NOVA_AGENT_ALLOW_SHELL'] == 'false'


def test_runner_failure_still_writes_blocked_report(tmp_path, monkeypatch):
    import json
    import nova_industrial_gate as gate
    monkeypatch.setattr(gate, 'source_manifest', lambda root: {'commit': 'abc', 'sha256': 'same', 'dirty': False, 'files': {}})
    class BrokenRunner:
        def __init__(self, *args, **kwargs):
            raise PermissionError('cannot acquire containment')
    monkeypatch.setattr(gate, 'GateRunner', BrokenRunner)
    output = tmp_path / 'evidence'
    report = gate.run_gate(tmp_path, output, scope='focused')
    assert report['final_verification']['passed'] is False
    assert (output / 'report.json').is_file()
    assert any(p['name'] == 'audit_error' for p in report['phases'])


def test_failed_proof_retains_partial_artifacts(tmp_path):
    import nova_industrial_gate as gate
    source = tmp_path / 'temp'
    target = tmp_path / 'evidence'
    source.mkdir()
    target.mkdir()
    artifacts = source / 'proof-artifacts'
    artifacts.mkdir()
    (artifacts / 'success-report.json').write_text('{"passed":true}')
    gate.archive_proof_evidence(source, target)
    assert (target / 'proof-artifacts' / 'success-report.json').read_text() == '{"passed":true}'
