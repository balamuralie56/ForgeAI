"""
Plugin bootstrap entry point for the ForgeAI Assistant Plugin.
"""

import logging
from typing import Optional

from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin

from .service import AssistantService, ForgeAIAssistant

logger = logging.getLogger("ForgeAI.Plugins.Assistant")


class AssistantPlugin(Plugin):
    """
    Plugin adapter registering the AssistantService into the system registry.
    """

    def __init__(self) -> None:
        self._service: Optional[ForgeAIAssistant] = None

    @property
    def name(self) -> str:
        return "assistant"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing AssistantPlugin...")
        service = ForgeAIAssistant(registry)
        service.initialize()
        self._service = service
        registry.register(AssistantService, service)  # type: ignore[type-abstract]
        logger.info("AssistantPlugin registered under AssistantService interface.")

    def shutdown(self) -> None:
        logger.info("AssistantPlugin shutting down.")
        if self._service is not None:
            self._service.shutdown()
            self._service = None
