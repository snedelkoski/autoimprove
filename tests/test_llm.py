"""Tests for autoimprove LLM client module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from autoimprove.config import LLMConfig
from autoimprove.llm import LLMClient


class TestLLMClient:
    def _make_client(self, api_key="test-key"):
        config = LLMConfig(api_key=api_key)
        return LLMClient(config)

    def test_init(self):
        client = self._make_client()
        assert client._client is None
        assert client.config.api_key == "test-key"

    @patch("autoimprove.llm.OpenAI")
    def test_chat(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello world"
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        result = client.chat([{"role": "user", "content": "hi"}])
        assert result == "Hello world"

    @patch("autoimprove.llm.OpenAI")
    def test_chat_json(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '{"key": "value"}'
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        result = client.chat_json([{"role": "user", "content": "hi"}])
        assert result == {"key": "value"}

    @patch("autoimprove.llm.OpenAI")
    def test_chat_json_with_code_fence(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '```json\n{"key": "value"}\n```'
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        result = client.chat_json([{"role": "user", "content": "hi"}])
        assert result == {"key": "value"}

    @patch("autoimprove.llm.OpenAI")
    def test_chat_json_invalid(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "not json at all"
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        with pytest.raises(ValueError, match="LLM did not return valid JSON"):
            client.chat_json([{"role": "user", "content": "hi"}])

    @patch("autoimprove.llm.OpenAI")
    def test_analyze(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Analysis result"
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        result = client.analyze("system prompt", "user prompt")
        assert result == "Analysis result"

        # Verify messages were structured correctly
        call_kwargs = mock_client.chat.completions.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    @patch("autoimprove.llm.OpenAI")
    def test_chat_empty_response_raises(self, mock_openai_cls):
        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_client.chat.completions.create.return_value = mock_response

        client = self._make_client()
        with pytest.raises(ValueError, match="LLM returned empty response"):
            client.chat([{"role": "user", "content": "hi"}])
