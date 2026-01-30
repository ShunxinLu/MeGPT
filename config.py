"""
Configuration loader for MeGPT.
Loads environment variables with sensible defaults for local development.
Supports pluggable LLM providers and data sources.
"""

import logging
import os
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load .env file
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a single provider"""
    provider_id: str  # e.g., "openai", "anthropic", "ollama"
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    is_default: bool = False


@dataclass
class DataSourceConfig:
    """Configuration for a data source"""
    source_id: str
    source_type: str  # e.g., "email", "calendar", "notion"
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    sync_interval_minutes: Optional[int] = None
    last_sync: Optional[str] = None  # ISO datetime


@dataclass
class Config:
    """Application configuration with typed fields and defaults."""

    # ========== Environment Mode ==========
    env_mode: str = os.getenv("ENV_MODE", "dev")  # "dev" or "prod"

    # ========== LLM Provider Settings ==========
    # Active provider ID (for backward compatibility)
    llm_provider: str = os.getenv("LLM_PROVIDER", "lmstudio")

    # Legacy settings (for backward compatibility)
    # Note: base URLs should NOT include /v1 suffix - it's added per API call
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:1234")
    llm_api_key: str = os.getenv("LLM_API_KEY", "lm-studio")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "qwen/qwen3-vl-30b")
    context_window_size: int = int(os.getenv("CONTEXT_WINDOW_SIZE", "4096"))

    # Vision Language Model for document processing
    vlm_model: str = os.getenv("VLM_MODEL", "qwen/qwen3-vl-30b")
    vlm_base_url: str = os.getenv("VLM_BASE_URL", "")  # Empty means use llm_base_url

    # Multiple provider configurations (from env or config file)
    llm_providers: List[ProviderConfig] = field(default_factory=list)

    # ========== Embedder Settings ==========
    embedder_base_url: str = os.getenv("EMBEDDER_BASE_URL", "http://localhost:1234")
    embedder_api_key: str = os.getenv("EMBEDDER_API_KEY", "lm-studio")
    embedder_model_name: str = os.getenv("EMBEDDER_MODEL_NAME", "text-embedding-bge-m3")

    # ========== Qdrant Settings ==========
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))

    # ========== Feature Flags ==========
    enable_web_search: bool = os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"

    # ========== User Identity ==========
    user_id: str = os.getenv("USER_ID", "default_user")

    # ========== Authentication ==========
    api_key: Optional[str] = os.getenv("API_KEY", None)
    admin_api_key: Optional[str] = os.getenv("ADMIN_API_KEY", None)

    # ========== Backup Settings ==========
    backup_interval_hours: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "0"))
    backup_retention_count: int = int(os.getenv("BACKUP_RETENTION_COUNT", "10"))
    auto_backup_before_restore: bool = (
        os.getenv("AUTO_BACKUP_BEFORE_RESTORE", "true").lower() == "true"
    )

    # ========== Data Sources ==========
    data_sources: List[DataSourceConfig] = field(default_factory=list)

    def __post_init__(self):
        """Initialize provider configs from environment variables"""
        self._load_provider_configs_from_env()
        self._load_data_source_configs_from_env()

    def _load_provider_configs_from_env(self):
        """Load LLM provider configurations from environment variables"""
        providers = []

        # Helper to get env var with prefix
        def get_prefixed_env(prefix: str, key: str, default: str = "") -> str:
            return os.getenv(f"{prefix.upper()}_{key.upper()}", os.getenv(f"{prefix}_{key}", default))

        # Check for provider configs in format: PROVIDER_<id>_<key>
        # E.g., OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.
        provider_mappings = {
            "openai": {"api_key": "OPENAI_API_KEY", "base_url": "OPENAI_BASE_URL", "model": "OPENAI_MODEL"},
            "anthropic": {"api_key": "ANTHROPIC_API_KEY", "model": "ANTHROPIC_MODEL"},
            "together": {"api_key": "TOGETHER_API_KEY", "model": "TOGETHER_MODEL"},
            "groq": {"api_key": "GROQ_API_KEY", "model": "GROQ_MODEL"},
            "deepinfra": {"api_key": "DEEPINFRA_API_KEY", "model": "DEEPINFRA_MODEL"},
            "deepseek": {"api_key": "DEEPSEEK_API_KEY", "base_url": "DEEPSEEK_BASE_URL", "model": "DEEPSEEK_MODEL"},
            "zai": {"api_key": "ZAI_API_KEY", "model": "ZAI_MODEL"},
            "xai": {"api_key": "XAI_API_KEY", "model": "XAI_MODEL"},
            "ollama": {"base_url": "OLLAMA_BASE_URL", "model": "OLLAMA_MODEL"},
            "lmstudio": {"base_url": "LMSTUDIO_BASE_URL", "model": "LMSTUDIO_MODEL"},
            "openrouter": {"api_key": "OPENROUTER_API_KEY", "base_url": "OPENROUTER_BASE_URL", "model": "OPENROUTER_MODEL"},
        }

        for provider_id, env_keys in provider_mappings.items():
            config = {}
            has_config = False

            for config_key, env_var in env_keys.items():
                value = os.getenv(env_var)
                if value:
                    config[config_key] = value
                    has_config = True

            if has_config:
                # Check if explicitly enabled/disabled
                enabled_env = os.getenv(f"{provider_id.upper()}_ENABLED", "true").lower()
                enabled = enabled_env == "true"

                # Use legacy config as fallback for lmstudio
                if provider_id == "lmstudio":
                    if "base_url" not in config:
                        config["base_url"] = self.llm_base_url
                    if "model" not in config:
                        config["model"] = self.llm_model_name

                providers.append(ProviderConfig(
                    provider_id=provider_id,
                    enabled=enabled,
                    config=config,
                    is_default=(provider_id == self.llm_provider)
                ))

        # If no providers found, add legacy config as lmstudio
        if not providers:
            providers.append(ProviderConfig(
                provider_id="lmstudio",
                enabled=True,
                is_default=True,
                config={
                    "base_url": self.llm_base_url,
                    "model": self.llm_model_name,
                }
            ))

        self.llm_providers = providers

    def _load_data_source_configs_from_env(self):
        """Load data source configurations from environment variables"""
        sources = []

        # Email data source
        if os.getenv("EMAIL_IMAP_SERVER"):
            sources.append(DataSourceConfig(
                source_id="email_imap",
                source_type="email",
                enabled=os.getenv("EMAIL_ENABLED", "true").lower() == "true",
                config={
                    "imap_server": os.getenv("EMAIL_IMAP_SERVER"),
                    "imap_port": int(os.getenv("EMAIL_IMAP_PORT", "993")),
                    "username": os.getenv("EMAIL_USERNAME"),
                    "password": os.getenv("EMAIL_PASSWORD"),
                    "use_ssl": os.getenv("EMAIL_USE_SSL", "true").lower() == "true",
                }
            ))

        # Notion data source
        if os.getenv("NOTION_API_KEY"):
            sources.append(DataSourceConfig(
                source_id="notion",
                source_type="notion",
                enabled=os.getenv("NOTION_ENABLED", "true").lower() == "true",
                config={
                    "api_key": os.getenv("NOTION_API_KEY"),
                    "database_id": os.getenv("NOTION_DATABASE_ID"),
                }
            ))

        # GitHub data source
        if os.getenv("GITHUB_TOKEN"):
            sources.append(DataSourceConfig(
                source_id="github",
                source_type="github",
                enabled=os.getenv("GITHUB_ENABLED", "true").lower() == "true",
                config={
                    "token": os.getenv("GITHUB_TOKEN"),
                    "repos": os.getenv("GITHUB_REPOS", "").split(",") if os.getenv("GITHUB_REPOS") else [],
                }
            ))

        self.data_sources = sources

    def get_active_llm_provider(self) -> Optional[ProviderConfig]:
        """Get the active LLM provider configuration"""
        # First try to find one marked as default
        for provider in self.llm_providers:
            if provider.enabled and provider.is_default:
                return provider

        # Otherwise return the first enabled one
        for provider in self.llm_providers:
            if provider.enabled:
                return provider

        return None

    def get_provider_config(self, provider_id: str) -> Optional[ProviderConfig]:
        """Get configuration for a specific provider"""
        for provider in self.llm_providers:
            if provider.provider_id == provider_id:
                return provider
        return None

    def get_data_source_config(self, source_id: str) -> Optional[DataSourceConfig]:
        """Get configuration for a specific data source"""
        for source in self.data_sources:
            if source.source_id == source_id:
                return source
        return None

    # ========== Computed Paths (Environment-Aware) ==========
    @property
    def data_dir(self) -> Path:
        """Data directory based on environment mode."""
        return Path(__file__).parent / "data" / self.env_mode

    @property
    def db_path(self) -> Path:
        """SQLite database path."""
        return self.data_dir / "megpt.db"

    @property
    def providers_db_path(self) -> Path:
        """Provider configuration database path."""
        return self.data_dir / "providers.db"

    @property
    def backups_dir(self) -> Path:
        """Backups directory."""
        return self.data_dir / "backups"

    @property
    def qdrant_collection(self) -> str:
        """Qdrant collection name based on environment."""
        return f"megpt_memories_{self.env_mode}"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.env_mode == "prod"

    def validate(self) -> None:
        """Validate critical configuration on startup."""
        if self.env_mode not in ("dev", "prod"):
            raise ValueError(f"ENV_MODE must be 'dev' or 'prod', got: {self.env_mode}")

        # Validate that at least one LLM provider is configured
        active_provider = self.get_active_llm_provider()
        if not active_provider:
            logger.warning("No LLM provider configured. Set up a provider in the UI or via environment variables.")

        # Production security requirements
        if self.is_production:
            if self.api_key is None:
                raise ValueError(
                    "SECURITY: API_KEY is required in production mode. "
                    "Set the API_KEY environment variable."
                )
            if self.admin_api_key is None:
                logger.warning(
                    "SECURITY: ADMIN_API_KEY not set. Admin operations will use regular API key. "
                    "For better security, set ADMIN_API_KEY environment variable."
                )
                self.admin_api_key = self.api_key

        # Ensure data directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)

        env_badge = "🔴 PRODUCTION" if self.is_production else "🟢 DEVELOPMENT"
        active = active_provider.provider_id if active_provider else "none"
        print(f"✓ Config loaded [{env_badge}]")
        print(f"  Active LLM Provider: {active}")
        print(f"  Data: {self.data_dir}")
        print(f"  Collection: {self.qdrant_collection}")


# Global config instance
config = Config()


def save_provider_config(provider_id: str, provider_config: Dict[str, Any]) -> bool:
    """Save provider configuration to the database"""
    import sqlite3

    config.providers_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_configs (
            provider_id TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        INSERT OR REPLACE INTO provider_configs (provider_id, config, enabled, is_default, updated_at)
        VALUES (?, ?, 1, 0, CURRENT_TIMESTAMP)
    """, (provider_id, json.dumps(provider_config)))

    conn.commit()
    conn.close()
    return True


def load_provider_config(provider_id: str) -> Optional[Dict[str, Any]]:
    """Load provider configuration from the database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return None

    conn = sqlite3.connect(config.providers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT config, enabled FROM provider_configs WHERE provider_id = ?",
        (provider_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {"config": json.loads(row["config"]), "enabled": bool(row["enabled"])}
    return None


def get_all_provider_configs() -> Dict[str, Dict[str, Any]]:
    """Get all provider configurations from database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return {}

    conn = sqlite3.connect(config.providers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT provider_id, config, enabled, is_default FROM provider_configs")

    result = {}
    for row in cursor.fetchall():
        result[row["provider_id"]] = {
            "config": json.loads(row["config"]),
            "enabled": bool(row["enabled"]),
            "is_default": bool(row["is_default"]),
        }

    conn.close()
    return result


def save_data_source_config(source_id: str, source_type: str, source_config: Dict[str, Any]) -> bool:
    """Save data source configuration to the database"""
    import sqlite3

    config.providers_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS data_source_configs (
            source_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            sync_interval INTEGER,
            last_sync TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        INSERT OR REPLACE INTO data_source_configs (source_id, source_type, config, enabled, updated_at)
        VALUES (?, ?, ?, 1, CURRENT_TIMESTAMP)
    """, (source_id, source_type, json.dumps(source_config)))

    conn.commit()
    conn.close()
    return True


def get_all_data_source_configs() -> Dict[str, Dict[str, Any]]:
    """Get all data source configurations from database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return {}

    conn = sqlite3.connect(config.providers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("SELECT source_id, source_type, config, enabled, sync_interval, last_sync FROM data_source_configs")

    result = {}
    for row in cursor.fetchall():
        result[row["source_id"]] = {
            "source_type": row["source_type"],
            "config": json.loads(row["config"]),
            "enabled": bool(row["enabled"]),
            "sync_interval": row["sync_interval"],
            "last_sync": row["last_sync"],
        }

    conn.close()
    return result
