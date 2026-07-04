"""
Service interfaces for the ForgeAI Model Router.
Allows decoupling code from concrete LLM provider APIs (e.g. Ollama, OpenAI).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ModelResponse:
    """
    Immutable representation of an LLM generation result.
    """

    text: str
    raw_response: Dict[str, Any]
    model_name: str
    usage: Dict[str, int] = field(default_factory=dict)


class ModelProvider(ABC):
    """
    Interface for concrete LLM API clients (e.g. Ollama, LM Studio).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for the provider (e.g., 'ollama', 'openai').

        Returns:
            str: Provider identifier name.
        """
        pass

    @abstractmethod
    def generate(
        self, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        """
        Submits a raw text completion request.

        Args:
            prompt (str): Text prompt.
            model (Optional[str]): Target model identifier. Defaults to provider default.
            **kwargs: Extra parameters (e.g. temperature, max_tokens).

        Returns:
            ModelResponse: Standardized model response container.
        """
        pass

    @abstractmethod
    def generate_chat(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        """
        Submits a structured chat/conversation request.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries with 'role' and 'content'.
            model (Optional[str]): Target model identifier. Defaults to provider default.
            **kwargs: Extra parameters (e.g. temperature, max_tokens).

        Returns:
            ModelResponse: Standardized model response container.
        """
        pass


class ModelRouterService(ABC):
    """
    Central router interface for resolving and calling registered model providers.
    """

    @abstractmethod
    def register_provider(self, provider: ModelProvider) -> None:
        """
        Registers a new model provider.

        Args:
            provider (ModelProvider): The provider instance to register.
        """
        pass

    @abstractmethod
    def get_provider(self, name: str) -> ModelProvider:
        """
        Resolves a registered model provider by name.

        Args:
            name (str): The provider name.

        Returns:
            ModelProvider: The registered provider instance.
        """
        pass

    @abstractmethod
    def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> ModelResponse:
        """
        Routes and executes a text generation request.
        Uses system default provider/model settings if parameters are omitted.

        Args:
            prompt (str): Text prompt.
            provider (Optional[str]): Target provider.
            model (Optional[str]): Target model name.
            **kwargs: Overrides for inference.

        Returns:
            ModelResponse: Generation result.
        """
        pass

    @abstractmethod
    def generate_chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs: Any
    ) -> ModelResponse:
        """
        Routes and executes a chat conversation request.
        Uses system default provider/model settings if parameters are omitted.

        Args:
            messages (List[Dict[str, str]]): Message history.
            provider (Optional[str]): Target provider.
            model (Optional[str]): Target model name.
            **kwargs: Overrides for inference.

        Returns:
            ModelResponse: Generation result.
        """
        pass
