"""
Plugin adapter bootstrap registering SecurityService inside the dependency container.
"""

import logging
from typing import List
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import SecurityService, ForgeAISecurity

logger = logging.getLogger("ForgeAI.Plugins.Security")


class SecurityPlugin(Plugin):
    """
    Plugin class registering the SecurityService.
    """

    @property
    def name(self) -> str:
        return "security"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> List[str]:
        """Exposes the supported capabilities of the security plugin."""
        return [
            "secret_scan",
            "dependency_scan",
            "static_analysis",
            "license_check",
            "security_report",
            "sarif_export",
        ]

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing SecurityPlugin...")
        self._service = ForgeAISecurity(registry)

        # Register the service under the abstract interface
        registry.register(SecurityService, self._service)  # type: ignore[type-abstract]

        logger.info("SecurityPlugin registered under SecurityService interface.")

    def shutdown(self) -> None:
        logger.info("SecurityPlugin shutting down.")
