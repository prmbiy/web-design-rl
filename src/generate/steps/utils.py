"""
Shared Anthropic client and utilities for all generation steps.
"""
import json
import os
import time
from pathlib import Path

import anthropic
import httpx
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

# Load .env from project root (two levels up from this file: steps/ → generate/ → src/ → root)
_ROOT = Path(__file__).parent.parent.parent.parent
load_dotenv(_ROOT / ".env")

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
MODEL = "claude-opus-4-7"

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        os.environ.pop("ANTHROPIC_BASE_URL", None)
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
        _client = anthropic.Anthropic(
            api_key=os.environ["ANTHROPIC_API_KEY"],
            base_url="https://api.anthropic.com",
            http_client=httpx.Client(verify=False, timeout=120.0),
        )
    return _client


def get_jinja_env() -> Environment:
    return Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), keep_trailing_newline=True)


def call_model(prompt: str, max_tokens: int = 16000, retries: int = 0) -> str:
    """Call Opus with streaming so we can see it's alive. Returns full text response."""
    client = get_client()
    print("    streaming", end="", flush=True)
    text = ""
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for chunk in stream.text_stream:
            text += chunk
            print(".", end="", flush=True)
    print(f" ({len(text)} chars)", flush=True)
    return text


def parse_json_response(text: str) -> dict:
    """Extract and parse JSON from model response, stripping any markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # strip opening and closing fences
        start = 1
        end = len(lines)
        for i, line in enumerate(lines):
            if i > 0 and line.strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end]).strip()
    return json.loads(text)
