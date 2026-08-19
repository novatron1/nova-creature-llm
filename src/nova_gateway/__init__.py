"""Nova provider-independent compatibility gateway."""

from .config import CONFIG_VERSION, GatewayConfig
from .core import NOVA_API_VERSION, NOVA_VERSION, NovaGatewayCore
from .engines import ENGINE_INTERFACE_VERSION, NovaEngineRegistry
from .comfyui import COMFYUI_ENGINE_VERSION, ComfyUIEngine
from .dream_lab import DREAM_LAB_INTERFACE_VERSION, DREAM_LAB_SCHEMA_VERSION, NovaDreamLab
from .errors import *  # noqa: F401,F403
from .model_registry import CAPABILITY_SCHEMA_VERSION, NovaModelCapability, NovaModelRegistry
from .providers import (
    PROVIDER_EXTENSION_POINTS,
    PROVIDER_INTERFACE_VERSION,
    ExistingNovaProvider,
    MockProvider,
    NovaModelProvider,
    NovaProviderRegistry,
    OllamaProvider,
)
from .router import NovaTaskRouter, RoutingDecision
from .tools import TOOL_CATEGORIES, TOOL_SCHEMA_VERSION, NovaRegisteredTool, NovaToolRegistry
from .world_model import (
    WORLD_MODEL_INTERFACE_VERSION,
    WORLD_MODEL_PERSISTENCE_MODES,
    WORLD_MODEL_SCHEMA_VERSION,
    CognitiveBlackboard,
    NovaWorldModel,
)

__all__ = [
    "CAPABILITY_SCHEMA_VERSION",
    "CONFIG_VERSION",
    "ENGINE_INTERFACE_VERSION",
    "COMFYUI_ENGINE_VERSION",
    "ComfyUIEngine",
    "DREAM_LAB_INTERFACE_VERSION",
    "DREAM_LAB_SCHEMA_VERSION",
    "NovaDreamLab",
    "NOVA_API_VERSION",
    "NOVA_VERSION",
    "PROVIDER_EXTENSION_POINTS",
    "PROVIDER_INTERFACE_VERSION",
    "ExistingNovaProvider",
    "GatewayConfig",
    "MockProvider",
    "NovaModelCapability",
    "NovaModelProvider",
    "NovaModelRegistry",
    "NovaGatewayCore",
    "NovaEngineRegistry",
    "NovaProviderRegistry",
    "NovaTaskRouter",
    "NovaRegisteredTool",
    "NovaToolRegistry",
    "OllamaProvider",
    "RoutingDecision",
    "TOOL_CATEGORIES",
    "TOOL_SCHEMA_VERSION",
    "WORLD_MODEL_INTERFACE_VERSION",
    "WORLD_MODEL_PERSISTENCE_MODES",
    "WORLD_MODEL_SCHEMA_VERSION",
    "CognitiveBlackboard",
    "NovaWorldModel",
]
