"""
Model Router implementation for ForgeAI.
Acts as a mediator resolving ModelProviders and routing LLM generation calls.
"""

import logging
from typing import Any, Dict, List, Optional

from forge_core.configuration.service import ConfigurationService

from .exceptions import ProviderNotFoundError
from .providers import OllamaProvider, OpenAICompatibleProvider
from .service import ModelProvider, ModelResponse, ModelRouterService

logger = logging.getLogger("ForgeAI.ModelRouter")


class ModelRouter(ModelRouterService):
    """
    Concrete implementation of the ModelRouterService.
    Registers multiple providers and routes requests to the configured/requested targets.
    """

    def __init__(self, config_service: ConfigurationService) -> None:
        """
        Initializes the Model Router and registers default providers based on configuration.

        Args:
            config_service (ConfigurationService): The system configuration provider.
        """
        self._config_service: ConfigurationService = config_service
        self._providers: Dict[str, ModelProvider] = {}

        # Load and bootstrap default provider from settings
        self._bootstrap_default_provider()

    def _bootstrap_default_provider(self) -> None:
        """Instantiates and registers the default model provider from config."""
        settings = self._config_service.get_model_settings()
        provider_name = settings.provider.lower()
        base_url = settings.base_url
        default_model = settings.default_model

        logger.info(
            f"Bootstrapping default model provider: '{provider_name}' "
            f"(Model: '{default_model}', URL: '{base_url}')"
        )

        request_timeout = settings.request_timeout

        provider: ModelProvider
        if provider_name == "ollama":
            provider = OllamaProvider(
                base_url=base_url,
                default_model=default_model,
                timeout=request_timeout,
                keep_alive=settings.keep_alive,
            )
        else:
            # Fallback/default to OpenAI-compatible for any other configured provider (LM Studio, vLLM, etc.)
            provider = OpenAICompatibleProvider(
                base_url=base_url,
                default_model=default_model,
                timeout=request_timeout,
            )
            # Ensure custom provider names map correctly to the class name property
            provider._name = provider_name  # type: ignore

        self.register_provider(provider)

    def register_provider(self, provider: ModelProvider) -> None:
        """
        Registers a new model provider.

        Args:
            provider (ModelProvider): The provider client implementation.
        """
        name = provider.name.lower()
        self._providers[name] = provider
        logger.info(f"Registered model provider: '{name}'")

    def get_provider(self, name: str) -> ModelProvider:
        """
        Resolves a model provider by name.

        Args:
            name (str): The provider name (e.g. 'ollama').

        Returns:
            ModelProvider: The registered provider client.

        Raises:
            ProviderNotFoundError: If the requested provider has not been registered.
        """
        name_lower = name.lower()
        if name_lower not in self._providers:
            raise ProviderNotFoundError(
                f"Model provider '{name}' has not been registered."
            )
        return self._providers[name_lower]

    def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        settings = self._config_service.get_model_settings()
        target_provider_name = (provider or settings.provider).lower()

        # Resolve target provider
        client = self.get_provider(target_provider_name)

        # Merge configuration defaults with explicitly passed overrides
        inference_params = {
            "temperature": kwargs.get("temperature", settings.temperature),
            "max_tokens": kwargs.get("max_tokens", settings.max_tokens),
            **kwargs,
        }

        logger.debug(
            f"Routing text generation to provider '{target_provider_name}' (Model: {model or 'default'})"
        )
        return client.generate(prompt=prompt, model=model, **inference_params)

    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> ModelResponse:
        settings = self._config_service.get_model_settings()
        target_provider_name = (provider or settings.provider).lower()

        client = self.get_provider(target_provider_name)

        inference_params = {
            "temperature": kwargs.get("temperature", settings.temperature),
            "max_tokens": kwargs.get("max_tokens", settings.max_tokens),
            **kwargs,
        }

        logger.debug(
            f"Routing chat generation to provider '{target_provider_name}' (Model: {model or 'default'})"
        )
        return client.generate_chat(messages=messages, model=model, **inference_params)
