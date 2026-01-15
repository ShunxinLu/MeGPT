"""
Universal LLM Factory - Provider-agnostic LLM client.
Works with any OpenAI-compatible endpoint (LM Studio, Ollama, vLLM, etc.)
"""
from langchain_openai import ChatOpenAI
from config import config


def get_llm(streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance configured for the local LLM server.
    
    Args:
        streaming: Enable token-by-token streaming (default: True)
        temperature: Sampling temperature (default: 0.7)
    
    Returns:
        Configured ChatOpenAI instance
    """
    return ChatOpenAI(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model_name,
        temperature=temperature,
        streaming=streaming,
    )


def get_llm_for_tools(temperature: float = 0.0) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance optimized for tool calling.
    Uses lower temperature for more deterministic tool selection.
    """
    return ChatOpenAI(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model_name,
        temperature=temperature,
        streaming=False,  # Tools work better without streaming
    )
