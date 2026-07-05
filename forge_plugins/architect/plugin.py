"""
Plugin bootstrap entry point for the ForgeAI Architect Plugin.
"""

import logging
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import ArchitectService, ForgeAIArchitect

logger = logging.getLogger("ForgeAI.Plugins.Architect")


class ArchitectPlugin(Plugin):
    """
    Plugin adapter registering the ArchitectService into the system registry.
    """

    @property
    def name(self) -> str:
        return "architect"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing ArchitectPlugin...")
        self._service = ForgeAIArchitect(registry)
        registry.register(ArchitectService, self._service)  # type: ignore[type-abstract]
        logger.info("ArchitectPlugin registered under ArchitectService interface.")

    def shutdown(self) -> None:
        logger.info("ArchitectPlugin shutting down.")
