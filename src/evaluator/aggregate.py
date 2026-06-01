"""Topology scoring and weighted aggregation."""
from __future__ import annotations

from .segment import SectionWords

TYPE_WEIGHTS: dict[str, float] = {
    "form_step":   1.0,
    "pricing":     1.0,
    "sidebar":     0.8,
    "hero":        0.7,
    "media":       0.6,
    "map":         0.5,
    "navigation":  0.4,
    "generic":     0.4,
    "footer":      0.2,
}

_MAX_ORDER_PENALTY = 0.2


def topology_score(
    sections: list[SectionWords],
    agent_section_mean_y: dict[str, float],
) -> float:
    """Fraction of GT sections with agent words, minus ordering penalty.

    agent_section_mean_y: {label: mean fractional y of agent words} — used
    to check whether sections appear in the same vertical order as GT.
    """
    if not sections:
        return 0.0

    present = [s for s in sections if s.agent_words]
    base = len(present) / len(sections)

    if len(present) >= 2:
        ordered_labels = [s.label for s in sections if s.agent_words]
        agent_ys = [agent_section_mean_y.get(lbl, 0.0) for lbl in ordered_labels]
        inversions = sum(
            1 for i in range(len(agent_ys) - 1)
            if agent_ys[i] > agent_ys[i + 1]
        )
        max_inversions = len(agent_ys) - 1
        if max_inversions > 0:
            order_penalty = _MAX_ORDER_PENALTY * (inversions / max_inversions)
            base = max(0.0, base - order_penalty)

    return base


def weighted_aggregate(
    sections: list[SectionWords],
    section_content_scores: dict[str, float],
) -> float:
    """Type-weighted mean of per-section content scores.

    Sections with no agent words score 0 and still contribute to the denominator.
    """
    if not sections:
        return 0.0

    total_weight = 0.0
    weighted_sum = 0.0
    for sec in sections:
        weight = TYPE_WEIGHTS.get(sec.type, 0.4)
        score = section_content_scores.get(sec.label, 0.0)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0.0:
        return 0.0
    return weighted_sum / total_weight


def final_score(topo: float, weighted_content: float, design: float) -> float:
    return max(0.0, min(1.0, topo * (weighted_content + design) / 2.0))
