"""
Concrete implementations of ModelProvider for local LLM clients (Ollama and OpenAI-compatible APIs).
Uses only standard Python libraries (urllib) to keep the engine lightweight.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .exceptions import GenerationError
from .service import ModelProvider, ModelResponse


class BaseHTTPProvider(ModelProvider):
    """
    Base class containing shared logic for submitting HTTP requests to LLM APIs.
    """

    def __init__(
        self, name: str, base_url: str, default_model: str, timeout: float = 300.0
    ) -> None:
        """
        Initializes the base HTTP model provider.

        Args:
            name (str): The provider identifier name.
            base_url (str): The base URL of the HTTP endpoint.
            default_model (str): The model identifier to fall back on if none is specified.
            timeout (float): Request timeout in seconds. Default is 60.0.
        """
        self._name: str = name
        self.base_url: str = base_url.rstrip("/")
        self.default_model: str = default_model
        self.timeout: float = timeout

    @property
    def name(self) -> str:
        return self._name

    def _post_request(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Submits a POST request to the provider API.

        Args:
            path (str): Relative API path (e.g. '/api/chat').
            payload (Dict[str, Any]): JSON payload dictionary.

        Returns:
            Dict[str, Any]: Decoded JSON response.

        Raises:
            GenerationError: If the HTTP request fails or returns a non-200 status code.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url, data=data, headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            raise GenerationError(
                f"HTTP Error {e.code} during generation with {self._name} provider: {e.reason}. "
                f"Body: {error_body}"
            ) from e
        except urllib.error.URLError as e:
            raise GenerationError(
                f"Network error connecting to {self._name} provider at {url}: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise GenerationError(
                f"Request to {self._name} provider timed out after {self.timeout}s"
            ) from e
        except Exception as e:
            raise GenerationError(
                f"Unexpected error during API call to {self._name} provider: {e}"
            ) from e


class OllamaProvider(BaseHTTPProvider):
    """
    Inference client for local Ollama instances.
    """

    def __init__(
        self, base_url: str, default_model: str, timeout: float = 300.0
    ) -> None:
        super().__init__("ollama", base_url, default_model, timeout)

    def generate(
        self, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        target_model = model or self.default_model

        # Build options mapping standard parameters to Ollama format
        options: Dict[str, Any] = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if "options" in kwargs:
            options.update(kwargs["options"])

        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }
        if options:
            payload["options"] = options

        raw_response = self._post_request("/api/generate", payload)

        # Map token usage if available in the Ollama response
        prompt_eval = raw_response.get("prompt_eval_count", 0)
        eval_count = raw_response.get("eval_count", 0)
        usage = {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        }

        return ModelResponse(
            text=raw_response.get("response", ""),
            raw_response=raw_response,
            model_name=target_model,
            usage=usage,
        )

    def generate_chat(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        target_model = model or self.default_model

        options: Dict[str, Any] = {}
        if "temperature" in kwargs:
            options["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs:
            options["num_predict"] = kwargs["max_tokens"]
        if "options" in kwargs:
            options.update(kwargs["options"])

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
        }
        if options:
            payload["options"] = options

        raw_response = self._post_request("/api/chat", payload)

        # Map token usage
        prompt_eval = raw_response.get("prompt_eval_count", 0)
        eval_count = raw_response.get("eval_count", 0)
        usage = {
            "prompt_tokens": prompt_eval,
            "completion_tokens": eval_count,
            "total_tokens": prompt_eval + eval_count,
        }

        content = raw_response.get("message", {}).get("content", "")
        return ModelResponse(
            text=content,
            raw_response=raw_response,
            model_name=target_model,
            usage=usage,
        )


class OpenAICompatibleProvider(BaseHTTPProvider):
    """
    Inference client for OpenAI-compatible local servers (e.g. LM Studio, vLLM, localai).
    """

    def __init__(
        self, base_url: str, default_model: str, timeout: float = 300.0
    ) -> None:
        # Default name is 'openai', but can be registered under custom instances
        super().__init__("openai", base_url, default_model, timeout)

    def generate(
        self, prompt: str, model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }

        # Map kwargs
        for param in [
            "temperature",
            "max_tokens",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
        ]:
            if param in kwargs:
                payload[param] = kwargs[param]

        raw_response = self._post_request("/completions", payload)

        choices = raw_response.get("choices", [])
        text = choices[0].get("text", "") if choices else ""

        usage_data = raw_response.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return ModelResponse(
            text=text, raw_response=raw_response, model_name=target_model, usage=usage
        )

    def generate_chat(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any
    ) -> ModelResponse:
        target_model = model or self.default_model
        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
        }

        for param in [
            "temperature",
            "max_tokens",
            "top_p",
            "presence_penalty",
            "frequency_penalty",
        ]:
            if param in kwargs:
                payload[param] = kwargs[param]

        raw_response = self._post_request("/chat/completions", payload)

        choices = raw_response.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""

        usage_data = raw_response.get("usage", {})
        usage = {
            "prompt_tokens": usage_data.get("prompt_tokens", 0),
            "completion_tokens": usage_data.get("completion_tokens", 0),
            "total_tokens": usage_data.get("total_tokens", 0),
        }

        return ModelResponse(
            text=content,
            raw_response=raw_response,
            model_name=target_model,
            usage=usage,
        )
