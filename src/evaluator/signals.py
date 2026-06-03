"""Scoring signals: content score (word-set F1) and design score (full-image LLM)."""
from __future__ import annotations

import base64
import io
import json
import re
from pathlib import Path

from PIL import Image
from .utils import get_client

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_DESIGN_MODEL = "claude-opus-4-7"
_DESIGN_MAX_TOKENS = 512
_DIMENSIONS = ("color", "typography", "assets", "proportion", "states")


def _encode_half(path: Path, crop_width: int | None = None) -> str:
    """Half-resolution encode for API — further downscale if still over 8000px."""
    with Image.open(path) as img:
        if crop_width and img.width > crop_width:
            img = img.crop((0, 0, crop_width, img.height))
        w, h = img.size
        w, h = w // 2, h // 2
        if max(w, h) > 7900:
            scale = 7900 / max(w, h)
            w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _unit(v: float) -> float:
    return max(0.0, min(1.0, v))


def _pil_to_b64(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            return json.loads(match.group(0))
        raise


def content_score(gt_words: list[str], agent_words: list[str]) -> float:
    """Token-level F1 between two word lists.

    Operates on multisets: repeated words count multiple times.
    Returns 0.0 if either list is empty.
    """
    if not gt_words and not agent_words:
        return 1.0
    if not gt_words or not agent_words:
        return 0.0

    def counts(words: list[str]) -> dict[str, int]:
        c: dict[str, int] = {}
        for w in words:
            w = w.lower().strip()
            if w:
                c[w] = c.get(w, 0) + 1
        return c

    gt_c = counts(gt_words)
    ag_c = counts(agent_words)
    common = sum(min(gt_c[w], ag_c.get(w, 0)) for w in gt_c)
    if common == 0:
        return 0.0
    precision = common / sum(ag_c.values())
    recall = common / sum(gt_c.values())
    return _unit(2 * precision * recall / (precision + recall))


def design_score(gt_path: Path, agent_path: Path) -> tuple[float, dict]:
    """Full-image LLM design evaluation across 5 directed dimensions.

    Returns (score, dimensions) where score is in [0, 1] and dimensions is
    a dict of {dim: {"score": int, "reason": str}} for interpretability.
    """
    from jinja2 import Environment, FileSystemLoader
    prompt = (
        Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), keep_trailing_newline=True)
        .get_template("design_diff.j2")
        .render()
    )

    client = get_client()
    msg = client.messages.create(
        model=_DESIGN_MODEL,
        max_tokens=_DESIGN_MAX_TOKENS,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode_half(gt_path)}},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode_half(agent_path, crop_width=1440)}},
                {"type": "text", "text": prompt},
            ],
        }],
    )
    raw = "".join(block.text for block in msg.content if block.type == "text")

    try:
        data = _parse_json(raw)
    except Exception:
        data = {}

    dimensions: dict = {}
    scores: list[float] = []
    for dim in _DIMENSIONS:
        entry = data.get(dim, {})
        raw_score = float(entry.get("score", 3))
        raw_score = max(1.0, min(5.0, raw_score))
        dimensions[dim] = {
            "score": int(raw_score),
            "reason": entry.get("reason", ""),
        }
        scores.append(raw_score / 5.0)

    score = _unit(sum(scores) / len(scores)) if scores else 0.0
    return score, dimensions
