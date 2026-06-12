"""Content-only baseline: whole-page OCR token-F1, no layout/design awareness."""
from __future__ import annotations

from pathlib import Path

from ..segment import _ocr_words_with_y
from ..signals import content_score
from .base import Method, MethodResult


class ContentOnlyMethod(Method):
    name = "content_only"

    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        # Agent images wider than 1440 are cropped from the left (matches the
        # rest of the evaluator's handling of overflow renders).
        gt_words = [w for w, _y in _ocr_words_with_y(gt_path)]
        agent_words = [w for w, _y in _ocr_words_with_y(agent_path, crop_width=1440)]
        s = content_score(gt_words, agent_words)
        return MethodResult(
            score=s,
            components={"content": s},
            metadata={"gt_word_count": len(gt_words), "agent_word_count": len(agent_words)},
        )
