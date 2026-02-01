"""Shared pytest fixtures for MeGPT tests."""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def mock_env_vars():
    """Mock environment variables for testing."""
    with patch.dict(
        os.environ,
        {
            "LLM_BASE_URL": "http://localhost:1234/v1",
            "LLM_MODEL_NAME": "test-model",
            "EMBEDDER_MODEL_NAME": "test-embedder",
            "QDRANT_HOST": "localhost:6333",
            "USER_ID": "test_user",
            "OPENAI_API_KEY": "test_key",
            "ANTHROPIC_API_KEY": "test_key",
            "GROQ_API_KEY": "test_key",
            "GEMINI_API_KEY": "test_key",
            "PERPLEXITY_API_KEY": "test_key",
        },
        clear=True,
    ):
        yield


@pytest.fixture
def mock_config(mock_env_vars):
    """Mock the config module with test settings."""
    # Import after patching environment
    from config import Config

    # Create a test config instance
    test_config = Config()

    # Patch the config module
    with patch("config.config", test_config):
        yield test_config


@pytest.fixture
def mock_database():
    """Mock database connections and operations."""
    with (
        patch("database.sqlite3") as mock_sqlite,
        patch("tools.memory_tool.QdrantClient") as mock_qdrant,
        patch("tools.memory_tool._qdrant_client", None),  # Reset singleton
        patch("tools.memory_tool._qdrant_last_health_check", 0),
    ):
        # Setup mock SQLite connection
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_sqlite.connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock execute to return cursor, and cursor.fetchone for WAL check
        mock_conn.execute = Mock(return_value=mock_cursor)
        mock_cursor.fetchone.return_value = ("wal",)

        # Mock commit, rollback, close (do nothing)
        mock_conn.commit = Mock()
        mock_conn.rollback = Mock()
        mock_conn.close = Mock()

        # Setup mock Qdrant client
        mock_qdrant_instance = Mock()
        mock_qdrant.return_value = mock_qdrant_instance

        yield {
            "sqlite": mock_sqlite,
            "qdrant": mock_qdrant,
            "connection": mock_conn,
            "cursor": mock_cursor,
            "qdrant_instance": mock_qdrant_instance,
        }


@pytest.fixture
def mock_llm_factory():
    """Mock LLM factory for testing."""
    with patch("utils.llm_factory.create_llm_client") as mock_create_llm:
        mock_llm = Mock()
        mock_create_llm.return_value = mock_llm
        yield mock_llm


@pytest.fixture
def test_user_id():
    """Return a test user ID for user-related tests."""
    return "test_user_123"


@pytest.fixture(autouse=True)
def cleanup_imports():
    """Clean up module imports between tests to avoid state leakage."""
    modules_to_clean = ["config", "database", "server", "agent_graph"]
    original_modules = {}

    for module_name in modules_to_clean:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]
            del sys.modules[module_name]

    yield

    # Restore original modules
    for module_name, module in original_modules.items():
        sys.modules[module_name] = module
