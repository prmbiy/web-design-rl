"""Our production grader as a Method: topology x (content + design) / 2."""
from __future__ import annotations

from pathlib import Path

from ..scorer import grade
from .base import Method, MethodResult


class OursMethod(Method):
    name = "ours"

    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        result = grade(gt_path, agent_path)
        c = result["components"]
        return MethodResult(
            score=result["score"],
            components={
                "topology": c["topology"],
                "weighted_content": c["weighted_content"],
                "design_score": c["design_score"],
            },
            metadata={"explanation": result.get("explanation", "")},
        )
