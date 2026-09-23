"""Verify identity through the actual brain route in separate fresh processes."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def worker(phase, output):
    import nova_enhanced_server as server
    rows = []

    def check(text, owner, expected, **options):
        response, trace = server._run_nova_chat_turn(text, {'user_id': owner, 'conversation_id': phase + '-' + owner, **options})
        rows.append({'text': text, 'owner': owner, 'expected': expected,
                     'actual': response, 'source': trace.get('source'),
                     'passed': response == expected and trace.get('source') == 'owned_identity_memory'})

    if phase == 'write':
        check('My name is Ray; your name is Nova', 'alice', 'Nice to meet you, Ray. My name is Nova.')
        check('Rename yourself to Luna', 'alice', 'You can call me Luna.')
        check('My name is Sam', 'bob', 'Nice to meet you, Sam.')
    else:
        check('What is my name?', 'alice', 'Your name is Ray.')
        check('What is your name?', 'alice', 'My name is Luna.')
        check('What is my name?', 'bob', 'Your name is Sam.')
        check('What is your name?', 'bob', 'My name is Nova.')
        check('What is my name?', 'unknown', "I don't have your name saved yet.")
        check('Your name is Evil', 'alice', 'My name is Luna. To change it, explicitly ask me to rename myself.')
        check('My name is Nova', 'alice', 'Nice to meet you, Nova.')
        check('What is your name?', 'alice', 'My name is Luna.')
        check('Rename yourself to Evil', 'alice', 'Identity memory updates are disabled for this turn.', private_mode=True)
        check('What is my name?', 'alice', 'Identity memory access is disabled for this turn.', nova_gateway=True)
        check('What is your name?', 'alice', 'My name is Luna.')
    output.write_text(json.dumps({'pid': os.getpid(), 'phase': phase, 'checks': rows}), encoding='utf-8')
    return 0 if all(row['passed'] for row in rows) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=['write', 'restart'])
    args = parser.parse_args()
    if args.worker:
        sys.path.insert(0, str(Path.cwd()))
        return worker(args.worker, args.output)
    root = Path(__file__).resolve().parents[1]
    report = {'schema_version': 1, 'passed': False, 'runtime': 'nova_enhanced_server._run_nova_chat_turn', 'processes': []}
    try:
        with tempfile.TemporaryDirectory(prefix='nova-identity-proof-') as folder:
            isolated = Path(folder)
            for source in [*root.glob('*.py'), *root.glob('*.html')]:
                shutil.copy2(source, isolated / source.name)
            shutil.copytree(root / 'src', isolated / 'src', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            env = {k: v for k, v in os.environ.items() if not k.startswith('NOVA_') and k != 'PYTHONPATH'}
            env.update(NOVA_IDENTITY_DATABASE=str(isolated / 'data' / 'identity.db'),
                       NOVA_SUPPRESS_RUNTIME_LOGS='true', NOVA_SUPPRESS_CONVERSATION_TRAINING='true',
                       PYTHONIOENCODING='utf-8')
            for phase in ('write', 'restart'):
                result_path = isolated / (phase + '.json')
                result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', phase, '--output', str(result_path)], cwd=isolated, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
                entry = json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {'phase': phase, 'checks': []}
                entry.update(exit_code=result.returncode, stderr_tail=result.stderr[-2000:])
                report['processes'].append(entry)
            report['passed'] = (all(p['exit_code'] == 0 and p['checks'] and all(c['passed'] for c in p['checks']) for p in report['processes']) and len({p.get('pid') for p in report['processes']}) == 2)
    except Exception as error:
        report['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'output': str(args.output)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
