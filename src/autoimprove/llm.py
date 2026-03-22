"""LLM client wrapper for autoimprove.

Uses the OpenAI SDK with configurable base_url to support any
OpenAI-compatible API: Anthropic, OpenAI, local models, etc.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from openai import OpenAI

from autoimprove.config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    """Thin wrapper around OpenAI-compatible API."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: Optional[OpenAI] = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.config.resolve_api_key(),
                base_url=self.config.resolve_base_url(),
            )
        return self._client

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
    ) -> str:
        """Send a chat completion request and return the text response."""
        resp = self.client.chat.completions.create(
            model=model or self.config.model,
            messages=messages,
            temperature=temperature if temperature is not None else self.config.temperature,
            max_tokens=max_tokens or self.config.max_tokens,
        )
        content = resp.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned empty response")
        return content.strip()

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """Send a chat request and parse the response as JSON.

        The prompt should instruct the model to return valid JSON.
        Handles markdown code fences (```json ... ```) that models
        sometimes wrap around their JSON output.
        """
        raw = self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            # Remove opening fence (possibly with language tag)
            first_newline = text.index("\n")
            text = text[first_newline + 1:]
            # Remove closing fence
            if text.endswith("```"):
                text = text[:-3].strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error("Failed to parse LLM JSON response: %s\nRaw: %s", e, raw[:500])
            raise ValueError(f"LLM did not return valid JSON: {e}") from e

    def analyze(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
        """Convenience: system + user message chat."""
        return self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **kwargs,
        )

    def analyze_json(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Convenience: system + user message chat returning JSON."""
        return self.chat_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **kwargs,
        )
