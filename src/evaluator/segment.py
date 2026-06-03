"""Stage 1: GT description + OCR-based word bucketing.

Two steps:
  1. describe_gt()     — LLM sees GT image, outputs section list with y-fraction bounds
  2. bucket_sections() — OCR both images, Python assigns words to sections by y-position
"""
from __future__ import annotations

import base64
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytesseract
from jinja2 import Environment, FileSystemLoader
from PIL import Image

from .utils import get_client

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MODEL = "claude-opus-4-7"
_DESCRIBE_MAX_TOKENS = 8192
_OCR_CONF_THRESHOLD = 30

VALID_TYPES = {
    "navigation", "hero", "form_step", "pricing",
    "sidebar", "media", "map", "footer", "generic",
}


@dataclass
class SectionSpec:
    label: str
    type: str
    y_top: float
    y_bottom: float


@dataclass
class SectionWords:
    label: str
    type: str
    gt_words: list[str] = field(default_factory=list)
    agent_words: list[str] = field(default_factory=list)
    # mean y-fraction of agent words — used for topology ordering check
    agent_mean_y: float = 0.0


def _encode(path: Path) -> str:
    """Half-resolution encode for API — further downscale if still over 8000px."""
    with Image.open(path) as img:
        w, h = img.size
        w, h = w // 2, h // 2
        if max(w, h) > 7900:
            scale = 7900 / max(w, h)
            w, h = int(w * scale), int(h * scale)
        img = img.resize((w, h), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _jinja() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        keep_trailing_newline=True,
    )


def _parse_json(text: str) -> object:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"[\[\{][\s\S]*[\]\}]", cleaned)
        if match:
            return json.loads(match.group(0))
        raise


def _ocr_words_with_y(image_path: Path, crop_width: int | None = None) -> list[tuple[str, float]]:
    """Return list of (word, y_fraction) from tesseract OCR."""
    with Image.open(image_path) as img:
        if crop_width and img.width > crop_width:
            img = img.crop((0, 0, crop_width, img.height))
        height = img.height
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    results: list[tuple[str, float]] = []
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            continue
        if conf < _OCR_CONF_THRESHOLD:
            continue
        y_centre = data["top"][i] + data["height"][i] / 2.0
        y_frac = round(y_centre / height, 4) if height > 0 else 0.0
        results.append((word, y_frac))
    return results[:600]


# Also expose the string format for the scorer's ordering check
def _ocr_word_list(image_path: Path) -> str:
    return "\n".join(
        f"{w} [y={y:.3f}]" for w, y in _ocr_words_with_y(image_path)
    )


def _bucket_words(
    words: list[tuple[str, float]],
    specs: list[SectionSpec],
) -> dict[str, list[str]]:
    """Assign each word to a section by y-fraction overlap. Pure Python, no LLM."""
    buckets: dict[str, list[str]] = {s.label: [] for s in specs}
    buckets["unassigned"] = []
    for word, y in words:
        assigned = False
        for spec in specs:
            if spec.y_top <= y <= spec.y_bottom:
                buckets[spec.label].append(word)
                assigned = True
                break
        if not assigned:
            buckets["unassigned"].append(word)
    return buckets


def describe_gt(gt_path: Path) -> list[SectionSpec]:
    """LLM describes GT sections with y-fraction bounds. Small output (~1024 tokens)."""
    prompt = _jinja().get_template("describe_gt.j2").render()
    client = get_client()
    content = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode(gt_path)}},
        {"type": "text", "text": prompt},
    ]
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=_DESCRIBE_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    raw = "".join(block.text for block in msg.content if block.type == "text")
    data = _parse_json(raw)

    specs: list[SectionSpec] = []
    for item in data:
        sec_type = item.get("type", "generic")
        if sec_type not in VALID_TYPES:
            sec_type = "generic"
        specs.append(SectionSpec(
            label=item["label"],
            type=sec_type,
            y_top=float(item.get("y_top", 0.0)),
            y_bottom=float(item.get("y_bottom", 1.0)),
        ))
    return specs


def bucket_sections(
    gt_path: Path,
    agent_path: Path,
    specs: list[SectionSpec],
) -> list[SectionWords]:
    """OCR both images, bucket words by y-fraction into sections. No LLM call."""
    gt_words = _ocr_words_with_y(gt_path)
    agent_words = _ocr_words_with_y(agent_path, crop_width=1440)

    gt_buckets = _bucket_words(gt_words, specs)
    agent_buckets = _bucket_words(agent_words, specs)

    result: list[SectionWords] = []
    for spec in specs:
        aw = agent_buckets.get(spec.label, [])
        agent_ys = [y for w, y in agent_words if w in aw]
        mean_y = sum(agent_ys) / len(agent_ys) if agent_ys else 0.0
        result.append(SectionWords(
            label=spec.label,
            type=spec.type,
            gt_words=gt_buckets.get(spec.label, []),
            agent_words=aw,
            agent_mean_y=mean_y,
        ))
    return result
