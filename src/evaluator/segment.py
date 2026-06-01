"""Stage 1: GT description and OCR-based soft sectioning.

Two steps:
  1. describe_gt()      — LLM sees GT image, outputs section list with NL descriptions (no coordinates)
  2. assign_sections()  — OCR both images, LLM assigns words to sections using the descriptions
"""
from __future__ import annotations

import base64
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
_MAX_TOKENS = 8192
_OCR_CONF_THRESHOLD = 30

VALID_TYPES = {
    "navigation", "hero", "form_step", "pricing",
    "sidebar", "media", "map", "footer", "generic",
}


@dataclass
class SectionSpec:
    label: str
    type: str
    description: str


@dataclass
class SectionWords:
    label: str
    type: str
    gt_words: list[str] = field(default_factory=list)
    agent_words: list[str] = field(default_factory=list)


def _encode(path: Path) -> str:
    return base64.standard_b64encode(path.read_bytes()).decode("ascii")


def _jinja() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_PROMPTS_DIR)),
        keep_trailing_newline=True,
    )


def _call_vision(prompt: str, *image_paths: Path) -> str:
    client = get_client()
    content: list = []
    for img_path in image_paths:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": _encode(img_path),
            },
        })
    content.append({"type": "text", "text": prompt})
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


def _call_text(prompt: str) -> str:
    client = get_client()
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text")


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


def _ocr_word_list(image_path: Path) -> str:
    """Run tesseract on an image and return a formatted word list string.

    Each line: "word [y=0.NN]" — fractional y position normalised to image height.
    Words below the confidence threshold are excluded.
    """
    with Image.open(image_path) as img:
        height = img.height
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    lines: list[str] = []
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
        y_frac = round(y_centre / height, 3) if height > 0 else 0.0
        lines.append(f"{word} [y={y_frac:.3f}]")
    # Keep at most 600 words — enough for any page, prevents prompt overflow on dense layouts
    return "\n".join(lines[:600])


def describe_gt(gt_path: Path) -> list[SectionSpec]:
    """Stage 1A: LLM describes the GT image sections with no coordinates."""
    prompt = _jinja().get_template("describe_gt.j2").render()
    raw = _call_vision(prompt, gt_path)
    data = _parse_json(raw)
    specs: list[SectionSpec] = []
    for item in data:
        sec_type = item.get("type", "generic")
        if sec_type not in VALID_TYPES:
            sec_type = "generic"
        specs.append(SectionSpec(
            label=item["label"],
            type=sec_type,
            description=item["description"],
        ))
    return specs


def assign_sections(
    gt_path: Path,
    agent_path: Path,
    specs: list[SectionSpec],
) -> list[SectionWords]:
    """Stage 1B: OCR both images, LLM assigns words to sections."""
    gt_words = _ocr_word_list(gt_path)
    agent_words = _ocr_word_list(agent_path)

    prompt = _jinja().get_template("assign_sections.j2").render(
        sections=specs,
        gt_words=gt_words,
        agent_words=agent_words,
    )
    raw = _call_text(prompt)
    data = _parse_json(raw)

    gt_map: dict[str, list[str]] = data.get("gt_sections", {})
    agent_map: dict[str, list[str]] = data.get("agent_sections", {})

    result: list[SectionWords] = []
    for spec in specs:
        result.append(SectionWords(
            label=spec.label,
            type=spec.type,
            gt_words=gt_map.get(spec.label, []),
            agent_words=agent_map.get(spec.label, []),
        ))
    return result
