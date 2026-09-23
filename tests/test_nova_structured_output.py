from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nova_local_llm_connector import LocalLLMConnector


def test_structured_prompt_keeps_request_last_and_tool_results_explicit():
    connector = object.__new__(LocalLLMConnector)
    prompt = connector._build_prompt({'response_format': 'json', 'user_message': 'Read the file then summarize.', 'tool_results': [{'tool': 'read_file', 'result': 'actual contents'}]})
    assert 'actual contents' in prompt
    assert prompt.endswith('JSON response:')
    assert 'WHEN DID THEY WRITE THE BIBLE' not in prompt


def test_structured_generation_uses_deep_route_and_json_transport(monkeypatch):
    from types import SimpleNamespace
    connector = object.__new__(LocalLLMConnector)
    connector.config = SimpleNamespace(use_local_llm=True, deep_model='deep-fixture', model='fast-fixture', provider='ollama', log_prompts=False, timeout=60)
    monkeypatch.setattr(connector, '_call_lora_runtime', lambda *a, **k: None)
    monkeypatch.setattr(connector, '_adapter_only_requested', lambda *a: False)
    monkeypatch.setattr(connector, '_record_managed_model_quality', lambda *a: None)
    import nova_structured_llm
    calls = []
    monkeypatch.setattr(nova_structured_llm, 'generate_structured', lambda client, context: calls.append((client, context)) or 'response')
    assert connector.generate({'response_format': 'json', 'user_message': 'Return a JSON object.'}) == 'response'
    assert calls[0][0] is connector
    assert calls[0][1]['response_format'] == 'json'
    from contextlib import nullcontext
    calls.clear()
    monkeypatch.setattr(connector, '_ollama_residency_context', lambda *a: nullcontext({'allowed': False}))
    monkeypatch.setattr(connector, '_residency_blocked_response', lambda *a: 'blocked')
    assert connector.generate({'response_format': 'json', 'adaptive_model_memory': True}) == 'blocked'
    assert calls == []


def test_native_chat_keeps_tool_observation_after_assistant_request():
    from nova_structured_llm import build_messages
    result = build_messages({'user_message': 'Inspect logs', 'tool_results': [{'tool': 'read_logs', 'arguments': {'tool': 'read_logs'}, 'result': {'error': 'port unavailable'}}]})
    assert [m['role'] for m in result] == ['system', 'user', 'assistant', 'tool']
    assert 'port unavailable' in result[-1]['content']
    assert 'port unavailable' not in result[0]['content']


def test_completion_without_required_tool_evidence_fails_closed(monkeypatch):
    import io
    from types import SimpleNamespace
    import nova_structured_llm as structured
    connector = SimpleNamespace(config=SimpleNamespace(deep_model='fixture', url='http://127.0.0.1:11434/api/generate', context_window=512, ollama_keep_alive='1m', timeout=5))
    calls = []
    def respond(request, **kwargs):
        calls.append(request)
        return io.StringIO('{"message":{"content":"{\\"verified\\":true}"}}')
    monkeypatch.setattr(structured, 'urlopen', respond)
    response = structured.generate_structured(connector, {'user_message': 'Verify output', 'required_tool_evidence': ['verify_output']})
    assert not response.local_llm_used
    assert 'missing required tool evidence' in response.error
    assert len(calls) == 2


def test_json_tool_request_is_not_mistaken_for_unverified_completion():
    from nova_structured_llm import requested_calls
    calls = requested_calls({'content': '{"tool":"read_input"}'}, {'available_tools': [{'name': 'read_input'}]})
    assert calls == [{'function': {'name': 'read_input', 'arguments': {}}}]
    assert not requested_calls({'content': '{"tool":"unknown"}'}, {'available_tools': [{'name': 'read_input'}]})
