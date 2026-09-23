"""Exercise known local fixtures with real Playwright; never claim OS isolation."""
from pathlib import Path
import argparse
import hashlib
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nova_runtime.orchestrator import run_proof_job


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    artifact_root = args.output.parent / 'proof-artifacts'
    artifact_root.mkdir()
    results = {}
    for label, expected in [('success', 'hello, nova'), ('failure', 'intentional verification failure')]:
        project = artifact_root / (label + '-source')
        project.mkdir()
        original = b'def answer():\r\n    return "hello"\r\n'
        (project / 'app.py').write_bytes(original)
        (project / 'test_app.py').write_text('from app import answer\n\ndef test_answer():\n    assert answer() == ' + repr(expected) + '\n', encoding='utf-8')
        result = run_proof_job(project_root=project, output_dir=artifact_root / (label + '-work'))
        payload = result.to_dict()
        (artifact_root / (label + '-report.json')).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        results[label] = result
    success, failure = results['success'], results['failure']
    browser = success.proof_artifacts['verification']
    screenshot = Path(browser.get('screenshot_path') or '')
    screenshot_valid = screenshot.is_file() and hashlib.sha256(screenshot.read_bytes()).hexdigest() == browser.get('screenshot_hash')
    restored = (Path(failure.workspace_root) / 'app.py').read_bytes() == original
    no_failure_memory = not (Path(failure.workspace_root) / 'provenance_memory.jsonl').exists()
    artifacts = {str(p.relative_to(args.output.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in artifact_root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.pytest_cache' not in p.parts}
    payload = {
        'browser_proof': {
            'passed': bool(success.report.final_verification['passed'] and success.run.state.value == 'completed' and browser['passed'] and screenshot_valid and browser['assertions']),
            'backend': 'real_playwright', 'screenshot_verified': screenshot_valid,
            'screenshot_sha256': browser['screenshot_hash'], 'dom_sha256': browser['dom_hash'],
            'report': 'proof-artifacts/success-report.json',
        },
        'rollback_proof': {
            'passed': bool(not failure.report.final_verification['passed'] and failure.run.state.value == 'rolled_back' and restored and no_failure_memory),
            'exact_original_bytes_restored': restored, 'no_failed_success_memory': no_failure_memory,
            'report': 'proof-artifacts/failure-report.json',
        },
        'isolation': {'os_sandbox': False, 'method': 'copied_workspace'},
        'artifacts': artifacts,
    }
    args.output.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in payload.items() if key != 'artifacts'}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
