"""Run all methods over all variants of chosen pages and write results JSON.

Usage:
    python -m src.evaluator.bench.run_synthetic \
        --task  tasks/task_028_research_lab \
        --slug  home \
        [--task tasks/task_001_indian_govt --slug home ...] \
        --out   bench_results/

For each (task, slug) pair:
  1. Fabricates all variants (PIL + HTML-space) + all traps.
  2. Scores every variant with every method.
  3. Computes bench metrics per method.
  4. Writes results to <out>/<task>_<slug>/scores.json.

All results combined into <out>/summary.json at the end.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from ..methods.base import Method
from ..methods.clip_only import CLIPOnlyMethod
from ..methods.content_only import ContentOnlyMethod
from ..methods.design2code import Design2CodeMethod
from ..methods.ours import OursMethod
from ..methods.vlm_only import VLMOnlyMethod
from .adversarial import build_all_traps
from .degrade import Variant, build_all_variants
from .metrics import BenchMetrics, compute_metrics


def build_methods() -> list[Method]:
    return [
        OursMethod(),
        ContentOnlyMethod(),
        CLIPOnlyMethod(),
        VLMOnlyMethod(),
        Design2CodeMethod(),
    ]


def score_page(
    gt_path: Path,
    html_path: Path | None,
    task_dir: Path,
    out_dir: Path,
    methods: list[Method],
) -> dict:
    variants_dir = out_dir / "variants"
    variants = build_all_variants(gt_path, html_path, variants_dir)
    traps = build_all_traps(gt_path, html_path, task_dir, variants_dir)
    all_variants = variants + [t for t in traps if t is not None]

    print(f"    {len(variants)} variants + {len(traps)} traps", flush=True)

    results: dict[str, dict] = {}
    for method in methods:
        method_scores: dict[str, float] = {}
        method_components: dict[str, dict] = {}
        for variant in all_variants:
            print(f"      {method.name:14s} {variant.name}", flush=True)
            r = method.score_safely(gt_path, variant.png_path)
            method_scores[variant.name] = round(r.score, 4)
            method_components[variant.name] = r.components
        metrics = compute_metrics(all_variants, method_scores)
        results[method.name] = {
            "scores": method_scores,
            "components": method_components,
            "metrics": {
                "rank_fidelity": round(metrics.rank_fidelity, 4),
                "dynamic_span": round(metrics.dynamic_span, 4),
                "trap_rejection_standard": round(metrics.trap_rejection_standard, 4) if not _is_nan(metrics.trap_rejection_standard) else None,
                "trap_rejection_llm": round(metrics.trap_rejection_llm, 4) if not _is_nan(metrics.trap_rejection_llm) else None,
                "n_ordered_pairs": metrics.n_ordered_pairs,
                "n_correct_pairs": metrics.n_correct_pairs,
            },
        }
    return {
        "variants": [{"name": v.name, "tier_index": v.tier_index, "is_trap": v.is_trap, "trap_kind": v.trap_kind} for v in all_variants],
        "methods": results,
    }


def _is_nan(x) -> bool:
    try:
        import math
        return math.isnan(x)
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", action="append", type=Path, required=True)
    parser.add_argument("--slug", action="append", type=str, required=True)
    parser.add_argument("--out", type=Path, default=Path("bench_results"))
    args = parser.parse_args()

    if len(args.task) != len(args.slug):
        parser.error("--task and --slug must be paired")

    args.out.mkdir(parents=True, exist_ok=True)
    methods = build_methods()
    summary: list[dict] = []

    for task_dir, slug in zip(args.task, args.slug):
        gt_path = task_dir / "harbor" / "environment" / "task_screenshots" / f"{slug}.png"
        html_path = task_dir / "harbor" / "solution" / "site" / f"{slug}.html"
        if not gt_path.exists():
            print(f"SKIP {task_dir.name}/{slug} — GT not found at {gt_path}", flush=True)
            continue
        if not html_path.exists():
            html_path = None
            print(f"  NOTE: no HTML for {task_dir.name}/{slug} — HTML-space variants skipped")

        page_key = f"{task_dir.name}_{slug}"
        page_out = args.out / page_key
        page_out.mkdir(parents=True, exist_ok=True)
        print(f"\n[{page_key}]", flush=True)

        result = score_page(gt_path, html_path, task_dir, page_out, methods)
        scores_path = page_out / "scores.json"
        scores_path.write_text(json.dumps(result, indent=2))
        print(f"  → {scores_path}", flush=True)

        for method_name, data in result["methods"].items():
            m = data["metrics"]
            print(f"    {method_name:14s}  rank_fidelity={m['rank_fidelity']:.3f}"
                  f"  span={m['dynamic_span']:.3f}"
                  f"  trap_std={m['trap_rejection_standard']}"
                  f"  trap_llm={m['trap_rejection_llm']}", flush=True)

        summary.append({"page": page_key, "result": result})

    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nSummary written to {args.out / 'summary.json'}")


if __name__ == "__main__":
    main()
