"""
Provider Management API Endpoints
Configure LLM providers and data sources via API
"""

import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from config import config, save_provider_config, load_provider_config, get_all_provider_configs
from config import save_data_source_config, get_all_data_source_configs
from providers.base import provider_registry
from providers.base import (
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/providers", tags=["providers"])

# Register built-in providers
provider_registry.register_llm_provider("openai", OpenAIProvider)
provider_registry.register_llm_provider("anthropic", AnthropicProvider)
provider_registry.register_llm_provider("lmstudio", LMStudioProvider)
provider_registry.register_llm_provider("ollama", OllamaProvider)
provider_registry.register_llm_provider("together", TogetherProvider)
provider_registry.register_llm_provider("groq", GroqProvider)
provider_registry.register_llm_provider("deepinfra", DeepInfraProvider)
provider_registry.register_llm_provider("deepseek", DeepSeekDirectProvider)
provider_registry.register_llm_provider("zai", ZAIProvider)
provider_registry.register_llm_provider("xai", XAIProvider)
provider_registry.register_llm_provider("openrouter", OpenRouterProvider)


# ========== Request/Response Models ==========

class ProviderConfigRequest(BaseModel):
    """Request to save/update provider configuration"""
    provider_id: str
    config: Dict[str, Any]
    enabled: bool = True


class ProviderConfigResponse(BaseModel):
    """Provider configuration response"""
    provider_id: str
    config: Dict[str, Any]  # Config with sensitive fields masked
    enabled: bool
    is_default: bool
    has_config: bool


class DataSourceConfigRequest(BaseModel):
    """Request to save/update data source configuration"""
    source_id: str
    source_type: str
    config: Dict[str, Any]
    enabled: bool = True
    sync_interval_minutes: Optional[int] = None


class DataSourceConfigResponse(BaseModel):
    """Data source configuration response"""
    source_id: str
    source_type: str
    config: Dict[str, Any]  # Config with sensitive fields masked
    enabled: bool
    sync_interval_minutes: Optional[int] = None
    last_sync: Optional[str] = None
    has_config: bool


class TestConnectionRequest(BaseModel):
    """Request to test provider connection"""
    provider_id: str
    config: Optional[Dict[str, Any]] = None


class ProviderInfo(BaseModel):
    """Provider information for UI"""
    id: str
    name: str
    description: str
    config_schema: Dict[str, Any]
    supports_streaming: bool
    supports_tools: bool
    max_context: int
    default_model: str
    available_models: List[str]


def _mask_sensitive_fields(
    provider_id: str,
    config: Dict[str, Any],
    schema: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Mask sensitive fields like API keys for UI display"""
    masked = config.copy()
    sensitive_fields = {"api_key", "password", "token", "secret", "private_key"}

    for key in sensitive_fields:
        if key in masked and masked[key]:
            # Show first 4 and last 4 characters, mask the middle
            value = masked[key]
            if isinstance(value, str) and len(value) > 8:
                masked[key] = f"{value[:4]}...{value[-4:]}"
            elif value:
                masked[key] = "***"

    return masked


def _get_provider_schema(provider_id: str) -> Optional[Dict[str, Any]]:
    """Get config schema for a provider"""
    provider_class = provider_registry.get_llm_provider(provider_id)
    if provider_class:
        # Create temp instance to get schema
        try:
            temp = provider_class({})
            return temp.config_schema
        except Exception:
            return None
    return None


# ========== Endpoints ==========

@router.get("/list")
async def list_providers() -> Dict[str, Any]:
    """
    List all available LLM providers with their configuration status.

    Returns:
        Dictionary with:
        - available: List of all registered providers with metadata
        - configured: List of providers with saved configuration
        - active: Currently active provider ID
    """
    # Get all provider info
    available = provider_registry.get_llm_providers_info()

    # Get configured providers from database
    configured = get_all_provider_configs()

    # Get active provider
    active = config.get_active_llm_provider()
    active_id = active.provider_id if active else None

    # Merge status
    for provider_info in available:
        provider_id = provider_info["id"]
        if provider_id in configured:
            provider_info["enabled"] = configured[provider_id]["enabled"]
            provider_info["is_default"] = configured[provider_id].get("is_default", False)
            provider_info["has_config"] = True
        else:
            # Check if env var config exists
            provider_config = config.get_provider_config(provider_id)
            if provider_config:
                provider_info["enabled"] = provider_config.enabled
                provider_info["has_config"] = True
            else:
                provider_info["enabled"] = False
                provider_info["has_config"] = False

    return {
        "available": available,
        "active": active_id,
    }


@router.get("/info/{provider_id}")
async def get_provider_info(provider_id: str) -> ProviderInfo:
    """
    Get detailed information about a specific provider.

    Args:
        provider_id: Provider identifier

    Returns:
        Provider information including config schema
    """
    providers = provider_registry.get_llm_providers_info()
    for provider in providers:
        if provider["id"] == provider_id:
            return ProviderInfo(**provider)

    raise HTTPException(status_code=404, detail=f"Provider {provider_id} not found")


@router.post("/configure")
async def configure_provider(request: ProviderConfigRequest) -> Dict[str, Any]:
    """
    Save or update provider configuration.

    Args:
        request: Provider configuration request

    Returns:
        Success status and updated configuration
    """
    provider_id = request.provider_id

    # Validate provider exists
    if provider_id not in provider_registry.list_llm_providers():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    # Validate config against schema
    schema = _get_provider_schema(provider_id)
    if schema:
        required = schema.get("required", [])
        for key in required:
            if key not in request.config:
                raise HTTPException(
                    status_code=400,
                    detail=f"Missing required config field: {key}"
                )

    # Save configuration
    save_provider_config(provider_id, request.config)

    # If this is set as default, clear default flag on others
    if request.enabled and request.config.get("is_default"):
        # Would need to update DB to clear other defaults
        pass

    logger.info(f"Provider {provider_id} configured")

    return {
        "success": True,
        "provider_id": provider_id,
        "enabled": request.enabled,
    }


@router.post("/set-default")
async def set_default_provider(provider_id: str) -> Dict[str, Any]:
    """
    Set a provider as the default active provider.

    Args:
        provider_id: Provider to set as default

    Returns:
        Success status
    """
    if provider_id not in provider_registry.list_llm_providers():
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    # Load current configs
    all_configs = get_all_provider_configs()

    # Update database to set this as default and clear others
    import sqlite3
    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("""
        UPDATE provider_configs SET is_default = 0
    """)
    conn.execute("""
        UPDATE provider_configs SET is_default = 1, enabled = 1
        WHERE provider_id = ?
    """, (provider_id,))
    conn.commit()
    conn.close()

    logger.info(f"Default provider set to: {provider_id}")

    return {"success": True, "default_provider": provider_id}


@router.get("/default")
async def get_default_provider() -> Dict[str, Any]:
    """Get the current default provider configuration"""
    import sqlite3

    if not config.providers_db_path.exists():
        # Return from config object (env vars)
        active = config.get_active_llm_provider()
        if active:
            return {
                "provider_id": active.provider_id,
                "config": active.config,
                "source": "environment",
            }
        raise HTTPException(status_code=404, detail="No default provider configured")

    conn = sqlite3.connect(config.providers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT provider_id, config, enabled FROM provider_configs
        WHERE is_default = 1
    """)
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "provider_id": row["provider_id"],
            "config": json.loads(row["config"]),
            "enabled": bool(row["enabled"]),
            "source": "database",
        }

    # Fallback to environment
    active = config.get_active_llm_provider()
    if active:
        return {
            "provider_id": active.provider_id,
            "config": active.config,
            "source": "environment",
        }

    raise HTTPException(status_code=404, detail="No default provider configured")


@router.post("/test")
async def test_provider_connection(request: TestConnectionRequest) -> Dict[str, Any]:
    """
    Test connection to a provider.

    Args:
        request: Test connection request with optional config override

    Returns:
        Test result with status and message
    """
    provider_id = request.provider_id
    test_config = request.config or {}

    # Get provider class
    provider_class = provider_registry.get_llm_provider(provider_id)
    if not provider_class:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_id}")

    # Merge with existing config
    existing_config = load_provider_config(provider_id)
    if existing_config and existing_config.get("config"):
        merged_config = {**existing_config["config"], **test_config}
    else:
        merged_config = test_config

    if not merged_config:
        # Try env config
        provider_cfg = config.get_provider_config(provider_id)
        if provider_cfg:
            merged_config = provider_cfg.config
        else:
            raise HTTPException(
                status_code=400,
                detail=f"No configuration found for provider {provider_id}. "
                "Provide config in request or set via environment variables."
            )

    try:
        # Create provider instance and test
        provider = provider_class(merged_config)
        is_valid = await provider.validate_connection()

        if is_valid:
            return {
                "success": True,
                "provider_id": provider_id,
                "message": "Connection successful",
            }
        else:
            return {
                "success": False,
                "provider_id": provider_id,
                "message": "Connection failed - check credentials",
            }

    except Exception as e:
        logger.error(f"Provider test failed for {provider_id}: {e}")
        return {
            "success": False,
            "provider_id": provider_id,
            "message": str(e),
        }


@router.get("/data-sources")
async def list_data_sources() -> Dict[str, Any]:
    """
    List all data source types and configured data sources.

    Returns:
        Dictionary with available data source types and configured instances
    """
    # Available data source types
    available_types = [
        {
            "id": "email",
            "name": "Email (IMAP)",
            "description": "Connect to email via IMAP to read and search emails",
            "config_schema": {
                "required": ["imap_server", "username", "password"],
                "properties": {
                    "imap_server": {"type": "string", "description": "IMAP server address"},
                    "imap_port": {"type": "integer", "default": 993},
                    "username": {"type": "string", "description": "Email username"},
                    "password": {"type": "string", "description": "Email password or app password"},
                    "use_ssl": {"type": "boolean", "default": True},
                },
            },
        },
        {
            "id": "notion",
            "name": "Notion",
            "description": "Connect to Notion databases",
            "config_schema": {
                "required": ["api_key"],
                "properties": {
                    "api_key": {"type": "string", "description": "Notion integration token"},
                    "database_id": {"type": "string", "description": "Database ID to sync"},
                },
            },
        },
        {
            "id": "github",
            "name": "GitHub",
            "description": "Sync repositories from GitHub",
            "config_schema": {
                "required": ["token"],
                "properties": {
                    "token": {"type": "string", "description": "GitHub personal access token"},
                    "repos": {"type": "list", "description": "List of repos (owner/repo format)"},
                },
            },
        },
        {
            "id": "filesystem",
            "name": "Local File System",
            "description": "Watch and index local directories",
            "config_schema": {
                "required": ["paths"],
                "properties": {
                    "paths": {"type": "list", "description": "List of directory paths to watch"},
                    "file_patterns": {"type": "list", "default": ["*.md", "*.txt", "*.py", "*.js"]},
                    "exclude_patterns": {"type": "list", "default": ["node_modules", ".git"]},
                },
            },
        },
    ]

    # Get configured data sources
    configured = get_all_data_source_configs()

    return {
        "available_types": available_types,
        "configured": [
            {
                "source_id": source_id,
                **config,
                "config": _mask_sensitive_fields(source_id, config["config"]),
            }
            for source_id, config in configured.items()
        ],
    }


@router.post("/data-sources/configure")
async def configure_data_source(request: DataSourceConfigRequest) -> Dict[str, Any]:
    """
    Save or update data source configuration.

    Args:
        request: Data source configuration request

    Returns:
        Success status
    """
    save_data_source_config(
        request.source_id,
        request.source_type,
        {**request.config, "sync_interval": request.sync_interval_minutes}
    )

    logger.info(f"Data source {request.source_id} ({request.source_type}) configured")

    return {
        "success": True,
        "source_id": request.source_id,
        "source_type": request.source_type,
    }


@router.post("/data-sources/{source_id}/sync")
async def sync_data_source(source_id: str) -> Dict[str, Any]:
    """
    Trigger a sync for a data source.

    Args:
        source_id: Data source to sync

    Returns:
        Sync result
    """
    # This would trigger the actual sync process
    # For now, return a placeholder
    return {
        "success": True,
        "source_id": source_id,
        "message": "Sync triggered (implementation pending)",
    }


@router.delete("/data-sources/{source_id}")
async def delete_data_source(source_id: str) -> Dict[str, Any]:
    """
    Delete a data source configuration.

    Args:
        source_id: Data source to delete

    Returns:
        Success status
    """
    import sqlite3

    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("DELETE FROM data_source_configs WHERE source_id = ?", (source_id,))
    conn.commit()
    conn.close()

    logger.info(f"Data source {source_id} deleted")

    return {"success": True, "source_id": source_id}
