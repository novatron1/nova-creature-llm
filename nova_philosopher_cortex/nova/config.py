"""
Nova configuration system.
Supports YAML-style config via dict, env vars, and config files.
"""
import os
import json
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NovaConfig:
    """Central configuration for Nova Philosopher Cortex."""

    # Model provider mappings
    models: dict = field(default_factory=lambda: {
        "language_cortex": "mock",
        "intent_detector": "mock",
        "assumption_detector": "mock",
        "philosopher_cortex": "mock",
        "science_cortex": "mock",
        "math_cortex": "mock",
        "final_voice": "mock",
    })

    # Provider settings
    provider_settings: dict = field(default_factory=lambda: {
        "mock": {"enabled": True},
        "openai": {
            "api_key": "",
            "model": "gpt-4o",
            "temperature": 0.7,
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama3",
        },
        "huggingface": {
            "model": "google/flan-t5-base",
        },
    })

    # Web / research settings
    web: dict = field(default_factory=lambda: {
        "enabled": False,
        "user_agent": "NovaPhilosopherCortex/0.1",
        "request_timeout": 15,
    })

    # Memory settings
    memory: dict = field(default_factory=lambda: {
        "enabled": True,
        "max_records": 10000,
        "memory_path": "nova/data/memory/nova_memory.jsonl",
        "training_path": "nova/data/memory/training_records.jsonl",
    })

    # Pipeline settings
    pipeline: dict = field(default_factory=lambda: {
        "strict_mode": True,
        "max_iterations": 3,
        "log_level": "INFO",
    })

    @classmethod
    def from_dict(cls, d: dict) -> "NovaConfig":
        cfg = cls()
        if "models" in d:
            cfg.models.update(d["models"])
        if "provider_settings" in d:
            for k, v in d["provider_settings"].items():
                if k in cfg.provider_settings:
                    cfg.provider_settings[k].update(v)
                else:
                    cfg.provider_settings[k] = v
        if "web" in d:
            cfg.web.update(d["web"])
        if "memory" in d:
            cfg.memory.update(d["memory"])
        if "pipeline" in d:
            cfg.pipeline.update(d["pipeline"])
        return cfg

    @classmethod
    def from_json(cls, path: str) -> "NovaConfig":
        with open(path) as f:
            return cls.from_dict(json.load(f))

    @classmethod
    def default(cls) -> "NovaConfig":
        return cls()


# Global config singleton
_config: Optional[NovaConfig] = None


def get_config() -> NovaConfig:
    global _config
    if _config is None:
        _config = NovaConfig.default()
    return _config


def set_config(cfg: NovaConfig) -> None:
    global _config
    _config = cfg
