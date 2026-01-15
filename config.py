"""
Configuration loader for the Local Memory Agent.
Loads environment variables with sensible defaults for local development.
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

# Load .env file
load_dotenv()


@dataclass
class Config:
    """Application configuration with typed fields and defaults."""
    
    # LLM Settings
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
    llm_api_key: str = os.getenv("LLM_API_KEY", "lm-studio")
    llm_model_name: str = os.getenv("LLM_MODEL_NAME", "qwen2.5-vl-30b-instruct")
    
    # Embedder Settings (separate from LLM for Mem0)
    embedder_base_url: str = os.getenv("EMBEDDER_BASE_URL", "http://localhost:1234/v1")
    embedder_api_key: str = os.getenv("EMBEDDER_API_KEY", "lm-studio")
    embedder_model_name: str = os.getenv("EMBEDDER_MODEL_NAME", "text-embedding-bge-m3")
    
    # Qdrant Settings
    qdrant_host: str = os.getenv("QDRANT_HOST", "localhost")
    qdrant_port: int = int(os.getenv("QDRANT_PORT", "6333"))
    
    # Feature Flags
    enable_web_search: bool = os.getenv("ENABLE_WEB_SEARCH", "true").lower() == "true"
    
    # User Identity
    user_id: str = os.getenv("USER_ID", "default_user")
    
    def validate(self) -> None:
        """Validate critical configuration on startup."""
        if not self.llm_base_url:
            raise ValueError("LLM_BASE_URL is required")
        if not self.embedder_base_url:
            raise ValueError("EMBEDDER_BASE_URL is required for Mem0")
        print(f"✓ Config loaded: LLM={self.llm_base_url}, Embedder={self.embedder_model_name}")


# Global config instance
config = Config()
