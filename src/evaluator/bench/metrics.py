"""Validation metrics for the evaluator's evaluator.

Three metrics, each in [0, 1] where 1 = perfect:

rank_fidelity   Fraction of ordered variant *pairs* the method ranks correctly.
                Tied pairs (same tier_index) are excluded from the count.

dynamic_span    score(identity) - score(blank_white). Large = uses full range.
                Small signals dynamic-range collapse (CLIP's known failure mode).

trap_rejection  Fraction of trap variants scored ≤ max score of real degradations.
                Split into trap_rejection_standard and trap_rejection_llm.
"""
from __future__ import annotations

from dataclasses import dataclass

from .degrade import Variant


@dataclass
class BenchMetrics:
    rank_fidelity: float
    dynamic_span: float
    trap_rejection_standard: float
    trap_rejection_llm: float
    n_ordered_pairs: int
    n_correct_pairs: int


def compute_metrics(
    variants: list[Variant],
    scores: dict[str, float],   # variant.name -> score
) -> BenchMetrics:
    real = [v for v in variants if not v.is_trap]
    traps = [v for v in variants if v.is_trap]

    # rank_fidelity
    correct = 0
    total = 0
    for i in range(len(real)):
        for j in range(i + 1, len(real)):
            a, b = real[i], real[j]
            if a.tier_index == b.tier_index:
                continue  # tie — skip
            total += 1
            higher = a if a.tier_index < b.tier_index else b
            lower = b if a.tier_index < b.tier_index else a
            if scores.get(higher.name, 0.0) >= scores.get(lower.name, 0.0):
                correct += 1
    rank_fidelity = correct / total if total > 0 else 0.0

    # dynamic_span
    id_score = scores.get("identity", 0.0)
    blank_score = scores.get("blank_white", 0.0)
    dynamic_span = max(0.0, id_score - blank_score)

    # worst real degradation score (threshold for trap rejection)
    worst_real = max((scores.get(v.name, 0.0) for v in real), default=0.0)
    # blank is the guaranteed floor
    worst_real = max(worst_real, scores.get("blank_white", 0.0))

    def trap_rej(kind: str | None) -> float:
        subset = [v for v in traps if kind is None or v.trap_kind == kind]
        if not subset:
            return float("nan")
        caught = sum(1 for v in subset if scores.get(v.name, 1.0) <= worst_real)
        return caught / len(subset)

    return BenchMetrics(
        rank_fidelity=rank_fidelity,
        dynamic_span=dynamic_span,
        trap_rejection_standard=trap_rej("standard"),
        trap_rejection_llm=trap_rej("llm_specific"),
        n_ordered_pairs=total,
        n_correct_pairs=correct,
    )
