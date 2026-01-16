"""
Configuration loader for the Local Memory Agent.
Loads environment variables with sensible defaults for local development.
Phase 4: Added ENV_MODE, data paths, and backup configuration.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()


@dataclass
class Config:
    """Application configuration with typed fields and defaults."""
    
    # ========== Environment Mode ==========
    env_mode: str = os.getenv("ENV_MODE", "dev")  # "dev" or "prod"
    
    # ========== LLM Settings ==========
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "lm-studio")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "qwen2.5-vl-30b-instruct")
    
    # ========== Embedder Settings ==========
    embedder_base_url: str = os.getenv("EMBEDDER_BASE_URL", "http://localhost:1234/v1")
    embedder_api_key: str = os.getenv("EMBEDDER_API_KEY", "lm-studio")
    embedder_model_name: str = os.getenv("EMBEDDER_MODEL_NAME", "text-embedding-bge-m3")
    
    # ========== Qdrant Settings ==========
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    
    # ========== Feature Flags ==========
    enable_web_search: bool = os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"
    
    # ========== User Identity ==========
    user_id: str = os.getenv("USER_ID", "default_user")
    
    # ========== Backup Settings ==========
    backup_interval_hours: int = int(os.getenv("BACKUP_INTERVAL_HOURS", "0"))  # 0 = disabled
    backup_retention_count: int = int(os.getenv("BACKUP_RETENTION_COUNT", "10"))
    auto_backup_before_restore: bool = os.getenv("AUTO_BACKUP_BEFORE_RESTORE", "true").lower() == "true"
    
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
        if not self.llm_base_url:
            raise ValueError("LLM_BASE_URL is required")
        if not self.embedder_base_url:
            raise ValueError("EMBEDDER_BASE_URL is required for Mem0")
        if self.env_mode not in ("dev", "prod"):
            raise ValueError(f"ENV_MODE must be 'dev' or 'prod', got: {self.env_mode}")
        
        # Ensure data directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        
        env_badge = "🔴 PRODUCTION" if self.is_production else "🟢 DEVELOPMENT"
        print(f"✓ Config loaded [{env_badge}]")
        print(f"  LLM: {self.llm_base_url}")
        print(f"  Data: {self.data_dir}")
        print(f"  Collection: {self.qdrant_collection}")


# Global config instance
config = Config()
