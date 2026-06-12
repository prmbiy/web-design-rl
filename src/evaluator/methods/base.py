"""Common interface for every grading method.

The bench (evaluator's evaluator) runs each method through this interface and
never reaches into a method's internals. A method takes two image paths and
returns a MethodResult with a score in [0, 1] plus optional component breakdown.
"""
from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MethodResult:
    score: float
    components: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class Method(ABC):
    """A grading method: (gt_png, agent_png) -> score in [0, 1]."""

    name: str = "method"

    @abstractmethod
    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        ...

    def score_safely(self, gt_path: Path, agent_path: Path) -> MethodResult:
        """Wrapper that never raises — returns score 0.0 on failure with the
        traceback in metadata. Keeps a bench sweep alive across one bad pair."""
        started = time.perf_counter()
        try:
            result = self.score(gt_path, agent_path)
        except Exception:
            return MethodResult(
                score=0.0,
                components={},
                metadata={"error": traceback.format_exc(), "method": self.name},
            )
        result.metadata.setdefault("method", self.name)
        result.metadata["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        return result
