"""
Plugin bootstrap entry point for the ForgeAI Git Plugin.
"""

import logging
from forge_core.kernel.service_registry import ServiceRegistry
from forge_core.plugin_manager.interface import Plugin
from .service import GitService, ForgeAIGit

logger = logging.getLogger("ForgeAI.Plugins.Git")


class GitPlugin(Plugin):
    """
    Plugin adapter that registers the GitService into the system service registry.
    """

    @property
    def name(self) -> str:
        return "git"

    @property
    def version(self) -> str:
        return "1.0.0"

    def initialize(self, registry: ServiceRegistry) -> None:
        logger.info("Initializing GitPlugin...")
        self._service = ForgeAIGit(registry)
        registry.register(GitService, self._service)  # type: ignore[type-abstract]
        logger.info("GitPlugin registered under GitService interface.")

    def shutdown(self) -> None:
        logger.info("GitPlugin shutting down.")
