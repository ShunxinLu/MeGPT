"""
Provider Registry
Manages registration and instantiation of providers
"""

from typing import Dict, Type, Any, Optional, List
import logging
from .llm_provider import LLMProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for LLM providers and data sources.
    Allows dynamic registration and instantiation.
    """

    def __init__(self):
        self._llm_providers: Dict[str, Type[LLMProvider]] = {}
        self._data_sources: Dict[str, Type] = {}
        self._active_llm: Optional[LLMProvider] = None
        self._active_data_sources: Dict[str, Any] = {}

    def register_llm_provider(
        self,
        provider_id: str,
        provider_class: Type[LLMProvider],
        overwrite: bool = False,
    ):
        """Register an LLM provider class"""
        if provider_id in self._llm_providers and not overwrite:
            raise ValueError(f"Provider {provider_id} already registered")

        self._llm_providers[provider_id] = provider_class
        logger.info(f"Registered LLM provider: {provider_id}")

    def register_data_source(
        self,
        source_id: str,
        source_class: Type,
        overwrite: bool = False,
    ):
        """Register a data source class"""
        if source_id in self._data_sources and not overwrite:
            raise ValueError(f"Data source {source_id} already registered")

        self._data_sources[source_id] = source_class
        logger.info(f"Registered data source: {source_id}")

    def get_llm_provider(self, provider_id: str) -> Optional[Type[LLMProvider]]:
        """Get an LLM provider class by ID"""
        return self._llm_providers.get(provider_id)

    def get_data_source(self, source_id: str) -> Optional[Type]:
        """Get a data source class by ID"""
        return self._data_sources.get(source_id)

    def list_llm_providers(self) -> List[str]:
        """List all registered LLM provider IDs"""
        return list(self._llm_providers.keys())

    def list_data_sources(self) -> List[str]:
        """List all registered data source IDs"""
        return list(self._data_sources.keys())

    def create_llm_provider(
        self, provider_id: str, config: Dict[str, Any]
    ) -> LLMProvider:
        """Create an instance of an LLM provider"""
        provider_class = self.get_llm_provider(provider_id)
        if not provider_class:
            raise ValueError(f"Unknown provider: {provider_id}")

        return provider_class(config)

    def create_data_source(self, source_id: str, config: Dict[str, Any]):
        """Create an instance of a data source"""
        source_class = self.get_data_source(source_id)
        if not source_class:
            raise ValueError(f"Unknown data source: {source_id}")

        return source_class(config)

    def set_active_llm(self, provider: LLMProvider):
        """Set the active LLM provider"""
        self._active_llm = provider
        logger.info(f"Set active LLM: {provider.provider_id}")

    def get_active_llm(self) -> Optional[LLMProvider]:
        """Get the active LLM provider"""
        return self._active_llm

    def add_active_data_source(self, source_id: str, instance: Any):
        """Add an active data source"""
        self._active_data_sources[source_id] = instance
        logger.info(f"Added active data source: {source_id}")

    def get_active_data_source(self, source_id: str) -> Optional[Any]:
        """Get an active data source"""
        return self._active_data_sources.get(source_id)

    def get_all_active_data_sources(self) -> Dict[str, Any]:
        """Get all active data sources"""
        return self._active_data_sources.copy()

    def get_llm_providers_info(self) -> List[Dict[str, Any]]:
        """Get info about all registered LLM providers"""
        info = []
        for provider_id, provider_class in self._llm_providers.items():
            # Create a dummy instance to get info
            try:
                dummy = provider_class({})
                info.append(dummy.get_provider_info())
            except Exception as e:
                logger.warning(f"Could not get info for {provider_id}: {e}")
                info.append({
                    "id": provider_id,
                    "name": provider_id,
                    "description": "Error loading provider info",
                    "error": str(e),
                })
        return info


# Global registry instance
provider_registry = ProviderRegistry()
