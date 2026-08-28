"""
Plugin adapter bootstrap registering ReviewerService inside the dependency container.
"""

import logging
from typing import List
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import ReviewerService, ForgeAIReviewer

logger = logging.getLogger("ForgeAI.Plugins.Reviewer")


class ReviewerPlugin(Plugin):
    """Plugin class registering the ReviewerService."""

    @property
    def name(self) -> str:
        return "reviewer"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> List[str]:
        """Exposes the supported capabilities of the reviewer plugin."""
        return [
            "code_smell_detection",
            "solid_scoring",
            "static_analysis",
            "review_report",
        ]

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing ReviewerPlugin...")
        self._service = ForgeAIReviewer(registry)

        registry.register(ReviewerService, self._service)  # type: ignore[type-abstract]

        logger.info("ReviewerPlugin registered under ReviewerService interface.")

    def shutdown(self) -> None:
        logger.info("ReviewerPlugin shutting down.")
