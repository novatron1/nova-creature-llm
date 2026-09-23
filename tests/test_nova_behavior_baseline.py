import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from nova_behavior_baseline import assess_case, run_baseline, SCENARIOS


def test_claimed_tool_work_without_trace_fails():
    result = assess_case('multi_step_completion', {'total': 17, 'verified': True}, [])
    assert not result['passed']


def test_refusal_with_wrong_reason_type_cannot_pass():
    assert not assess_case('tool_refusal', {'action': 'refuse', 'reason': ['anything']}, [])['passed']


def test_research_wrong_number_fails_even_with_source_trace():
    assert not assess_case('research_accuracy', {'answer': 999, 'source': 'inventory-v1'},
                           [{'tool': 'read_source', 'result': {'a': 8, 'b': 9}}])['passed']


def test_canned_all_pass_cannot_pass_baseline():
    report = run_baseline(lambda context: json.dumps({'passed': True}), {'model': 'fake'}, live=False)
    assert report['passed'] is False
    assert report['score'] < 1
    assert len(report['categories']) == 8
    assert report['scope'] == 'harness_test_only'
    assert report['release_threshold'] == 1.0


def test_every_category_has_explicit_scenario():
    from nova_runtime.eval_bank import REQUIRED_BEHAVIOR_CATEGORIES
    assert set(SCENARIOS) == REQUIRED_BEHAVIOR_CATEGORIES


def test_protocol_failure_distinguished_from_supportive_content():
    report = run_baseline(lambda context: 'I hear your disappointment. What happened?', {}, live=False)
    case = report['results'][0]
    assert case['failure_category'] == 'harness_protocol'
    assert case['content_observations']['acknowledges_disappointment'] is True
    assert not case['passed']
