"""
Plugin bootstrap entry point for the ForgeAI Documentation Plugin.
"""

import logging
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import DocumentationService, ForgeAIDocumentation

logger = logging.getLogger("ForgeAI.Plugins.Documentation")


class DocumentationPlugin(Plugin):
    """
    Plugin adapter registering the DocumentationService into the system registry.
    """

    @property
    def name(self) -> str:
        return "documentation"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing DocumentationPlugin...")
        self._service = ForgeAIDocumentation(registry)
        registry.register(DocumentationService, self._service)  # type: ignore[type-abstract]
        logger.info(
            "DocumentationPlugin registered under DocumentationService interface."
        )

    def shutdown(self) -> None:
        logger.info("DocumentationPlugin shutting down.")
