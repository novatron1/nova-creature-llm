"""
Model provider abstraction.
Each provider implements generate() and can be swapped via config.
"""
from __future__ import annotations
from typing import Optional


class ModelProvider:
    """Base interface for all model providers."""
    name: str = "base"

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt."""
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this provider is available."""
        return False


class MockProvider(ModelProvider):
    """Mock provider for testing. Returns rule-based responses."""
    name = "mock"

    def generate(self, prompt: str, **kwargs) -> str:
        return f"[Mock response to: {prompt[:60]}...]"

    def is_available(self) -> bool:
        return True


class OpenAIProvider(ModelProvider):
    """OpenAI API provider."""
    name = "openai"

    def __init__(self, api_key: str = "", model: str = "gpt-4o"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _lazy_init(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=self.api_key or None)
            except ImportError:
                raise ImportError("openai package not installed. Run: pip install openai")

    def generate(self, prompt: str, **kwargs) -> str:
        self._lazy_init()
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=kwargs.get("temperature", 0.7),
        )
        return response.choices[0].message.content

    def is_available(self) -> bool:
        try:
            self._lazy_init()
            return True
        except Exception:
            return False


class OllamaProvider(ModelProvider):
    """Ollama local model provider."""
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, **kwargs) -> str:
        import requests
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def is_available(self) -> bool:
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False


def get_provider(name: str, config: dict | None = None) -> ModelProvider:
    """Factory: get a provider by name."""
    cfg = config or {}
    providers = {
        "mock": MockProvider(),
        "openai": OpenAIProvider(
            api_key=cfg.get("api_key", ""),
            model=cfg.get("model", "gpt-4o"),
        ),
        "ollama": OllamaProvider(
            base_url=cfg.get("base_url", "http://localhost:11434"),
            model=cfg.get("model", "llama3"),
        ),
    }
    return providers.get(name, MockProvider())


# Global provider cache
_providers: dict[str, ModelProvider] = {}


def get_cached_provider(name: str, config: dict | None = None) -> ModelProvider:
    """Get or create a cached provider."""
    if name not in _providers:
        _providers[name] = get_provider(name, config)
    return _providers[name]
