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
class ContextConfig:
    """Configuration for context retrieval and memory limits"""
    # Score thresholds for semantic search (lower = more results)
    fact_score_threshold: float = 0.4
    email_fact_score_threshold: float = 0.4
    document_fact_score_threshold: float = 0.35

    # Limits for different intent types
    recent_messages_limit_overview: int = 2
    recent_messages_limit_followup: int = 5
    recent_messages_limit_general: int = 3
    recent_messages_limit_default: int = 15

    # Search limits
    fact_search_limit: int = 10
    email_search_limit: int = 10
    document_search_limit: int = 10
    document_scroll_limit: int = 500
    scroll_limit: int = 100

    # Summary limits
    summary_recent_limit: int = 20
    summary_context_limit: int = 10


@dataclass
class TokenConfig:
    """Configuration for token counting and context window management"""
    # Approximate tokens per character for estimation (conservative)
    tokens_per_char: float = 0.3
    # Target context usage (leave room for response)
    target_context_ratio: float = 0.7
    # Maximum tokens for system context
    max_system_tokens: int = 2000


@dataclass
class EmailConfig:
    """Configuration for email integration and processing"""
    # Classification model (can be different from chat model)
    classification_provider_id: str = "lmstudio"  # provider_id to use for email classification
    classification_model: str = ""  # Empty = use provider's default model

    # Sync settings
    initial_sync_months: int = 2  # Number of months to sync initially
    incremental_sync_interval_minutes: int = 120  # 2 hours

    # Processing options
    auto_extract_facts: bool = True  # Automatically extract facts to Qdrant
    auto_create_reminders: bool = True  # Automatically create reminders from deadlines


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

    # ========== Context Configuration ==========
    context: ContextConfig = field(default_factory=ContextConfig)
    tokens: TokenConfig = field(default_factory=TokenConfig)

    # ========== Email Configuration ==========
    email: EmailConfig = field(default_factory=EmailConfig)

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

        env_badge = "[PRODUCTION]" if self.is_production else "[DEVELOPMENT]"
        active = active_provider.provider_id if active_provider else "none"
        print(f"[OK] Config loaded {env_badge}")
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


def save_embedding_provider_config(provider_id: str, provider_config: Dict[str, Any]) -> bool:
    """Save embedding provider configuration to the database"""
    import sqlite3

    config.providers_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS embedding_provider_configs (
            provider_id TEXT PRIMARY KEY,
            config TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            is_default INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Unset previous default if setting new default
    if provider_config.get("is_default"):
        conn.execute("UPDATE embedding_provider_configs SET is_default = 0")

    conn.execute("""
        INSERT OR REPLACE INTO embedding_provider_configs (provider_id, config, enabled, is_default, updated_at)
        VALUES (?, ?, COALESCE((SELECT enabled FROM embedding_provider_configs WHERE provider_id = ?), 1), ?, CURRENT_TIMESTAMP)
    """, (provider_id, json.dumps(provider_config), provider_id, 1 if provider_config.get("is_default") else 0))

    conn.commit()
    conn.close()
    return True


def init_default_embedding_provider():
    """Initialize default embedding provider if none exists"""
    import sqlite3

    if not config.providers_db_path.exists():
        config.providers_db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        conn = sqlite3.connect(config.providers_db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_provider_configs (
                provider_id TEXT PRIMARY KEY,
                config TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                is_default INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check if any embedding provider exists
        cursor = conn.execute("SELECT COUNT(*) as count FROM embedding_provider_configs")
        row = cursor.fetchone()

        if row and row[0] == 0:
            # No embedding provider configured, set up LM Studio as default
            default_config = {
                "base_url": config.embedder_base_url,  # Use env var as default
                "model": "text-embedding-bge-m3",
                "is_default": True,
            }
            conn.execute("""
                INSERT INTO embedding_provider_configs (provider_id, config, enabled, is_default)
                VALUES (?, ?, 1, 1)
            """, ("lmstudio", json.dumps(default_config)))
            conn.commit()
            logger.info("Initialized default embedding provider: LM Studio with text-embedding-bge-m3")

        conn.close()
    except sqlite3.OperationalError:
        pass  # Will be created on first save


def load_embedding_provider_config(provider_id: str) -> Optional[Dict[str, Any]]:
    """Load embedding provider configuration from the database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return None

    conn = sqlite3.connect(config.providers_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute(
        "SELECT config, enabled, is_default FROM embedding_provider_configs WHERE provider_id = ?",
        (provider_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if row:
        return {
            "config": json.loads(row["config"]),
            "enabled": bool(row["enabled"]),
            "is_default": bool(row["is_default"])
        }
    return None


def get_active_embedding_provider() -> Optional[Dict[str, Any]]:
    """Get the active embedding provider from database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return None

    try:
        conn = sqlite3.connect(config.providers_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("""
            SELECT provider_id, config, enabled
            FROM embedding_provider_configs
            WHERE is_default = 1 AND enabled = 1
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "provider_id": row["provider_id"],
                "config": json.loads(row["config"]),
                "enabled": bool(row["enabled"])
            }
        return None
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return None


def get_all_embedding_provider_configs() -> Dict[str, Dict[str, Any]]:
    """Get all embedding provider configurations from database"""
    import sqlite3

    if not config.providers_db_path.exists():
        return {}

    try:
        conn = sqlite3.connect(config.providers_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT provider_id, config, enabled, is_default FROM embedding_provider_configs")

        result = {}
        for row in cursor.fetchall():
            result[row["provider_id"]] = {
                "config": json.loads(row["config"]),
                "enabled": bool(row["enabled"]),
                "is_default": bool(row["is_default"]),
            }

        conn.close()
        return result
    except sqlite3.OperationalError:
        # Table doesn't exist yet
        return {}


# Initialize default embedding provider on module load
init_default_embedding_provider()


# ========== Email Classification Config ==========

def save_email_classification_config(provider_id: str, model: str) -> bool:
    """Save email classification provider configuration to the database"""
    import sqlite3

    config.providers_db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(config.providers_db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_classification_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            provider_id TEXT NOT NULL,
            model TEXT,
            enabled INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        INSERT OR REPLACE INTO email_classification_config (id, provider_id, model, enabled, updated_at)
        VALUES (1, ?, ?, 1, CURRENT_TIMESTAMP)
    """, (provider_id, model))

    conn.commit()
    conn.close()
    return True


def get_email_classification_config() -> Dict[str, Any]:
    """Get the email classification provider configuration from database"""
    import sqlite3

    if not config.providers_db_path.exists():
        # Return default from Config
        return {
            "provider_id": config.email.classification_provider_id,
            "model": config.email.classification_model or config.llm_model_name,
            "enabled": True,
        }

    try:
        conn = sqlite3.connect(config.providers_db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT provider_id, model, enabled FROM email_classification_config WHERE id = 1")
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "provider_id": row["provider_id"],
                "model": row["model"] or config.llm_model_name,
                "enabled": bool(row["enabled"]),
            }
    except sqlite3.OperationalError:
        pass  # Table doesn't exist yet

    # Fallback to config defaults
    return {
        "provider_id": config.email.classification_provider_id,
        "model": config.email.classification_model or config.llm_model_name,
        "enabled": True,
    }


def get_email_classification_llm() -> tuple[str, str, str]:
    """
    Get the LLM config for email classification.
    Returns (base_url, api_key, model) from the configured provider.
    """
    from utils.llm_factory import _normalize_base_url

    classification_config = get_email_classification_config()

    if not classification_config.get("enabled"):
        # Fall back to main LLM
        return get_llm_config()

    provider_id = classification_config["provider_id"]
    model = classification_config["model"]

    # Get provider config from database
    provider_config = load_provider_config(provider_id)

    if provider_config:
        base_url = provider_config["config"].get("base_url", config.llm_base_url)
        api_key = provider_config["config"].get("api_key", config.llm_api_key)
    else:
        # Try environment variables
        env_prefix = provider_id.upper()
        base_url = os.getenv(f"{env_prefix}_BASE_URL", config.llm_base_url)
        api_key = os.getenv(f"{env_prefix}_API_KEY", config.llm_api_key)

    # Normalize and add /v1
    base_url = _normalize_base_url(base_url)
    return (f"{base_url}/v1", api_key, model)


# ========== Token Counting Utilities ==========
def estimate_tokens(text: str) -> int:
    """
    Estimate token count for a text string.
    Uses a conservative approximation: ~0.3 tokens per character for English text.
    This is a rough estimate - actual token count depends on the model's tokenizer.
    """
    if not text:
        return 0
    return int(len(text) * config.tokens.tokens_per_char)


def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """
    Truncate text to fit within a token limit.
    Preserves the beginning of the text (most important for context).
    """
    if not text:
        return text

    estimated = estimate_tokens(text)
    if estimated <= max_tokens:
        return text

    # Calculate how many characters to keep
    char_limit = int(max_tokens / config.tokens.tokens_per_char)
    truncated = text[:char_limit]

    # Try to end at a sentence boundary
    last_period = truncated.rfind(".")
    last_newline = truncated.rfind("\n")
    best_boundary = max(last_period, last_newline)

    if best_boundary > char_limit // 2:  # Only truncate at boundary if it's not too early
        return text[:best_boundary + 1]

    return truncated


def get_context_budget() -> int:
    """
    Get the available token budget for context.
    Returns the number of tokens reserved for system context, leaving room for user input and response.
    """
    return int(config.context_window_size * config.tokens.target_context_ratio)

