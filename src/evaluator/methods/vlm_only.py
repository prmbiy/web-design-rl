"""VLM-only baseline: our 5-dimension design judge alone, no content/topology."""
from __future__ import annotations

from pathlib import Path

from ..signals import design_score
from .base import Method, MethodResult


class VLMOnlyMethod(Method):
    name = "vlm_only"

    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        s, dims = design_score(gt_path, agent_path)
        return MethodResult(
            score=s,
            components={dim: v["score"] / 5.0 for dim, v in dims.items()},
            metadata={"dimensions": dims},
        )
