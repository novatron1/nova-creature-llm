from pathlib import Path
from types import SimpleNamespace
import contextlib
from queue import Queue
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import nova_local_llm_connector as llm


class _FakeTensor:
    def __init__(self, data=None):
        self.data = data or [[1, 2, 3]]

    def to(self, _device):
        return self

    def __getitem__(self, item):
        if isinstance(item, tuple):
            row, col = item
            row_data = self.data[row]
            if isinstance(col, slice):
                return row_data[col]
            return row_data[col]
        return self.data[item]

    @property
    def shape(self):
        return (len(self.data), len(self.data[0]))


class _FakeTokenizer:
    eos_token_id = 2
    pad_token_id = None
    last_messages = None

    @classmethod
    def from_pretrained(cls, path, **_kwargs):
        cls.loaded_from = path
        return cls()

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        type(self).last_messages = messages
        assert messages[-1]["role"] == "user"
        suffix = "\nNova:" if add_generation_prompt else ""
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else "test"
        return "SYSTEM: " + system + "\nUser: " + messages[-1]["content"] + suffix

    def __call__(self, prompt, return_tensors=None):
        assert "User:" in prompt
        return SimpleNamespace(input_ids=_FakeTensor([[1, 2, 3]]))

    def decode(self, tokens, skip_special_tokens=True):
        return "Yeah, this answer came from the trained LoRA path."


class _FakeBaseModel:
    @classmethod
    def from_pretrained(cls, model_name, **kwargs):
        cls.loaded_model_name = model_name
        cls.loaded_kwargs = kwargs
        return cls()


class _FakePeftModel:
    @classmethod
    def from_pretrained(cls, base_model, adapter_path):
        cls.loaded_adapter_path = adapter_path
        return cls()

    def eval(self):
        return self

    def generate(self, **kwargs):
        self.generated_kwargs = kwargs
        return _FakeTensor([[1, 2, 3, 4, 5]])


def test_lora_runtime_generates_with_hf_peft_stack_without_float32_qwen_expansion(
    tmp_path, monkeypatch
):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        float16="float16",
        float32="float32",
        no_grad=lambda: contextlib.nullcontext(),
    )
    fake_transformers = SimpleNamespace(
        AutoTokenizer=_FakeTokenizer,
        AutoModelForCausalLM=_FakeBaseModel,
    )
    fake_peft = SimpleNamespace(PeftModel=_FakePeftModel)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    import nova_lora_runtime

    runtime = nova_lora_runtime.NovaLoraRuntime(
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        adapter_path=str(adapter_dir),
        device="cpu",
    )
    response = runtime.generate("Talk naturally.", max_new_tokens=24)

    assert response.local_llm_used is True
    assert response.provider == "hf_peft_lora"
    assert response.model == "Qwen/Qwen2.5-1.5B-Instruct + LoRA"
    assert response.raw_output == "Yeah, this answer came from the trained LoRA path."
    assert _FakePeftModel.loaded_adapter_path == str(adapter_dir)
    assert _FakeBaseModel.loaded_kwargs["local_files_only"] is True
    assert _FakeBaseModel.loaded_kwargs["low_cpu_mem_usage"] is True
    assert _FakeBaseModel.loaded_kwargs["dtype"] == "auto"
    assert "torch_dtype" not in _FakeBaseModel.loaded_kwargs


def test_lora_runtime_chat_template_uses_nova_system_identity(tmp_path, monkeypatch):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        float16="float16",
        float32="float32",
        no_grad=lambda: contextlib.nullcontext(),
    )
    fake_transformers = SimpleNamespace(
        AutoTokenizer=_FakeTokenizer,
        AutoModelForCausalLM=_FakeBaseModel,
    )
    fake_peft = SimpleNamespace(PeftModel=_FakePeftModel)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "peft", fake_peft)

    import nova_lora_runtime

    _FakeTokenizer.last_messages = None
    runtime = nova_lora_runtime.NovaLoraRuntime(
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        adapter_path=str(adapter_dir),
        device="cpu",
    )
    runtime.generate("What is your name?", max_new_tokens=24)

    messages = _FakeTokenizer.last_messages
    assert messages[0]["role"] == "system"
    assert "Nova Creature" in messages[0]["content"]
    assert "Alibaba" not in messages[0]["content"]
    assert "Qwen" not in messages[0]["content"]


def test_lora_runtime_raw_mode_uses_only_user_message(tmp_path, monkeypatch):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    fake_torch = SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False),
        float16="float16", float32="float32", no_grad=lambda: contextlib.nullcontext(),
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(
        sys.modules, "transformers",
        SimpleNamespace(AutoTokenizer=_FakeTokenizer, AutoModelForCausalLM=_FakeBaseModel),
    )
    monkeypatch.setitem(sys.modules, "peft", SimpleNamespace(PeftModel=_FakePeftModel))

    import nova_lora_runtime

    _FakeTokenizer.last_messages = None
    runtime = nova_lora_runtime.NovaLoraRuntime(
        base_model="Qwen/Qwen2.5-1.5B-Instruct", adapter_path=str(adapter_dir), device="cpu",
    )
    runtime.generate("What is your name?", max_new_tokens=24, raw_mode=True)

    assert _FakeTokenizer.last_messages == [{"role": "user", "content": "What is your name?"}]


def test_dolphin_cpu_runtime_preserves_checkpoint_precision(tmp_path):
    import nova_lora_runtime

    runtime = nova_lora_runtime.NovaLoraRuntime(
        base_model="dphn/Dolphin3.0-Llama3.1-8B", adapter_path=str(tmp_path), device="cpu",
    )
    device, dtype = runtime._resolve_device_and_dtype(
        SimpleNamespace(float16="float16", float32="float32", cuda=SimpleNamespace(is_available=lambda: False))
    )

    assert device == "cpu"
    assert dtype == "auto"


def test_runtime_cache_releases_previous_adapter_when_switching(monkeypatch, tmp_path):
    import nova_lora_runtime

    monkeypatch.setattr(nova_lora_runtime, "_RUNTIME_CACHE", {})
    qwen = nova_lora_runtime.get_lora_runtime("Qwen/Qwen2.5-1.5B-Instruct", str(tmp_path / "qwen"))
    dolphin = nova_lora_runtime.get_lora_runtime("dphn/Dolphin3.0-Llama3.1-8B", str(tmp_path / "dolphin"))

    assert qwen is not dolphin
    assert list(nova_lora_runtime._RUNTIME_CACHE.values()) == [dolphin]


def test_runtime_cache_status_is_safe_and_unload_releases_idle_runtime(monkeypatch, tmp_path):
    import nova_lora_runtime

    adapter_path = tmp_path / "qwen-adapter"
    runtime = nova_lora_runtime.NovaLoraRuntime(
        "Qwen/Qwen2.5-1.5B-Instruct", str(adapter_path), device="cpu"
    )
    runtime.model = object()
    runtime.tokenizer = object()
    monkeypatch.setattr(nova_lora_runtime, "_RUNTIME_CACHE", {("qwen", "adapter", "cpu", False): runtime})
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)),
    )

    status = nova_lora_runtime.runtime_cache_status()
    result = nova_lora_runtime.unload_cached_lora_runtimes()

    assert status == [
        {
            "base_model": "Qwen/Qwen2.5-1.5B-Instruct",
            "adapter_name": "qwen-adapter",
            "device": "cpu",
            "loaded": True,
            "active_generations": 0,
            "busy": False,
            "unload_requested": False,
            "last_used_at": None,
        }
    ]
    assert result["ok"] is True
    assert result["unloaded"][0]["adapter_name"] == "qwen-adapter"
    assert nova_lora_runtime._RUNTIME_CACHE == {}


def test_runtime_unload_protects_active_generation(monkeypatch, tmp_path):
    import nova_lora_runtime

    runtime = nova_lora_runtime.NovaLoraRuntime("Qwen", str(tmp_path / "adapter"), device="cpu")
    runtime._active_generations = 1
    cache = {("qwen", "adapter", "cpu", False): runtime}
    monkeypatch.setattr(nova_lora_runtime, "_RUNTIME_CACHE", cache)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False, empty_cache=lambda: None)),
    )

    result = nova_lora_runtime.unload_cached_lora_runtimes()

    assert result["ok"] is False
    assert result["unloaded"] == []
    assert result["skipped"][0]["reason"] == "generation_in_progress_unload_queued"
    assert nova_lora_runtime._RUNTIME_CACHE == cache

    runtime._finish_activity()

    assert nova_lora_runtime._RUNTIME_CACHE == {}


def test_lora_runtime_streams_transformer_text_incrementally(tmp_path, monkeypatch):
    import nova_lora_runtime

    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    class FakeStoppingCriteria:
        pass

    class FakeStoppingCriteriaList(list):
        pass

    class FakeTextIteratorStreamer:
        _END = object()

        def __init__(self, tokenizer, **kwargs):
            self.queue = Queue()

        def on_finalized_text(self, text, stream_end=False):
            if text:
                self.queue.put(text)
            if stream_end:
                self.queue.put(self._END)

        def __iter__(self):
            return self

        def __next__(self):
            value = self.queue.get(timeout=1)
            if value is self._END:
                raise StopIteration
            return value

    class FakeStreamModel:
        def generate(self, **kwargs):
            kwargs["streamer"].on_finalized_text("Nova ")
            kwargs["streamer"].on_finalized_text("streams.", stream_end=True)

    tokenizer = _FakeTokenizer()
    runtime = nova_lora_runtime.NovaLoraRuntime(
        base_model="Qwen/Qwen2.5-1.5B-Instruct",
        adapter_path=str(adapter_dir),
        device="cpu",
    )
    runtime.tokenizer = tokenizer
    runtime.model = FakeStreamModel()
    fake_torch = SimpleNamespace(no_grad=lambda: contextlib.nullcontext())
    fake_transformers = SimpleNamespace(
        StoppingCriteria=FakeStoppingCriteria,
        StoppingCriteriaList=FakeStoppingCriteriaList,
        TextIteratorStreamer=FakeTextIteratorStreamer,
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    emitted = []

    response = runtime.generate_stream(
        "Talk naturally.",
        lambda delta: emitted.append(delta) or True,
        max_new_tokens=24,
    )

    assert response.local_llm_used is True
    assert response.raw_output == "Nova streams."
    assert emitted == ["Nova ", "streams."]


def test_connector_does_not_mix_ollama_after_partial_lora_stream(monkeypatch):
    def fake_lora_stream(prompt, on_delta, **kwargs):
        on_delta("Safe partial sentence.")
        return llm.LocalLLMResponse(
            local_llm_used=False,
            provider="hf_peft_lora",
            model="Qwen + LoRA",
            raw_output="Safe partial sentence.",
            error="generation_interrupted",
            fallback_used=True,
            fallback_reason="generation interrupted",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora_stream=fake_lora_stream),
    )
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "always",
            "NOVA_LOG_LOCAL_LLM_PROMPTS": False,
        }
    )
    connector = llm.LocalLLMConnector(config)

    def ollama_must_not_run(*args, **kwargs):
        raise AssertionError("A second provider must not continue an already-visible stream")

    monkeypatch.setattr(connector, "_call_ollama_stream", ollama_must_not_run)
    emitted = []

    response = connector.generate_stream(
        {"user_message": "Stream", "selected_route": "general_conversation"},
        lambda delta: emitted.append(delta) or True,
    )

    assert emitted == ["Safe partial sentence."]
    assert response.provider == "hf_peft_lora"
    assert response.local_llm_used is False


def test_lora_runtime_skips_dolphin_8b_on_cpu_by_default(monkeypatch, tmp_path):
    import nova_lora_runtime

    adapter_dir = tmp_path / "dolphin-adapter"
    adapter_dir.mkdir()
    monkeypatch.delenv("NOVA_LORA_ALLOW_DOLPHIN_CPU", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "dphn/Dolphin3.0-Llama3.1-8B",
        }
    )

    response = nova_lora_runtime.generate_with_lora(
        "Do you like music?",
        config=config,
        adapter_path=str(adapter_dir),
        base_model="dphn/Dolphin3.0-Llama3.1-8B",
    )

    assert response.local_llm_used is False
    assert response.fallback_used is True
    assert "no CUDA GPU" in response.fallback_reason


def test_lora_runtime_explicit_dolphin_cpu_consent_reaches_raw_runtime(monkeypatch, tmp_path):
    import nova_lora_runtime

    adapter_dir = tmp_path / "dolphin-adapter"
    adapter_dir.mkdir()
    monkeypatch.delenv("NOVA_LORA_ALLOW_DOLPHIN_CPU", raising=False)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)))
    captured = {}

    class FakeRuntime:
        def generate(self, prompt, **kwargs):
            captured.update(prompt=prompt, **kwargs)
            return llm.LocalLLMResponse(
                local_llm_used=True, provider="hf_peft_lora", model="Dolphin + LoRA", raw_output="Raw Dolphin answer.",
            )

    monkeypatch.setattr(nova_lora_runtime, "get_lora_runtime", lambda **kwargs: FakeRuntime())
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "dphn/Dolphin3.0-Llama3.1-8B",
        }
    )

    response = nova_lora_runtime.generate_with_lora(
        "Do you love me?", config=config, adapter_path=str(adapter_dir),
        base_model="dphn/Dolphin3.0-Llama3.1-8B", allow_slow_cpu=True, raw_mode=True,
    )

    assert response.raw_output == "Raw Dolphin answer."
    assert captured["prompt"] == "Do you love me?"
    assert captured["raw_mode"] is True


def test_adapter_runtime_availability_reports_dolphin_cpu_guard(monkeypatch, tmp_path):
    import nova_lora_runtime

    adapter_dir = tmp_path / "dolphin-adapter"
    adapter_dir.mkdir()
    monkeypatch.delenv("NOVA_LORA_ALLOW_DOLPHIN_CPU", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False)),
    )

    unavailable = nova_lora_runtime.adapter_runtime_availability(
        "dphn/Dolphin3.0-Llama3.1-8B",
        str(adapter_dir),
    )
    available = nova_lora_runtime.adapter_runtime_availability(
        "Qwen/Qwen2.5-1.5B-Instruct",
        str(adapter_dir),
    )

    assert unavailable["runnable"] is False
    assert unavailable["state"] == "unavailable"
    assert unavailable["requires_cuda"] is True
    assert unavailable["slow_cpu_override_available"] is True
    assert "no CUDA GPU" in unavailable["reason"]
    assert available["runnable"] is True
    assert available["state"] == "available"


def test_local_connector_uses_lora_runtime_for_explicit_deep_lora_request(monkeypatch, tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")
    captured = {}

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        captured["prompt"] = prompt
        captured["config"] = config
        captured["kwargs"] = kwargs
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            prompt=prompt,
            raw_output="LoRA-backed answer.",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fail_ollama(*_args, **_kwargs):
        raise AssertionError("Ollama should not be called when LoRA runtime succeeds")

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fail_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
            "NOVA_LORA_AUTO_MODE": "dolphin_first",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: use Nova LoRA\nNova:",
            "user_message": "Use Nova LoRA for this answer.",
            "selected_route": "deepseek_direct",
        }
    )

    assert response.local_llm_used is True
    assert response.provider == "hf_peft_lora"
    assert response.raw_output == "LoRA-backed answer."
    assert captured["prompt"] == "User: use Nova LoRA\nNova:"


def test_local_connector_adapter_only_mode_does_not_fallback_to_ollama(monkeypatch, tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=False,
            provider="hf_peft_lora",
            model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            prompt=prompt,
            error="adapter test failure",
            fallback_used=True,
            fallback_reason="LoRA runtime error: adapter test failure",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fail_ollama(*_args, **_kwargs):
        raise AssertionError("Adapter-only mode must not hide a LoRA failure by falling back to Ollama")

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fail_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
            "NOVA_LORA_AUTO_MODE": "dolphin_first",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: answer through the adapter only\nNova:",
            "user_message": "answer through the adapter only",
            "selected_route": "deepseek_direct",
            "use_lora_runtime": True,
            "adapter_only_mode": True,
        }
    )

    assert response.local_llm_used is False
    assert response.provider == "hf_peft_lora"
    assert response.model == "Qwen/Qwen2.5-1.5B-Instruct + LoRA"
    assert response.error == "adapter test failure"
    assert response.fallback_reason == "LoRA runtime error: adapter test failure"


def test_local_connector_adapter_only_can_target_dolphin_lora_by_id(monkeypatch, tmp_path):
    captured = {}

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model="dphn/Dolphin3.0-Llama3.1-8B + LoRA",
            prompt=prompt,
            raw_output="Dolphin adapter answer.",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fail_ollama(*_args, **_kwargs):
        raise AssertionError("Dolphin adapter-only mode must not fall back to Ollama")

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fail_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(tmp_path / "qwen-active"),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: use dolphin adapter\nNova:",
            "user_message": "Use the Dolphin adapter for this answer.",
            "selected_route": "deepseek_direct",
            "use_lora_runtime": True,
            "adapter_only_mode": True,
            "lora_adapter_id": "nova-dolphin3-llama3-1-8b-full-sft-20260712",
        }
    )

    assert response.local_llm_used is True
    assert response.model == "dphn/Dolphin3.0-Llama3.1-8B + LoRA"
    assert captured["kwargs"]["adapter_id"] == "nova-dolphin3-llama3-1-8b-full-sft-20260712"


def test_local_connector_skips_lora_runtime_for_planner_fast_path(monkeypatch, tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    lora_calls = []

    def fake_lora(*_args, **_kwargs):
        lora_calls.append(True)
        return llm.LocalLLMResponse(
            local_llm_used=False,
            provider="hf_peft_lora",
            fallback_used=True,
            fallback_reason="test should not call LoRA",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_lora),
    )

    def fake_ollama(self, prompt, **_kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model="dolphin3",
            prompt=prompt,
            raw_output='{"route":"general_conversation"}',
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
            "NOVA_LORA_AUTO_MODE": "dolphin_first",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "Return JSON only.",
            "user_message": "How should this route?",
            "selected_route": "planner",
            "local_llm_model": "dolphin3",
        }
    )

    assert response.local_llm_used is True
    assert response.provider == "ollama"
    assert response.raw_output == '{"route":"general_conversation"}'
    assert lora_calls == []


def test_local_connector_uses_dolphin_first_for_normal_chat_by_default(monkeypatch, tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    lora_calls = []

    def fake_lora(*_args, **_kwargs):
        lora_calls.append(True)
        raise AssertionError("Normal Nova should use Dolphin first unless LoRA is explicit or a retry is requested")

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_lora),
    )

    def fake_ollama(self, prompt, **_kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model="dolphin3",
            prompt=prompt,
            raw_output="Fast Dolphin answer.",
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
            "NOVA_LORA_AUTO_MODE": "dolphin_first",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: how are you?\nNova:",
            "user_message": "How are you?",
            "selected_route": "general_conversation",
            "local_llm_model": "dolphin3",
        }
    )

    assert response.local_llm_used is True
    assert response.provider == "ollama"
    assert response.raw_output == "Fast Dolphin answer."
    assert lora_calls == []


def test_local_connector_smart_adapter_uses_qwen_for_factual_questions(monkeypatch, tmp_path):
    captured = {}

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        captured["kwargs"] = kwargs
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            prompt=prompt,
            raw_output="A bird is a feathered vertebrate.",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fail_ollama(*_args, **_kwargs):
        raise AssertionError("Smart adapter mode should use Qwen LoRA for factual questions before Ollama")

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fail_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "smart_adapter",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: What is a bird?\nNova:",
            "user_message": "What is a bird?",
            "selected_route": "general_conversation",
        }
    )

    assert response.local_llm_used is True
    assert captured["kwargs"]["adapter_id"] == llm.QWEN_FULL_LORA_ADAPTER_ID


def test_local_connector_smart_adapter_uses_dolphin_for_creative_and_social_prompts(monkeypatch):
    captured = {}

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        captured["kwargs"] = kwargs
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model="dphn/Dolphin3.0-Llama3.1-8B + LoRA",
            prompt=prompt,
            raw_output="Yeah, I can build that into a simple runner.",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fail_ollama(*_args, **_kwargs):
        raise AssertionError("Smart adapter mode should use Dolphin LoRA for creative/social prompts before Ollama")

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fail_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "smart_adapter",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "User: Can you make me a Temple Run style game?\nNova:",
            "user_message": "Can you make me a Temple Run style game?",
            "selected_route": "general_conversation",
        }
    )

    assert response.local_llm_used is True
    assert captured["kwargs"]["adapter_id"] == llm.DOLPHIN_FULL_LORA_ADAPTER_ID


def test_local_connector_qwen_first_uses_small_qwen_for_regular_social_chat(monkeypatch):
    captured = {}

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="hf_peft_lora",
            model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            prompt=prompt,
            raw_output="I am doing well and I remember the context you shared.",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )
    monkeypatch.setattr(
        llm.LocalLLMConnector,
        "_call_ollama",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Regular qwen_first chat must not call the larger Ollama model first")
        ),
    )
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "qwen_first",
        }
    )

    response = llm.LocalLLMConnector(config).generate(
        {
            "user_message": "How are you today?",
            "selected_route": "general_conversation",
            "memory_matches": "The user prefers concise answers.",
            "task_instruction": "Use Nova memory and answer naturally.",
        }
    )

    assert response.local_llm_used is True
    assert captured["kwargs"]["adapter_id"] == llm.QWEN_FULL_LORA_ADAPTER_ID
    assert "The user prefers concise answers." in captured["prompt"]


def test_local_connector_qwen_first_still_keeps_planner_on_fast_provider(monkeypatch):
    lora_calls = []

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=lambda *_args, **_kwargs: lora_calls.append(True)),
    )

    def fake_ollama(self, prompt, **_kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model="dolphin3",
            prompt=prompt,
            raw_output='{"route":"general_conversation"}',
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "qwen_first",
        }
    )

    response = llm.LocalLLMConnector(config).generate(
        {
            "user_message": "route this",
            "selected_route": "planner",
        }
    )

    assert response.provider == "ollama"
    assert lora_calls == []


def test_local_connector_ollama_qwen_first_uses_small_ollama_model_and_skips_lora(monkeypatch):
    captured = {}
    lora_calls = []

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=lambda *_args, **_kwargs: lora_calls.append(True)),
    )

    def fake_ollama(self, prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model=kwargs.get("model_override"),
            prompt=prompt,
            raw_output="Listening makes a good conversation.",
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LOCAL_LLM_MODEL": "qwen2.5:1.5b",
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "ollama_qwen_first",
        }
    )

    response = llm.LocalLLMConnector(config).generate(
        {
            "user_message": "What makes a good conversation?",
            "selected_route": "general_conversation",
            "local_llm_model": "qwen2.5:1.5b",
            "memory_matches": "The user values direct answers.",
        }
    )

    assert response.local_llm_used is True
    assert response.provider == "ollama"
    assert response.model == "qwen2.5:1.5b"
    assert captured["model_override"] == "qwen2.5:1.5b"
    assert "The user values direct answers." in captured["prompt"]
    assert lora_calls == []


def test_local_connector_smart_adapter_still_skips_planner_route(monkeypatch):
    lora_calls = []

    def fake_generate_with_lora(*_args, **_kwargs):
        lora_calls.append(True)
        raise AssertionError("Planner/control routes must stay fast and avoid adapter generation")

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fake_ollama(self, prompt, **_kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model="dolphin3",
            prompt=prompt,
            raw_output='{"route":"general_conversation"}',
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_AUTO_MODE": "smart_adapter",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate(
        {
            "raw_prompt": "Return route JSON.",
            "user_message": "route this",
            "selected_route": "planner",
        }
    )

    assert response.provider == "ollama"
    assert lora_calls == []


def test_local_connector_falls_back_to_ollama_when_lora_runtime_unavailable(monkeypatch, tmp_path):
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "adapter_config.json").write_text("{}", encoding="utf-8")

    def fake_generate_with_lora(prompt, config=None, **kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=False,
            provider="hf_peft_lora",
            model="Qwen/Qwen2.5-1.5B-Instruct + LoRA",
            prompt=prompt,
            error="transformers_not_installed",
            fallback_used=True,
            fallback_reason="LoRA runtime unavailable: transformers_not_installed",
        )

    monkeypatch.setitem(
        sys.modules,
        "nova_lora_runtime",
        SimpleNamespace(generate_with_lora=fake_generate_with_lora),
    )

    def fake_ollama(self, prompt, **_kwargs):
        return llm.LocalLLMResponse(
            local_llm_used=True,
            provider="ollama",
            model="dolphin3",
            prompt=prompt,
            raw_output="Fallback dolphin answer.",
        )

    monkeypatch.setattr(llm.LocalLLMConnector, "_call_ollama", fake_ollama)
    config = llm.LocalLLMConfig()
    config.config.update(
        {
            "NOVA_USE_LOCAL_LLM": True,
            "NOVA_LORA_ADAPTER_ENABLED": True,
            "NOVA_LORA_RUNTIME_ENABLED": True,
            "NOVA_LORA_ADAPTER_PATH": str(adapter_dir),
            "NOVA_LORA_BASE_MODEL": "Qwen/Qwen2.5-1.5B-Instruct",
        }
    )

    connector = llm.LocalLLMConnector(config)
    response = connector.generate({"raw_prompt": "User: hi\nNova:", "user_message": "hi"})

    assert response.local_llm_used is True
    assert response.provider == "ollama"
    assert response.raw_output == "Fallback dolphin answer."
