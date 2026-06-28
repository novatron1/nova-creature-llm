"""Model Registry - maps modules to model providers for easy swapping."""
from typing import Optional
from nova.config import get_config
from nova.model_provider import get_cached_provider


class ModelRegistry:
    """Maps pipeline modules to model providers.
    Allows swapping between mock, local, Ollama, HuggingFace, and OpenAI models.
    """

    def __init__(self):
        self.config = get_config()

    def get_provider_for(self, module_name: str):
        """Get the provider for a given module name."""
        model_name = self.config.models.get(module_name, "mock")
        provider_cfg = self.config.provider_settings.get(model_name, {})
        return get_cached_provider(model_name, provider_cfg)

    def register(self, module_name: str, provider_name: str) -> None:
        """Register a module to use a specific provider."""
        self.config.models[module_name] = provider_name

    def list_registrations(self) -> dict:
        """List all current module-to-provider mappings."""
        return dict(self.config.models)

    def switch_all(self, provider_name: str) -> None:
        """Switch all modules to a single provider."""
        for module in self.config.models:
            self.config.models[module] = provider_name

    @staticmethod
    def describe_swap_plan() -> str:
        """Describe how to swap mock modules for real models."""
        return """
MODEL SWAP PLAN
===============

Phase 1: Local Models
- Install a local model via Ollama: ollama pull llama3
- Set config: models.{module_name}: ollama
- Works for: language_cortex, intent_detector, final_voice

Phase 2: HuggingFace Models
- Install: pip install transformers torch
- Use: huggingface provider
- Good for: small control modules (intent, assumption, bias detection)
- Recommended: google/flan-t5-base for control tasks

Phase 3: OpenAI
- Set OPENAI_API_KEY env var
- Use: openai provider
- Best for: language_cortex, philosopher_cortex, final_voice
- Configure model: gpt-4o or gpt-4o-mini

Example config:
  models:
    language_cortex: openai
    intent_detector: ollama
    philosopher_cortex: openai
    math_cortex: mock
    final_voice: openai

To implement:
  1. Update nova/config.py NovaConfig.models dict
  2. Or create a JSON config file and load with NovaConfig.from_json()
"""
