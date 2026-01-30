"""
Provider Plugin System for MeGPT
Allows users to bring their own LLM providers and data sources
"""

from .llm_provider import (
    LLMProvider,
    LLMResponse,
    LLMMessage,
    ChatCompletionOptions,
    StreamChunk,
)
from .registry import ProviderRegistry, provider_registry
from .builtin import (
    OpenAIProvider,
    AnthropicProvider,
    LMStudioProvider,
    OllamaProvider,
    TogetherProvider,
    GroqProvider,
    DeepInfraProvider,
    DeepSeekDirectProvider,
    ZAIProvider,
    XAIProvider,
    OpenRouterProvider,
)

__all__ = [
    # Base interfaces
    "LLMProvider",
    "LLMResponse",
    "LLMMessage",
    "ChatCompletionOptions",
    "StreamChunk",
    # Registry
    "ProviderRegistry",
    "provider_registry",
    # Built-in providers
    "OpenAIProvider",
    "AnthropicProvider",
    "LMStudioProvider",
    "OllamaProvider",
    "TogetherProvider",
    "GroqProvider",
    "DeepInfraProvider",
    "DeepSeekDirectProvider",
    "ZAIProvider",
    "XAIProvider",
    "OpenRouterProvider",
]
