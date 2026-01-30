"""
LLM Provider Base Interface
Defines the contract for all LLM providers
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator, Iterator
from dataclasses import dataclass, field
from enum import Enum


class MessageRole(Enum):
    """Standard message roles"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    FUNCTION = "function"


@dataclass
class LLMMessage:
    """Standardized message format"""
    role: MessageRole | str
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to provider-agnostic dict"""
        result = {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
        }
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMMessage":
        """Create from dict"""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class ChatCompletionOptions:
    """Options for chat completion"""
    max_tokens: Optional[int] = None
    temperature: float = 0.7
    top_p: float = 1.0
    stop: Optional[List[str]] = None
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str | Dict[str, Any]] = None
    stream: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Standardized response format"""
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    usage: Dict[str, int] = field(default_factory=dict)
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A chunk of streaming response"""
    content: str
    delta: str
    finish_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Base class for all LLM providers.
    Implement this interface to add a new provider.
    """

    # Provider metadata
    provider_id: str = "base"
    provider_name: str = "Base Provider"
    description: str = "Base provider interface"

    # Configuration schema (for UI validation)
    config_schema: Dict[str, Any] = {}

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._validate_config()

    def _validate_config(self):
        """Validate provider configuration"""
        # Base validation - can be overridden
        required_keys = self.config_schema.get("required", [])
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Missing required config key: {key}")

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[LLMMessage],
        options: ChatCompletionOptions,
    ) -> LLMResponse:
        """
        Get a chat completion response.

        Args:
            messages: List of conversation messages
            options: Completion options

        Returns:
            LLMResponse with content and metadata
        """
        pass

    @abstractmethod
    async def chat_completion_stream(
        self,
        messages: List[LLMMessage],
        options: ChatCompletionOptions,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream a chat completion response.

        Args:
            messages: List of conversation messages
            options: Completion options

        Yields:
            StreamChunk with incremental content
        """
        pass

    def supports_streaming(self) -> bool:
        """Check if provider supports streaming"""
        return True

    def supports_tools(self) -> bool:
        """Check if provider supports function calling"""
        return True

    def get_max_context_length(self) -> int:
        """Get maximum context window size"""
        return 4096

    def get_default_model(self) -> str:
        """Get default model for this provider"""
        return "default"

    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        return [self.get_default_model()]

    async def validate_connection(self) -> bool:
        """Validate that the provider is accessible and credentials work"""
        try:
            response = await self.chat_completion(
                [LLMMessage(role="user", content="Hi")],
                ChatCompletionOptions(max_tokens=5),
            )
            return bool(response.content)
        except Exception:
            return False

    def get_provider_info(self) -> Dict[str, Any]:
        """Get provider information for UI display"""
        return {
            "id": self.provider_id,
            "name": self.provider_name,
            "description": self.description,
            "config_schema": self.config_schema,
            "supports_streaming": self.supports_streaming(),
            "supports_tools": self.supports_tools(),
            "max_context": self.get_max_context_length(),
            "default_model": self.get_default_model(),
            "available_models": self.get_available_models(),
        }
