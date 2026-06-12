"""One-sentence failure explanation — pure interpretability, no numeric role."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .utils import create_message

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_MODEL = "claude-opus-4-7"
_MAX_TOKENS = 128


def explain(
    score: float,
    topology: float,
    design: dict,
    sections: dict,
) -> str:
    prompt = (
        Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), keep_trailing_newline=True)
        .get_template("explain.j2")
        .render(score=score, topology=topology, design=design, sections=sections)
    )
    msg = create_message(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in msg.content if block.type == "text").strip()
