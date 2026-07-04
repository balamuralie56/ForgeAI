"""
Unit tests for the ForgeAI Model Router and concrete HTTP providers.
Mocks urllib response interfaces to validate correct network payloads and routing.
"""
import io
import json
import urllib.error
import urllib.request
from typing import Any, Dict
import unittest
from unittest.mock import MagicMock, patch

from forge_core.configuration.config_manager import ConfigurationManager
from forge_core.configuration.models import ModelSettings
from forge_core.configuration.service import ConfigurationService
from forge_core.model_router.exceptions import GenerationError, ProviderNotFoundError
from forge_core.model_router.providers import OllamaProvider, OpenAICompatibleProvider
from forge_core.model_router.router import ModelRouter
from forge_core.model_router.service import ModelProvider, ModelResponse


class MockHTTPResponse:
    """Mock standard urllib response containing text body."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self.body = body
        self.status = status

    def read(self) -> bytes:
        return self.body

    def __enter__(self) -> 'MockHTTPResponse':
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass


class TestModelRouter(unittest.TestCase):
    """Test suite for registering providers and routing logic."""

    def setUp(self) -> None:
        self.mock_config = MagicMock(spec=ConfigurationService)
        self.settings = ModelSettings(
            provider="ollama",
            default_model="qwen-test",
            base_url="http://localhost:11434",
            temperature=0.5,
            max_tokens=2048
        )
        self.mock_config.get_model_settings.return_value = self.settings

    def test_router_bootstraps_default_provider(self) -> None:
        router = ModelRouter(self.mock_config)
        provider = router.get_provider("ollama")
        self.assertIsNotNone(provider)
        self.assertEqual(provider.name, "ollama")

    def test_router_register_and_get_provider(self) -> None:
        router = ModelRouter(self.mock_config)
        custom_provider = MagicMock(spec=ModelProvider)
        custom_provider.name = "custom-llm"
        
        router.register_provider(custom_provider)
        resolved = router.get_provider("custom-llm")
        self.assertEqual(resolved, custom_provider)

    def test_get_unregistered_raises_error(self) -> None:
        router = ModelRouter(self.mock_config)
        with self.assertRaises(ProviderNotFoundError):
            router.get_provider("nonexistent")


class TestOllamaProvider(unittest.TestCase):
    """Test suite verifying Ollama HTTP request formatting and responses."""

    def setUp(self) -> None:
        self.provider = OllamaProvider(
            base_url="http://localhost:11434",
            default_model="qwen-coder"
        )

    @patch("urllib.request.urlopen")
    def test_generate_text_success(self, mock_urlopen) -> None:
        mock_response = {
            "model": "qwen-coder",
            "response": "Hello world response",
            "prompt_eval_count": 10,
            "eval_count": 20
        }
        mock_urlopen.return_value = MockHTTPResponse(json.dumps(mock_response).encode("utf-8"))

        res = self.provider.generate(prompt="Hello", temperature=0.8, max_tokens=150)
        
        self.assertEqual(res.text, "Hello world response")
        self.assertEqual(res.model_name, "qwen-coder")
        self.assertEqual(res.usage["prompt_tokens"], 10)
        self.assertEqual(res.usage["completion_tokens"], 20)
        self.assertEqual(res.usage["total_tokens"], 30)

        # Validate request payload sent to urllib
        args, kwargs = mock_urlopen.call_args
        req = args[0]
        self.assertIsInstance(req, urllib.request.Request)
        self.assertEqual(req.get_full_url(), "http://localhost:11434/api/generate")
        
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "qwen-coder")
        self.assertEqual(body_sent["prompt"], "Hello")
        self.assertEqual(body_sent["options"]["temperature"], 0.8)
        self.assertEqual(body_sent["options"]["num_predict"], 150)

    @patch("urllib.request.urlopen")
    def test_generate_chat_success(self, mock_urlopen) -> None:
        mock_response = {
            "model": "qwen-coder",
            "message": {"role": "assistant", "content": "Assistant chat reply"},
            "prompt_eval_count": 5,
            "eval_count": 15
        }
        mock_urlopen.return_value = MockHTTPResponse(json.dumps(mock_response).encode("utf-8"))

        messages = [{"role": "user", "content": "Hello user"}]
        res = self.provider.generate_chat(messages=messages)
        
        self.assertEqual(res.text, "Assistant chat reply")
        self.assertEqual(res.usage["prompt_tokens"], 5)
        self.assertEqual(res.usage["completion_tokens"], 15)

        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.get_full_url(), "http://localhost:11434/api/chat")
        
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["messages"], messages)

    @patch("urllib.request.urlopen")
    def test_http_error_handling(self, mock_urlopen) -> None:
        # Create an HTTPError
        fp = io.BytesIO(b"internal server error body")
        http_error = urllib.error.HTTPError(
            url="http://localhost:11434/api/generate",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore
            fp=fp
        )
        mock_urlopen.side_effect = http_error

        with self.assertRaises(GenerationError) as ctx:
            self.provider.generate(prompt="test prompt")
            
        self.assertIn("HTTP Error 500", str(ctx.exception))
        self.assertIn("internal server error body", str(ctx.exception))


class TestOpenAICompatibleProvider(unittest.TestCase):
    """Test suite verifying OpenAI-compatible HTTP requests and response translation."""

    def setUp(self) -> None:
        self.provider = OpenAICompatibleProvider(
            base_url="http://localhost:1234/v1",
            default_model="lm-studio-model"
        )

    @patch("urllib.request.urlopen")
    def test_generate_text_success(self, mock_urlopen) -> None:
        mock_response = {
            "model": "lm-studio-model",
            "choices": [{"text": "OpenAI text completion result"}],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 24,
                "total_tokens": 36
            }
        }
        mock_urlopen.return_value = MockHTTPResponse(json.dumps(mock_response).encode("utf-8"))

        res = self.provider.generate(prompt="OpenAI prompt", temperature=0.7)
        self.assertEqual(res.text, "OpenAI text completion result")
        self.assertEqual(res.usage["prompt_tokens"], 12)
        self.assertEqual(res.usage["completion_tokens"], 24)

        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.get_full_url(), "http://localhost:1234/v1/completions")
        
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "lm-studio-model")
        self.assertEqual(body_sent["temperature"], 0.7)

    @patch("urllib.request.urlopen")
    def test_generate_chat_success(self, mock_urlopen) -> None:
        mock_response = {
            "model": "lm-studio-model",
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "OpenAI chat completion reply"
                }
            }],
            "usage": {
                "prompt_tokens": 15,
                "completion_tokens": 30,
                "total_tokens": 45
            }
        }
        mock_urlopen.return_value = MockHTTPResponse(json.dumps(mock_response).encode("utf-8"))

        messages = [{"role": "user", "content": "How are you?"}]
        res = self.provider.generate_chat(messages=messages, model="custom-override")
        
        self.assertEqual(res.text, "OpenAI chat completion reply")
        self.assertEqual(res.model_name, "custom-override")
        self.assertEqual(res.usage["prompt_tokens"], 15)

        args, _ = mock_urlopen.call_args
        req = args[0]
        self.assertEqual(req.get_full_url(), "http://localhost:1234/v1/chat/completions")
        
        body_sent = json.loads(req.data.decode("utf-8"))
        self.assertEqual(body_sent["model"], "custom-override")
        self.assertEqual(body_sent["messages"], messages)


if __name__ == "__main__":
    unittest.main()
