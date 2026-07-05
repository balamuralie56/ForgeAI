"""
Plugin bootstrap entry point for the ForgeAI Planner Plugin.
"""

import logging
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import PlannerService, ForgeAIPlanner

logger = logging.getLogger("ForgeAI.Plugins.Planner")


class PlannerPlugin(Plugin):
    """
    Plugin adapter registering the PlannerService into the system registry.
    """

    @property
    def name(self) -> str:
        return "planner"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing PlannerPlugin...")
        self._service = ForgeAIPlanner(registry)
        registry.register(PlannerService, self._service)  # type: ignore[type-abstract]
        logger.info("PlannerPlugin registered under PlannerService interface.")

    def shutdown(self) -> None:
        logger.info("PlannerPlugin shutting down.")
