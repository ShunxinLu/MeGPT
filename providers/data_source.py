"""
Data Source Plugin Interface
Defines the contract for all data source plugins
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class DataSourceType(Enum):
    """Types of data sources"""
    EMAIL = "email"
    CALENDAR = "calendar"
    FILE_SYSTEM = "file_system"
    DATABASE = "database"
    NOTION = "notion"
    GITHUB = "github"
    DISCORD = "discord"
    SLACK = "slack"
    WEB = "web"
    CUSTOM = "custom"


class SyncStatus(Enum):
    """Sync status for data sources"""
    IDLE = "idle"
    SYNCING = "syncing"
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


@dataclass
class DataItem:
    """Standardized data item from any source"""
    id: str
    source_type: DataSourceType
    source_id: str
    title: str
    content: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    url: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def to_searchable_text(self) -> str:
        """Convert to searchable text format"""
        parts = [f"Title: {self.title}", f"Content: {self.content}"]
        if self.author:
            parts.append(f"Author: {self.author}")
        if self.tags:
            parts.append(f"Tags: {', '.join(self.tags)}")
        return "\n".join(parts)


@dataclass
class SyncResult:
    """Result of a sync operation"""
    status: SyncStatus
    items_added: int = 0
    items_updated: int = 0
    items_removed: int = 0
    error: Optional[str] = None
    last_sync: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataSourceConfig:
    """Configuration for a data source"""
    source_id: str
    source_type: DataSourceType
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    sync_interval: Optional[int] = None  # minutes
    last_sync: Optional[datetime] = None


class DataSource(ABC):
    """
    Base class for all data source plugins.
    Implement this interface to add a new data source.
    """

    # Data source metadata
    source_id: str = "base"
    source_name: str = "Base Data Source"
    source_type: DataSourceType = DataSourceType.CUSTOM
    description: str = "Base data source interface"

    # Configuration schema (for UI validation)
    config_schema: Dict[str, Any] = {}

    # Capabilities
    supports_streaming: bool = False
    supports_incremental_sync: bool = False
    supports_webhooks: bool = False

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._validate_config()

    def _validate_config(self):
        """Validate data source configuration"""
        required_keys = self.config_schema.get("required", [])
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"Missing required config key: {key}")

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the data source.
        Should validate credentials and connectivity.

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    async def sync(self, since: Optional[datetime] = None) -> SyncResult:
        """
        Sync data from the source.

        Args:
            since: Only sync items modified after this time (for incremental sync)

        Returns:
            SyncResult with status and counts
        """
        pass

    async def stream_items(
        self, since: Optional[datetime] = None
    ) -> AsyncIterator[DataItem]:
        """
        Stream items from the source (if supported).

        Args:
            since: Only stream items modified after this time

        Yields:
            DataItem instances
        """
        raise NotImplementedError("Streaming not supported by this source")

    @abstractmethod
    async def search(self, query: str, limit: int = 10) -> List[DataItem]:
        """
        Search items in the data source.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of matching DataItems
        """
        pass

    @abstractmethod
    async def get_item(self, item_id: str) -> Optional[DataItem]:
        """
        Get a specific item by ID.

        Args:
            item_id: Unique identifier for the item

        Returns:
            DataItem if found, None otherwise
        """
        pass

    async def disconnect(self):
        """Clean up connections"""
        pass

    def get_source_info(self) -> Dict[str, Any]:
        """Get data source information for UI display"""
        return {
            "id": self.source_id,
            "name": self.source_name,
            "type": self.source_type.value,
            "description": self.description,
            "config_schema": self.config_schema,
            "supports_streaming": self.supports_streaming,
            "supports_incremental_sync": self.supports_incremental_sync,
            "supports_webhooks": self.supports_webhooks,
        }

    async def validate_connection(self) -> bool:
        """Validate that the data source is accessible"""
        try:
            return await self.connect()
        except Exception:
            return False
