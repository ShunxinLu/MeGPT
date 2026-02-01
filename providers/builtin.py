"""
Built-in LLM Providers
Includes: OpenAI, Anthropic, LM Studio, Ollama, Together, Groq, DeepInfra
"""

import logging
import httpx
import json
from typing import List, Dict, Any, Optional, AsyncIterator
from .llm_provider import (
    LLMProvider,
    LLMMessage,
    LLMResponse,
    ChatCompletionOptions,
    StreamChunk,
    MessageRole,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI API provider (works with OpenAI-compatible APIs)"""

    provider_id = "openai"
    provider_name = "OpenAI"
    description = "OpenAI GPT models (also works with compatible APIs)"

    config_schema = {
        "required": ["api_key", "base_url"],
        "properties": {
            "api_key": {"type": "string", "description": "API key"},
            "base_url": {
                "type": "string",
                "description": "API base URL",
                "default": "https://api.openai.com/v1",
            },
            "model": {
                "type": "string",
                "description": "Model name",
                "default": "gpt-4o",
            },
            "max_tokens": {"type": "integer", "default": 4096},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        # Allow base_url to be optional for real OpenAI
        if "base_url" not in config:
            config["base_url"] = "https://api.openai.com/v1"
        super().__init__(config)
        self.api_key = config["api_key"]
        self.base_url = config["base_url"].rstrip("/")
        self.model = config.get("model", "gpt-4o")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def get_available_models(self) -> List[str]:
        """Fetch available models from OpenAI API"""
        client = self._get_client()
        try:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]
        except Exception as e:
            logger.warning(f"Failed to fetch OpenAI models: {e}")
            return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"]

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or self.get_max_context_length(),
            "top_p": options.top_p,
        }

        if options.stop:
            payload["stop"] = options.stop
        if options.tools:
            payload["tools"] = options.tools
        if options.tool_choice:
            payload["tool_choice"] = options.tool_choice

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        msg = choice["message"]

        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
            model=data.get("model"),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or self.get_max_context_length(),
            "top_p": options.top_p,
            "stream": True,
        }

        if options.stop:
            payload["stop"] = options.stop
        if options.tools:
            payload["tools"] = options.tools
        if options.tool_choice:
            payload["tool_choice"] = options.tool_choice

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"]
                        content = delta.get("content") or ""
                        finish_reason = data["choices"][0].get("finish_reason")

                        yield StreamChunk(
                            content=content,
                            delta=content,
                            finish_reason=finish_reason,
                        )
                    except json.JSONDecodeError:
                        continue

    def get_max_context_length(self) -> int:
        return self.config.get("max_tokens", 128000)

    def get_default_model(self) -> str:
        return self.model

    def get_available_models(self) -> List[str]:
        return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider"""

    provider_id = "anthropic"
    provider_name = "Anthropic"
    description = "Anthropic Claude models"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string", "description": "Anthropic API key"},
            "model": {"type": "string", "default": "claude-3-5-sonnet-20241022"},
            "max_tokens": {"type": "integer", "default": 200000},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "claude-3-5-sonnet-20241022")
        self.base_url = config.get("base_url", "https://api.anthropic.com")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    def _convert_messages(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        """Convert messages to Anthropic format"""
        converted = []
        system_message = None

        for msg in messages:
            if isinstance(msg.role, MessageRole):
                role = msg.role.value
            else:
                role = msg.role

            if role == "system":
                system_message = msg.content
            else:
                # Anthropic uses "user" and "assistant" (no "system" in messages array)
                # Tool messages need special handling
                if role == "tool":
                    # Convert tool response to user message with tool_result content
                    converted.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": msg.tool_call_id,
                                    "content": msg.content,
                                }
                            ],
                        }
                    )
                else:
                    converted.append({"role": role, "content": msg.content})

        return converted, system_message

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        converted_messages, system_message = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": options.max_tokens or 4096,
            "temperature": options.temperature,
            "top_p": options.top_p,
        }

        if system_message:
            payload["system"] = system_message
        if options.stop:
            payload["stop_sequences"] = options.stop
        if options.tools:
            payload["tools"] = options.tools
        if options.tool_choice:
            payload["tool_choice"] = options.tool_choice

        response = await client.post("/v1/messages", json=payload)
        response.raise_for_status()
        data = response.json()

        content = ""
        tool_calls = []

        if "content" in data:
            for block in data["content"]:
                if block["type"] == "text":
                    content += block["text"]
                elif block["type"] == "tool_use":
                    tool_calls.append(
                        {
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"]),
                            },
                        }
                    )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=data.get("stop_reason"),
            usage=data.get("usage", {}),
            model=data.get("model"),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        converted_messages, system_message = self._convert_messages(messages)

        payload = {
            "model": self.model,
            "messages": converted_messages,
            "max_tokens": options.max_tokens or 4096,
            "temperature": options.temperature,
            "top_p": options.top_p,
            "stream": True,
        }

        if system_message:
            payload["system"] = system_message
        if options.stop:
            payload["stop_sequences"] = options.stop

        async with client.stream("POST", "/v1/messages", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        data = json.loads(data_str)
                        if data["type"] == "content_block_delta":
                            delta = data.get("delta", {})
                            content = delta.get("text", "")
                            yield StreamChunk(content=content, delta=content)
                        elif data["type"] == "message_stop":
                            yield StreamChunk(
                                content="",
                                delta="",
                                finish_reason=data.get("stop_reason"),
                            )
                    except json.JSONDecodeError:
                        continue

    def get_max_context_length(self) -> int:
        return self.config.get("max_tokens", 200000)

    def get_default_model(self) -> str:
        return self.model

    async def get_available_models(self) -> List[str]:
        """Fetch available models from Anthropic API"""
        # Anthropic doesn't have a public /models endpoint
        # Return current known models
        return [
            "claude-sonnet-4-20250514",
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]


class LMStudioProvider(LLMProvider):
    """LM Studio local provider"""

    provider_id = "lmstudio"
    provider_name = "LM Studio"
    description = "Local LM Studio server"

    config_schema = {
        "required": ["base_url"],
        "properties": {
            "base_url": {"type": "string", "default": "http://localhost:1234/v1"},
            "model": {"type": "string", "default": "local-model"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.model = config.get("model", "local-model")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Content-Type": "application/json"},
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or -1,  # LM Studio uses -1 for unlimited
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        msg = choice["message"]

        return LLMResponse(
            content=msg.get("content") or "",
            tool_calls=msg.get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or -1,
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"]
                        content = delta.get("content") or ""
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    def get_max_context_length(self) -> int:
        return 32768  # Typical for local models
    
    async def get_available_models(self) -> List[str]:
        """Get list of available LM Studio models"""
        client = self._get_client()
        try:
            # Handle both http://localhost:1234 and http://localhost:1234/v1
            base = self.base_url.rstrip('/')
            if not base.endswith('/v1'):
                base = f"{base}/v1"
            
            response = await client.get(f"{base}/models")
            response.raise_for_status()
            data = response.json()
            # LM Studio returns OpenAI-compatible format
            models = [m["id"] for m in data.get("data", [])]
            return models if models else [self.model]
        except Exception:
            # Fallback to configured model if API call fails
            return [self.model]


class OllamaProvider(LLMProvider):
    """Ollama local provider"""

    provider_id = "ollama"
    provider_name = "Ollama"
    description = "Local Ollama server"

    config_schema = {
        "required": ["base_url"],
        "properties": {
            "base_url": {"type": "string", "default": "http://localhost:11434"},
            "model": {"type": "string", "default": "llama3"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = config["base_url"].rstrip("/")
        self.model = config.get("model", "llama3")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Content-Type": "application/json"},
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "options": {
                "temperature": options.temperature,
                "num_predict": options.max_tokens or 2048,
                "top_p": options.top_p,
            },
        }

        if options.stop:
            payload["options"]["stop"] = options.stop

        response = await client.post("/api/chat", json=payload)
        response.raise_for_status()
        data = response.json()

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            finish_reason="done" if data.get("done") else None,
            usage=data.get("prompt_eval_count", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "stream": True,
            "options": {
                "temperature": options.temperature,
                "num_predict": options.max_tokens or 2048,
                "top_p": options.top_p,
            },
        }

        if options.stop:
            payload["options"]["stop"] = options.stop

        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                try:
                    data = json.loads(line)
                    content = data.get("message", {}).get("content", "")
                    yield StreamChunk(
                        content=content,
                        delta=content,
                        finish_reason="done" if data.get("done") else None,
                    )
                except json.JSONDecodeError:
                    continue

    def get_max_context_length(self) -> int:
        return 32768

    async def get_available_models(self) -> List[str]:
        """Get list of available Ollama models"""
        client = self._get_client()
        try:
            response = await client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return [self.model]


class TogetherProvider(LLMProvider):
    """Together AI provider"""

    provider_id = "together"
    provider_name = "Together AI"
    description = "Together AI hosted models"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {
                "type": "string",
                "default": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            },
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.together.xyz/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "top_p": options.top_p,
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    async def get_available_models(self) -> List[str]:
        """Fetch available models from Together API"""
        client = self._get_client()
        try:
            # Together uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"]
        except Exception as e:
            logger.warning(f"Failed to fetch Together models: {e}")
            return ["meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"]


class GroqProvider(LLMProvider):
    """Groq provider"""

    provider_id = "groq"
    provider_name = "Groq"
    description = "Groq fast inference"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "llama-3.3-70b-versatile"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "llama-3.3-70b-versatile")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.groq.com/openai/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "top_p": options.top_p,
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    async def get_available_models(self) -> List[str]:
        """Fetch available models from Groq API"""
        client = self._get_client()
        try:
            # Groq uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile"]
        except Exception as e:
            logger.warning(f"Failed to fetch Groq models: {e}")
            return ["llama-3.3-70b-versatile", "llama-3.1-70b-versatile"]


class DeepInfraProvider(LLMProvider):
    """DeepInfra provider"""

    provider_id = "deepinfra"
    provider_name = "DeepInfra"
    description = "DeepInfra fast inference"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "deepseek-ai/DeepSeek-V3"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "deepseek-ai/DeepSeek-V3")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.deepinfra.com/v1/openai",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "top_p": options.top_p,
        }

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "stream": True,
        }

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    async def get_available_models(self) -> List[str]:
        """Fetch available models from DeepInfra API"""
        client = self._get_client()
        try:
            # DeepInfra uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["deepseek-ai/DeepSeek-V3"]
        except Exception as e:
            logger.warning(f"Failed to fetch DeepInfra models: {e}")
            return ["deepseek-ai/DeepSeek-V3"]


class DeepSeekDirectProvider(LLMProvider):
    """DeepSeek direct API provider (platform.deepseek.com)"""

    provider_id = "deepseek"
    provider_name = "DeepSeek"
    description = "DeepSeek AI models (direct API from platform.deepseek.com)"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "deepseek-chat"},
            "base_url": {"type": "string", "default": "https://api.deepseek.com"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "deepseek-chat")
        self.base_url = config.get("base_url", "https://api.deepseek.com").rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 8192,
            "top_p": options.top_p,
        }

        if options.stop:
            payload["stop"] = options.stop

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 8192,
            "stream": True,
        }

        if options.stop:
            payload["stop"] = options.stop

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    def get_max_context_length(self) -> int:
        return 128000  # DeepSeek-V3 context

    async def get_available_models(self) -> List[str]:
        """Fetch available models from DeepSeek API"""
        client = self._get_client()
        try:
            # DeepSeek uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["deepseek-chat", "deepseek-coder"]
        except Exception as e:
            logger.warning(f"Failed to fetch DeepSeek models: {e}")
            return ["deepseek-chat", "deepseek-coder"]


class ZAIProvider(LLMProvider):
    """z.ai provider - Chinese AI service (zhipu AI)"""

    provider_id = "zai"
    provider_name = "z.ai"
    description = "z.ai - Chinese AI service with GLM models"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "glm-4-flash"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "glm-4-flash")
        self._client: Optional[httpx.AsyncClient] = None

        # Determine base URL based on model type
        # GLM-4.7 (Coding Plan) uses a different endpoint
        if self._is_coding_plan_model(self.model):
            self.base_url = "https://api.z.ai/api/coding/paas/v4"
        else:
            self.base_url = "https://open.bigmodel.cn/api/paas/v4"

    def _is_coding_plan_model(self, model: str) -> bool:
        """Check if the model is a GLM-4.7 Coding Plan model."""
        return model in ["glm-4.7", "glm-4.5-air"]

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 8192,
            "top_p": options.top_p,
        }

        if options.stop:
            payload["stop"] = options.stop

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 8192,
            "stream": True,
        }

        if options.stop:
            payload["stop"] = options.stop

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        content = data["choices"][0]["delta"].get("content", "")
                        yield StreamChunk(content=content, delta=content)
                    except json.JSONDecodeError:
                        continue

    def get_max_context_length(self) -> int:
        return 128000

    async def get_available_models(self) -> List[str]:
        """Fetch available models from zhipu AI API"""
        client = self._get_client()
        try:
            # zhipu AI uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["glm-4-flash", "glm-4-plus", "glm-4"]
        except Exception as e:
            logger.warning(f"Failed to fetch z.ai models: {e}")
            # Return fallback list
            return ["glm-4-flash", "glm-4-plus", "glm-4"]


class XAIProvider(LLMProvider):
    """xAI (Grok) provider"""

    provider_id = "xai"
    provider_name = "xAI"
    description = "xAI Grok models"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "grok-beta"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "grok-beta")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url="https://api.x.ai/v1",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "top_p": options.top_p,
            "stream": False,
        }

        if options.stop:
            payload["stop"] = options.stop

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens or 4096,
            "stream": True,
        }

        if options.stop:
            payload["stop"] = options.stop

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            try:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data["choices"][0]["delta"].get("content", "")
                            yield StreamChunk(content=content, delta=content)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Stream error: {e}")
                raise

    def get_max_context_length(self) -> int:
        return 128000

    async def get_available_models(self) -> List[str]:
        """Fetch available models from xAI API"""
        client = self._get_client()
        try:
            # xAI uses OpenAI-compatible /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["grok-beta"]
        except Exception as e:
            logger.warning(f"Failed to fetch xAI models: {e}")
            return ["grok-beta"]


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider"""

    provider_id = "openrouter"
    provider_name = "OpenRouter"
    description = "Unified interface for top LLMs"

    config_schema = {
        "required": ["api_key"],
        "properties": {
            "api_key": {"type": "string"},
            "model": {"type": "string", "default": "openai/gpt-4o"},
            "site_url": {"type": "string", "description": "Your site URL (optional)"},
            "site_name": {"type": "string", "description": "Your site name (optional)"},
        },
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.model = config.get("model", "openai/gpt-4o")
        self.site_url = config.get("site_url", "")
        self.site_name = config.get("site_name", "")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if self.site_url:
                headers["HTTP-Referer"] = self.site_url
            if self.site_name:
                headers["X-Title"] = self.site_name

            self._client = httpx.AsyncClient(
                base_url="https://openrouter.ai/api/v1",
                headers=headers,
                timeout=120,
            )
        return self._client

    async def chat_completion(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> LLMResponse:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "top_p": options.top_p,
        }

        if options.stop:
            payload["stop"] = options.stop

        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        return LLMResponse(
            content=choice["message"].get("content", ""),
            tool_calls=choice["message"].get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage", {}),
        )

    async def chat_completion_stream(
        self, messages: List[LLMMessage], options: ChatCompletionOptions
    ) -> AsyncIterator[StreamChunk]:
        client = self._get_client()

        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "temperature": options.temperature,
            "max_tokens": options.max_tokens,
            "stream": True,
        }

        if options.stop:
            payload["stop"] = options.stop

        async with client.stream("POST", "/chat/completions", json=payload) as response:
            try:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            content = data["choices"][0]["delta"].get("content", "")
                            yield StreamChunk(content=content, delta=content)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"Stream error: {e}")
                raise

    def get_max_context_length(self) -> int:
        return 128000  # Varies by model

    async def get_available_models(self) -> List[str]:
        """Fetch available models from OpenRouter API"""
        client = self._get_client()
        try:
            # OpenRouter has a /models endpoint
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            return models if models else ["openai/gpt-4o", "anthropic/claude-3.5-sonnet"]
        except Exception as e:
            logger.warning(f"Failed to fetch OpenRouter models: {e}")
            return [
                "openai/gpt-4o",
                "anthropic/claude-3.5-sonnet",
                "meta-llama/llama-3.1-70b-instruct",
                "google/gemini-pro-1.5",
            ]
