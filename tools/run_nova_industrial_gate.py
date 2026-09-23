"""Run the fail-closed Nova Industrial Gate evidence audit."""
from pathlib import Path
import argparse
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nova_industrial_gate import run_gate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scope', choices=['full', 'focused'], default='full')
    parser.add_argument('--timeout', type=int, default=600, help='Deadline per subprocess in seconds')
    args = parser.parse_args()
    try:
        report = run_gate(args.root, args.output, scope=args.scope, timeout_seconds=args.timeout)
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({'passed': False, 'error': str(error)}))
        return 2
    verdict = report['final_verification']
    print(json.dumps({'run_id': report['run_id'], 'report': str(args.output / 'report.json'), **verdict}, indent=2))
    return 0 if verdict['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
