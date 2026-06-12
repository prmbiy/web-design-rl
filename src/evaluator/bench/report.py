"""Generate a human-readable report from synthetic bench results.

Usage:
    python -m src.evaluator.bench.report --results bench_results/summary.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


_METHODS = ["ours", "content_only", "clip_only", "vlm_only", "design2code"]


def _fmt(x) -> str:
    if x is None:
        return "n/a"
    try:
        return f"{float(x):.3f}"
    except Exception:
        return str(x)


def build_report(summary: list[dict]) -> str:
    lines: list[str] = []
    lines.append("# Grader Validation Report — Synthetic Bench\n")
    lines.append(
        "Five grading methods evaluated on fabricated variants of known relative quality.\n"
        "Variants include PIL image-space and HTML-space degradations, plus standard and\n"
        "LLM-specific adversarial traps.\n"
    )

    # Aggregate metric tables across all pages
    method_rf: dict[str, list[float]] = {m: [] for m in _METHODS}
    method_span: dict[str, list[float]] = {m: [] for m in _METHODS}
    method_trap_std: dict[str, list] = {m: [] for m in _METHODS}
    method_trap_llm: dict[str, list] = {m: [] for m in _METHODS}

    for entry in summary:
        page = entry["page"]
        result = entry["result"]
        lines.append(f"## Page: {page}\n")

        # Variant score table
        variants = result["variants"]
        methods = result["methods"]
        variant_names = [v["name"] for v in variants]
        tiers = {v["name"]: v["tier_index"] for v in variants}
        is_trap = {v["name"]: v["is_trap"] for v in variants}

        lines.append("### Variant scores\n")
        header = ["variant", "tier"] + _METHODS
        lines.append("| " + " | ".join(header) + " |")
        lines.append("| " + " | ".join(["---"] * len(header)) + " |")
        for name in variant_names:
            tier = tiers[name]
            trap_flag = " [T]" if is_trap[name] else ""
            row = [f"{name}{trap_flag}", f"{tier}" if not is_trap[name] else "trap"]
            for m in _METHODS:
                s = methods.get(m, {}).get("scores", {}).get(name)
                row.append(_fmt(s))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")

        # Metrics table
        lines.append("### Metrics\n")
        mheader = ["method", "rank_fidelity", "dynamic_span", "trap_std", "trap_llm"]
        lines.append("| " + " | ".join(mheader) + " |")
        lines.append("| " + " | ".join(["---"] * len(mheader)) + " |")
        for m in _METHODS:
            mdata = methods.get(m, {}).get("metrics", {})
            rf = mdata.get("rank_fidelity")
            span = mdata.get("dynamic_span")
            ts = mdata.get("trap_rejection_standard")
            tl = mdata.get("trap_rejection_llm")
            lines.append(f"| {m} | {_fmt(rf)} | {_fmt(span)} | {_fmt(ts)} | {_fmt(tl)} |")
            # accumulate for aggregate
            if rf is not None:
                method_rf[m].append(rf)
            if span is not None:
                method_span[m].append(span)
            if ts is not None:
                method_trap_std[m].append(ts)
            if tl is not None:
                method_trap_llm[m].append(tl)
        lines.append("")

    # Aggregate summary
    lines.append("---\n")
    lines.append("## Aggregate summary (mean across all pages)\n")
    aheader = ["method", "rank_fidelity", "dynamic_span", "trap_std", "trap_llm"]
    lines.append("| " + " | ".join(aheader) + " |")
    lines.append("| " + " | ".join(["---"] * len(aheader)) + " |")

    def _mean(lst): return sum(lst) / len(lst) if lst else float("nan")

    for m in _METHODS:
        rf = _fmt(_mean(method_rf[m]))
        span = _fmt(_mean(method_span[m]))
        ts = _fmt(_mean(method_trap_std[m]))
        tl = _fmt(_mean(method_trap_llm[m]))
        lines.append(f"| {m} | {rf} | {span} | {ts} | {tl} |")
    lines.append("")

    lines.append("## Metric definitions\n")
    lines.append(
        "- **rank_fidelity** — fraction of cross-tier variant pairs ranked in the correct order. "
        "1.0 = perfect alignment with gold quality ordering.\n"
        "- **dynamic_span** — `score(identity) − score(blank_white)`. Larger = grader uses more of "
        "the [0,1] range. Small values indicate dynamic-range collapse.\n"
        "- **trap_std** — fraction of standard adversarial traps scored ≤ the worst real degradation. "
        "1.0 = grader correctly penalises all traps.\n"
        "- **trap_llm** — same for LLM-specific + per-dimension traps. Our grader should lead on "
        "this metric over content-only and CLIP.\n"
        "\n[T] = trap case. tier = quality tier (lower = higher quality; same tier = tied).\n"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    summary = json.loads(args.results.read_text())
    report = build_report(summary)

    out = args.out or args.results.parent / "report.md"
    out.write_text(report)
    print(f"Report written to {out}")
    print()
    print(report[:2000])


if __name__ == "__main__":
    main()
