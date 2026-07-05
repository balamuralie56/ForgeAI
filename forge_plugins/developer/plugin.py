"""
Plugin bootstrap entry point for the ForgeAI Developer Plugin.
"""

import logging

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import DeveloperService, ForgeAIDeveloper

logger = logging.getLogger("ForgeAI.Plugins.Developer")


class DeveloperPlugin(Plugin):
    """
    Plugin adapter registering the DeveloperService into the system registry.
    """

    @property
    def name(self) -> str:
        return "developer"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing DeveloperPlugin...")
        self._service = ForgeAIDeveloper(registry)
        registry.register(DeveloperService, self._service)  # type: ignore[type-abstract]
        logger.info("DeveloperPlugin registered under DeveloperService interface.")

    def shutdown(self) -> None:
        logger.info("DeveloperPlugin shutting down.")
