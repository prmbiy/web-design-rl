"""Score multiple agent runs on the same task with all methods.

This is Stage C: given N runs of Claude Code on a task (from Harbor scratch jobs),
score every run's agent_screenshots against the GT with all 5 methods, then
report whether the graders produce a sensible spread and agree on ordering.

Usage:
    python -m src.evaluator.bench.run_real \
        --task  tasks/task_028_research_lab \
        --runs  jobs/scratch/run1/harbor__xxx  jobs/scratch/run2/harbor__yyy ... \
        --out   bench_results/real_task028/
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..methods.clip_only import CLIPOnlyMethod
from ..methods.content_only import ContentOnlyMethod
from ..methods.design2code import Design2CodeMethod
from ..methods.ours import OursMethod
from ..methods.vlm_only import VLMOnlyMethod
from .run_synthetic import build_methods


def score_run(
    gt_dir: Path,
    agent_screenshots_dir: Path,
    methods,
    run_id: str,
) -> dict:
    """Score one agent run: all matching pages with all methods."""
    gt_pages = sorted(gt_dir.glob("*.png"))
    page_results: dict[str, dict] = {}

    for gt_path in gt_pages:
        agent_path = agent_screenshots_dir / gt_path.name
        if not agent_path.exists():
            print(f"    SKIP {gt_path.name} — agent file missing")
            continue
        print(f"    {gt_path.stem}", flush=True)
        page_scores: dict[str, float] = {}
        for method in methods:
            r = method.score_safely(gt_path, agent_path)
            page_scores[method.name] = round(r.score, 4)
            print(f"      {method.name:14s} {r.score:.3f}", flush=True)
        page_results[gt_path.stem] = page_scores

    if not page_results:
        return {"run_id": run_id, "pages": {}, "avg_scores": {}}

    # Average per method across pages
    all_methods = list(next(iter(page_results.values())).keys())
    avg_scores = {}
    for m in all_methods:
        vals = [page_results[p][m] for p in page_results if m in page_results[p]]
        avg_scores[m] = round(sum(vals) / len(vals), 4) if vals else 0.0

    return {
        "run_id": run_id,
        "pages": page_results,
        "avg_scores": avg_scores,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--runs", type=Path, nargs="+", required=True,
                        help="Paths to harbor__XXX dirs (each is one run)")
    parser.add_argument("--out", type=Path, default=Path("bench_results/real"))
    args = parser.parse_args()

    gt_dir = args.task / "harbor" / "environment" / "task_screenshots"
    if not gt_dir.exists():
        raise SystemExit(f"GT screenshots not found: {gt_dir}")

    args.out.mkdir(parents=True, exist_ok=True)
    methods = build_methods()
    all_runs: list[dict] = []

    for run_path in sorted(args.runs):
        agent_dir = run_path / "verifier" / "agent_screenshots"
        if not agent_dir.exists():
            print(f"SKIP {run_path.name} — no agent_screenshots")
            continue
        run_id = run_path.name
        print(f"\n[{run_id}]", flush=True)
        result = score_run(gt_dir, agent_dir, methods, run_id)
        all_runs.append(result)
        print(f"  avg: " + "  ".join(f"{m}={v:.3f}" for m, v in result["avg_scores"].items()))

    # Write per-run scores
    out_path = args.out / "scores.json"
    out_path.write_text(json.dumps(all_runs, indent=2))

    # Print ordering comparison across methods
    print(f"\n{'='*60}")
    print(f"Task: {args.task.name}  —  {len(all_runs)} runs\n")
    all_methods = list(all_runs[0]["avg_scores"].keys()) if all_runs else []
    for m in all_methods:
        sorted_runs = sorted(all_runs, key=lambda r: r["avg_scores"].get(m, 0), reverse=True)
        ranking = [f"{r['run_id'][:12]}({r['avg_scores'].get(m, 0):.3f})" for r in sorted_runs]
        print(f"{m:14s}: " + "  >  ".join(ranking))

    print(f"\nScores written to {out_path}")


if __name__ == "__main__":
    main()
