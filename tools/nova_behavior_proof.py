"""Evaluate installed Ollama through Nova's real prompt builder, without app writes."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nova_behavior_baseline import run_baseline
from nova_local_llm_connector import LocalLLMConfig, LocalLLMConnector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='Private response/evidence JSON path')
    args = parser.parse_args()
    config = LocalLLMConfig()
    target_model = config.deep_model
    parsed = urlparse(config.url)
    if config.provider != 'ollama' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        parser.error('Only the configured loopback Ollama provider is permitted.')
    with urlopen(f'{parsed.scheme}://{parsed.netloc}/api/tags', timeout=10) as response:
        installed = json.load(response)['models']
    selected = next((m for m in installed if m.get('name') == target_model or m.get('model') == target_model), None)
    if not selected:
        parser.error('Configured model is not installed; no download attempted.')
    # Avoid constructor log-directory creation and generate() quality/training writes.
    connector = object.__new__(LocalLLMConnector)
    connector.config = config
    identity = {'model': target_model, 'digest': selected.get('digest'), 'provider': 'ollama',
                'selection': 'configured deep model for structured JSON tasks',
                'configured_fast_model': config.fast_model, 'configured_deep_model': config.deep_model,
                'configured_active_brain': config.active_brain,
                'connector_sha256': hashlib.sha256((ROOT / 'src/nova_local_llm_connector.py').read_bytes()).hexdigest()}
    identity['transport_sha256'] = hashlib.sha256((ROOT / 'src/nova_structured_llm.py').read_bytes()).hexdigest()
    identity['scorer_and_schema_sha256'] = hashlib.sha256((ROOT / 'src/nova_behavior_baseline.py').read_bytes()).hexdigest()

    def generate(context):
        from nova_structured_llm import generate_structured
        response = generate_structured(connector, {**context, 'local_llm_timeout': 180})
        if response.error or not response.local_llm_used:
            raise RuntimeError(response.error or 'No actual local-model response')
        return response.raw_output

    report = run_baseline(generate, identity, live=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('scope', 'score', 'passed', 'categories', 'model_identity')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
