"""
Plugin bootstrap entry point for the ForgeAI Tester Plugin.
"""

import logging
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import TesterService, ForgeAITester

logger = logging.getLogger("ForgeAI.Plugins.Tester")


class TesterPlugin(Plugin):
    """
    Plugin adapter registering the TesterService into the system registry.
    """

    @property
    def name(self) -> str:
        return "tester"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing TesterPlugin...")
        self._service = ForgeAITester(registry)
        registry.register(TesterService, self._service)  # type: ignore[type-abstract]
        logger.info("TesterPlugin registered under TesterService interface.")

    def shutdown(self) -> None:
        logger.info("TesterPlugin shutting down.")
