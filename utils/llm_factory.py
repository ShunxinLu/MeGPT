"""
Universal LLM Factory - Provider-agnostic LLM client.
Works with any OpenAI-compatible endpoint (LM Studio, Ollama, vLLM, etc.)
Now reads from database for dynamic model selection.
"""
import json
import sqlite3
import logging
from pathlib import Path
from langchain_openai import ChatOpenAI
from config import config

logger = logging.getLogger(__name__)


def _is_coding_plan_model(model: str) -> bool:
    """Check if the model is a GLM-4.7 Coding Plan model."""
    if not model:
        return False
    # GLM-4.7 and GLM-4.5-air use the coding plan endpoint
    model_lower = model.lower()
    return "glm-4.7" in model_lower or "glm-4.5-air" in model_lower


def _get_provider_base_url(provider_id: str, model: str = None) -> str:
    """
    Get the correct base URL for a provider, considering model-specific endpoints.

    Some providers have different endpoints for specific models (e.g., GLM-4.7).
    """
    # Special handling for z.ai GLM-4.7 Coding Plan models
    if provider_id == "zai" and model and _is_coding_plan_model(model):
        logger.info(f"GLM-4.7 Coding Plan model detected: {model}, using api.z.ai endpoint")
        return "https://api.z.ai/api/coding/paas/v4"

    # Default endpoints for each provider
    provider_endpoints = {
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "groq": "https://api.groq.com/openai/v1",
        "deepseek": "https://api.deepseek.com",
        "zai": "https://open.bigmodel.cn/api/paas/v4",
        "xai": "https://api.x.ai/v1",
        "together": "https://api.together.xyz/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "lmstudio": None,  # Must be provided by user
        "ollama": None,  # Must be provided by user
    }
    return provider_endpoints.get(provider_id)


def _normalize_base_url(base_url: str) -> str:
    """
    Normalize base URL by stripping trailing /v1 suffix.

    ChatOpenAI will add /v1 automatically, so we need to remove it if present
    to avoid duplication like: http://localhost:1234/v1/v1/chat/completions
    """
    if not base_url:
        return base_url
    base_url = base_url.rstrip("/")
    if base_url.endswith("/v1"):
        base_url = base_url[:-3]
    return base_url


def _get_active_provider_from_db():
    """
    Get the active provider config from the database.
    Returns (base_url, api_key, model, provider_id) tuple or None if not found.
    """
    db_path = config.providers_db_path
    if not db_path.exists():
        logger.debug(f"Provider DB does not exist: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
            SELECT provider_id, config FROM provider_configs
            WHERE is_default = 1 AND enabled = 1
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row:
            provider_id, config_json = row
            provider_config = json.loads(config_json)

            # Extract connection details
            base_url = provider_config.get("base_url")
            api_key = provider_config.get("api_key", "not-needed")
            model = provider_config.get("model")

            logger.info(f"Loading provider from DB: {provider_id}, model: {model}")

            # If no base_url in config, use provider's default endpoint
            if not base_url:
                base_url = _get_provider_base_url(provider_id, model)

            # Normalize base_url (strip /v1 suffix for ChatOpenAI)
            if base_url:
                base_url = _normalize_base_url(base_url)

            if base_url and model:
                logger.info(f"Using provider: {provider_id}, model: {model}, base_url: {base_url}")
                return (base_url, api_key, model, provider_id)
            else:
                logger.warning(f"Provider {provider_id} missing base_url or model in config")
                logger.warning(f"  base_url: {base_url}, model: {model}")
        else:
            logger.debug("No default provider found in database")

        return None
    except Exception as e:
        logger.error(f"Error reading provider from DB: {e}", exc_info=True)
        return None


def get_llm(streaming: bool = True, temperature: float = 0.7) -> ChatOpenAI:
    """
    Create a ChatOpenAI instance configured for the active LLM provider.

    First checks database for user-selected provider/model,
    then falls back to config (environment variables).

    Args:
        streaming: Enable token-by-token streaming (default: True)
        temperature: Sampling temperature (default: 0.7)

    Returns:
        Configured ChatOpenAI instance
    """
    # Try to get from database first
    db_config = _get_active_provider_from_db()

    if db_config:
        base_url, api_key, model, provider_id = db_config
        logger.info(f"Creating LLM from DB config: provider={provider_id}, model={model}")
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            streaming=streaming,
        )

    # Fall back to config (env vars)
    logger.info(f"Creating LLM from env config: model={config.llm_model_name}")
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
    # Try to get from database first
    db_config = _get_active_provider_from_db()

    if db_config:
        base_url, api_key, model, provider_id = db_config
        logger.info(f"Creating LLM for tools from DB config: provider={provider_id}, model={model}")
        return ChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            streaming=False,  # Tools work better without streaming
        )

    # Fall back to config (env vars)
    logger.info(f"Creating LLM for tools from env config: model={config.llm_model_name}")
    return ChatOpenAI(
        base_url=config.llm_base_url,
        api_key=config.llm_api_key,
        model=config.llm_model_name,
        temperature=temperature,
        streaming=False,  # Tools work better without streaming
    )


def get_llm_config():
    """
    Get the current LLM configuration as a tuple.
    Returns (base_url, api_key, model) from database or env vars.

    This is used by code that makes direct HTTP calls instead of using ChatOpenAI.
    The returned base_url is ready for appending /chat/completions.
    For zai GLM-4.7 Coding Plan models, the base_url already includes the correct path.
    """
    db_config = _get_active_provider_from_db()

    if db_config:
        base_url, api_key, model, provider_id = db_config
        # Use the provider-specific base URL (handles special cases like GLM-4.7)
        provider_base_url = _get_provider_base_url(provider_id, model)

        # For zai GLM-4.7 Coding Plan, return the full URL (no /chat/completions needed)
        if provider_id == "zai" and _is_coding_plan_model(model):
            return (f"{provider_base_url}/chat/completions", api_key, model)
        else:
            # Standard OpenAI-compatible: base URL needs /chat/completions appended
            return (provider_base_url, api_key, model)

    # Fall back to env vars
    return (config.llm_base_url, config.llm_api_key, config.llm_model_name)


def get_llm_endpoint_url():
    """
    Get the full LLM endpoint URL for direct HTTP calls.
    Returns a URL that's ready to use (includes /chat/completions).

    This handles provider-specific endpoints like zai GLM-4.7 Coding Plan.
    """
    base_url, _, _ = get_llm_config()

    # If base_url already ends with /chat/completions, return as-is
    # Otherwise, append it
    if base_url.endswith("/chat/completions"):
        return base_url
    else:
        return f"{base_url}/chat/completions"


def get_embedding_config():
    """
    Get the current embedding provider configuration as a tuple.
    Returns (base_url, api_key, model) from database or env vars.

    The returned base_url includes /v1 suffix for direct HTTP calls.
    """
    from config import get_active_embedding_provider

    db_config = get_active_embedding_provider()

    if db_config:
        provider_config = db_config["config"]
        base_url = provider_config.get("base_url")
        api_key = provider_config.get("api_key", "not-needed")
        model = provider_config.get("model")

        if base_url and model:
            # Normalize and add /v1 for direct HTTP calls
            base_url = _normalize_base_url(base_url)
            return (f"{base_url}/v1", api_key, model)

    # Fall back to env vars
    return (
        _normalize_base_url(config.embedder_base_url) + "/v1",
        config.embedder_api_key,
        config.embedder_model_name
    )
