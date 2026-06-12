"""Shared LLM client for the grading pipeline.

Supports two backends, selected by environment variables:

  LLM_PROXY_BASE_URL + LLM_PROXY_API_KEY
      OpenAI-compatible endpoint, accessed via the openai SDK.
      Used when LLM_PROXY_BASE_URL is set in .env.

  ANTHROPIC_API_KEY (fallback)
      Direct Anthropic SDK when no proxy is configured.

.env is gitignored — no credentials or endpoint URLs appear in committed code.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

_ROOT = Path(__file__).parent.parent.parent
load_dotenv(_ROOT / ".env")

_client = None
_openai_client = None


def _use_proxy() -> bool:
    return bool(os.environ.get("LLM_PROXY_BASE_URL"))


def get_client():
    """Return the appropriate LLM client based on environment config."""
    global _client, _openai_client

    if _use_proxy():
        if _openai_client is None:
            from openai import OpenAI
            _openai_client = OpenAI(
                api_key=os.environ["LLM_PROXY_API_KEY"],
                base_url=os.environ["LLM_PROXY_BASE_URL"],
                http_client=httpx.Client(verify=False, timeout=300),
            )
        return _openai_client
    else:
        if _client is None:
            import anthropic
            _client = anthropic.Anthropic(
                api_key=os.environ["ANTHROPIC_API_KEY"],
                base_url="https://api.anthropic.com",
                http_client=httpx.Client(verify=False, timeout=180.0),
            )
        return _client


def create_message(model: str, max_tokens: int, messages: list, **kwargs):
    """Unified message creation — handles both Anthropic and OpenAI-compat clients."""
    if _use_proxy():
        client = get_client()
        resp = client.chat.completions.create(
            model=os.environ.get("LLM_PROXY_MODEL", model),
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )
        # Wrap in a duck-typed object matching Anthropic's response shape
        return _OpenAIResponseWrapper(resp)
    else:
        client = get_client()
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **kwargs,
        )


class _OpenAIResponseWrapper:
    """Wraps an OpenAI ChatCompletion to look like an Anthropic Messages response."""
    def __init__(self, resp):
        self._resp = resp

    @property
    def content(self):
        return [_ContentBlock(c.message.content or "") for c in self._resp.choices]


class _ContentBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text
