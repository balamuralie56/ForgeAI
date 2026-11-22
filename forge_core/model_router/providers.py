"""
Concrete implementations of ModelProvider for local LLM clients (Ollama and OpenAI-compatible APIs).
Uses only standard Python libraries (urllib) to keep the engine lightweight.
"""

import json
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, List, Optional

from .exceptions import GenerationError
from .service import ChatChunk, ModelProvider, ModelResponse


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

    def _stream_lines(self, path: str, payload: Dict[str, Any]) -> Iterator[str]:
        """
        Submits a POST request and yields the non-empty lines of a streamed body.

        The connection is closed as soon as the caller stops iterating (for
        example when a client cancels a reply), which also stops generation on
        the provider side.

        Args:
            path (str): Relative API path (e.g. '/api/chat').
            payload (Dict[str, Any]): JSON payload dictionary.

        Yields:
            str: Each non-empty, decoded line of the response body.

        Raises:
            GenerationError: If the request fails, returns an error status, or
                the connection drops or times out mid-stream.
        """
        url = f"{self.base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url=url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if line:
                        yield line
        except urllib.error.HTTPError as e:
            try:
                error_body = e.read().decode("utf-8")
            except OSError as read_error:
                error_body = f"<unreadable: {read_error}>"
            raise GenerationError(
                f"HTTP Error {e.code} during streaming with {self._name} provider: "
                f"{e.reason}. Body: {error_body}"
            ) from e
        except urllib.error.URLError as e:
            raise GenerationError(
                f"Network error connecting to {self._name} provider at {url}: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise GenerationError(
                f"Streaming from {self._name} provider stalled for more than "
                f"{self.timeout}s"
            ) from e
        except (OSError, UnicodeDecodeError) as e:
            raise GenerationError(
                f"Stream from {self._name} provider was interrupted: {e}"
            ) from e


def _ollama_options(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Maps standard inference parameters onto Ollama's `options` object."""
    options: Dict[str, Any] = {}
    if "temperature" in kwargs:
        options["temperature"] = kwargs["temperature"]
    if "max_tokens" in kwargs:
        options["num_predict"] = kwargs["max_tokens"]
    if "options" in kwargs:
        options.update(kwargs["options"])
    return options


class OllamaProvider(BaseHTTPProvider):
    """
    Inference client for local Ollama instances.
    """

    def __init__(
        self,
        base_url: str,
        default_model: str,
        timeout: float = 300.0,
        keep_alive: str = "30m",
    ) -> None:
        super().__init__("ollama", base_url, default_model, timeout)
        self.keep_alive = keep_alive

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

        payload: Dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if options:
            payload["options"] = options
        if kwargs.get("response_format") == "json":
            # Grammar-constrained decoding: Ollama guarantees syntactically
            # valid JSON output, eliminating the malformed-JSON failure modes
            # (unescaped quotes, raw newlines in strings, prose wrapping the
            # object) that post-hoc parsing can only ever partially recover
            # from. Only set when the caller actually expects JSON back -
            # forcing this on free-form generations (commit messages, doc
            # prose, review notes) would make the model produce garbage.
            payload["format"] = "json"

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

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.keep_alive,
        }
        if options:
            payload["options"] = options
        if kwargs.get("response_format") == "json":
            payload["format"] = "json"

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

    def stream_chat(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any
    ) -> Iterator[ChatChunk]:
        """
        Streams a chat reply from Ollama's `/api/chat` NDJSON stream.

        Args:
            messages (List[Dict[str, str]]): Messages with 'role' and 'content'.
            model (Optional[str]): Target model. Defaults to the provider default.
            **kwargs: temperature, max_tokens, options, response_format.

        Yields:
            ChatChunk: Incremental reply text; the last chunk has `done=True`
            and carries token usage.

        Raises:
            GenerationError: If Ollama reports an error, sends malformed data,
                or closes the stream before the reply is finished.
        """
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.keep_alive,
        }
        options = _ollama_options(kwargs)
        if options:
            payload["options"] = options
        if kwargs.get("response_format") == "json":
            payload["format"] = "json"

        for line in self._stream_lines("/api/chat", payload):
            try:
                event = json.loads(line)
            except json.JSONDecodeError as e:
                raise GenerationError(
                    f"Malformed stream data from Ollama: {line[:200]!r}"
                ) from e
            if not isinstance(event, dict):
                raise GenerationError(
                    f"Unexpected stream data from Ollama: {line[:200]!r}"
                )
            if event.get("error"):
                raise GenerationError(f"Ollama error: {event['error']}")

            message = event.get("message")
            text = message.get("content", "") if isinstance(message, dict) else ""
            if event.get("done"):
                prompt_eval = int(event.get("prompt_eval_count", 0) or 0)
                eval_count = int(event.get("eval_count", 0) or 0)
                yield ChatChunk(
                    text=text,
                    done=True,
                    model_name=target_model,
                    usage={
                        "prompt_tokens": prompt_eval,
                        "completion_tokens": eval_count,
                        "total_tokens": prompt_eval + eval_count,
                    },
                )
                return
            if text:
                yield ChatChunk(text=text, model_name=target_model)

        raise GenerationError("Ollama closed the stream before the reply finished.")


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
        payload: Dict[str, Any] = {
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
        payload: Dict[str, Any] = {
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
        if kwargs.get("response_format") == "json":
            # OpenAI-compatible chat completions accept this exact shape.
            # Only /chat/completions supports it, not the legacy /completions
            # endpoint used by generate() above.
            payload["response_format"] = {"type": "json_object"}

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

    def stream_chat(
        self, messages: List[Dict[str, str]], model: Optional[str] = None, **kwargs: Any
    ) -> Iterator[ChatChunk]:
        """
        Streams a chat reply from an OpenAI-compatible `/chat/completions`
        server-sent-event stream.

        Args:
            messages (List[Dict[str, str]]): Messages with 'role' and 'content'.
            model (Optional[str]): Target model. Defaults to the provider default.
            **kwargs: temperature, max_tokens, top_p, penalties, response_format.

        Yields:
            ChatChunk: Incremental reply text; the last chunk has `done=True`.

        Raises:
            GenerationError: If the server sends malformed data or closes the
                stream before the reply is finished.
        """
        target_model = model or self.default_model
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "stream": True,
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
        if kwargs.get("response_format") == "json":
            payload["response_format"] = {"type": "json_object"}

        usage: Dict[str, int] = {}
        finished = False
        for line in self._stream_lines("/chat/completions", payload):
            if not line.startswith("data:"):
                continue
            body = line[len("data:") :].strip()
            if body == "[DONE]":
                yield ChatChunk(
                    text="", done=True, model_name=target_model, usage=usage
                )
                return
            try:
                event = json.loads(body)
            except json.JSONDecodeError as e:
                raise GenerationError(
                    f"Malformed stream data from {self._name} provider: {body[:200]!r}"
                ) from e
            if not isinstance(event, dict):
                continue
            usage_data = event.get("usage")
            if isinstance(usage_data, dict):
                usage = {
                    "prompt_tokens": int(usage_data.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(
                        usage_data.get("completion_tokens", 0) or 0
                    ),
                    "total_tokens": int(usage_data.get("total_tokens", 0) or 0),
                }
            for choice in event.get("choices") or []:
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                text = delta.get("content") if isinstance(delta, dict) else None
                if text:
                    yield ChatChunk(text=text, model_name=target_model)
                if choice.get("finish_reason"):
                    finished = True

        if finished:
            yield ChatChunk(text="", done=True, model_name=target_model, usage=usage)
            return
        raise GenerationError(
            f"{self._name} provider closed the stream before the reply finished."
        )
