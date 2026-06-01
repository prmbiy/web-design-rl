"""Main entry point for the visual similarity scorer.

Single-image mode:
    python -m src.evaluator.scorer \\
        --gt    tasks/task_030_community_events/screenshots/create.png \\
        --agent jobs/.../verifier/agent_screenshots/create.png \\
        --out   /tmp/reward.json

Task mode (auto-discovers all pages, writes evals/ + task report):
    python -m src.evaluator.scorer --task tasks/task_001_indian_govt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .aggregate import final_score, topology_score, weighted_aggregate
from .explain import explain
from .segment import SectionWords, assign_sections, describe_gt
from .signals import content_score, design_score


def _parse_y_from_word_list(word_list_str: str) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for line in word_list_str.splitlines():
        m = re.match(r"(.+?) \[y=([0-9.]+)\]", line.strip())
        if m:
            word = m.group(1)
            y = float(m.group(2))
            result.setdefault(word, []).append(y)
    return result


def _mean_y_for_section(words: list[str], word_y_map: dict[str, list[float]]) -> float:
    ys: list[float] = []
    for w in words:
        key = w.lower().strip()
        if key in word_y_map:
            ys.extend(word_y_map[key])
    return sum(ys) / len(ys) if ys else 0.0


def grade(gt_path: Path, agent_path: Path) -> dict:
    """Run the full 4-stage scorer and return the reward dict."""

    print("  [1/4] describing GT sections...", flush=True)
    specs = describe_gt(gt_path)
    print(f"        {len(specs)} sections identified", flush=True)

    print("  [2/4] OCR + assigning words to sections...", flush=True)
    sections: list[SectionWords] = assign_sections(gt_path, agent_path, specs)
    for s in sections:
        print(f"        {s.label}: gt={len(s.gt_words)} words  agent={len(s.agent_words)} words", flush=True)

    print("  [3/4] scoring...", flush=True)
    section_content_scores: dict[str, float] = {}
    sections_detail: dict[str, dict] = {}
    for s in sections:
        cs = content_score(s.gt_words, s.agent_words)
        section_content_scores[s.label] = cs
        sections_detail[s.label] = {
            "type": s.type,
            "content_score": round(cs, 4),
            "gt_word_count": len(s.gt_words),
            "agent_word_count": len(s.agent_words),
        }
        print(f"        {s.label}: content_score={cs:.3f}", flush=True)

    from .segment import _ocr_word_list
    word_y_map = _parse_y_from_word_list(_ocr_word_list(agent_path))
    agent_mean_ys = {s.label: _mean_y_for_section(s.agent_words, word_y_map) for s in sections}

    topo = topology_score(sections, agent_mean_ys)
    w_content = weighted_aggregate(sections, section_content_scores)
    print(f"        topology={topo:.3f}  weighted_content={w_content:.3f}", flush=True)

    d_score, dimensions = design_score(gt_path, agent_path)
    print(f"        design_score={d_score:.3f}", flush=True)
    for dim, v in dimensions.items():
        print(f"          {dim}: {v['score']}/5 — {v['reason']}", flush=True)

    f_score = final_score(topo, w_content, d_score)
    print(f"        final={f_score:.3f}", flush=True)

    print("  [4/4] generating explanation...", flush=True)
    explanation = explain(f_score, topo, dimensions, sections_detail)
    print(f"        {explanation}", flush=True)

    return {
        "score": round(f_score, 6),
        "scorer": "visual-similarity-v2",
        "components": {
            "topology": round(topo, 4),
            "weighted_content": round(w_content, 4),
            "design_score": round(d_score, 4),
            "design_dimensions": dimensions,
            "sections": sections_detail,
        },
        "explanation": explanation,
    }


def _task_report(task_dir: Path, page_results: dict[str, dict]) -> dict:
    """Aggregate per-page results into a concise task-level report."""
    scores = [r["score"] for r in page_results.values()]
    avg_score = round(sum(scores) / len(scores), 6) if scores else 0.0

    # Average each design dimension score across pages
    dim_names = ("color", "typography", "assets", "proportion", "states")
    dim_scores: dict[str, list[int]] = {d: [] for d in dim_names}
    dim_reasons: dict[str, list[str]] = {d: [] for d in dim_names}
    topo_scores, content_scores, design_scores = [], [], []

    for r in page_results.values():
        c = r["components"]
        topo_scores.append(c["topology"])
        content_scores.append(c["weighted_content"])
        design_scores.append(c["design_score"])
        for dim in dim_names:
            entry = c["design_dimensions"].get(dim, {})
            if entry.get("score"):
                dim_scores[dim].append(entry["score"])
            if entry.get("reason"):
                dim_reasons[dim].append(entry["reason"])

    def _avg(lst: list) -> float:
        return round(sum(lst) / len(lst), 3) if lst else 0.0

    design_summary = {}
    for dim in dim_names:
        avg_dim = _avg(dim_scores[dim])
        # Pick the reason from the lowest-scoring page for this dimension
        reasons = dim_reasons[dim]
        worst_reason = reasons[dim_scores[dim].index(min(dim_scores[dim]))] if dim_scores[dim] else ""
        design_summary[dim] = {"avg_score": avg_dim, "worst_reason": worst_reason}

    page_summary = {
        page: {"score": round(r["score"], 4), "explanation": r["explanation"]}
        for page, r in page_results.items()
    }

    return {
        "task": task_dir.name,
        "avg_score": avg_score,
        "avg_topology": _avg(topo_scores),
        "avg_content": _avg(content_scores),
        "avg_design": _avg(design_scores),
        "design_dimensions": design_summary,
        "pages": page_summary,
    }


def run_task(task_dir: Path) -> None:
    gt_dir = task_dir / "screenshots"
    agent_dir = task_dir / "agent_result" / "agent_screenshots"
    evals_dir = task_dir / "evals"

    if not gt_dir.exists():
        print(f"ERROR: screenshots dir not found: {gt_dir}", file=sys.stderr)
        sys.exit(1)
    if not agent_dir.exists():
        print(f"ERROR: agent_result/agent_screenshots not found: {agent_dir}", file=sys.stderr)
        sys.exit(1)

    gt_pages = sorted(gt_dir.glob("*.png"))
    if not gt_pages:
        print(f"ERROR: no PNG files in {gt_dir}", file=sys.stderr)
        sys.exit(1)

    evals_dir.mkdir(exist_ok=True)
    page_results: dict[str, dict] = {}

    for gt_path in gt_pages:
        page = gt_path.stem
        agent_path = agent_dir / gt_path.name
        if not agent_path.exists():
            print(f"  SKIP {page} — agent file missing", flush=True)
            continue

        print(f"\n=== {page} ===", flush=True)
        result = grade(gt_path, agent_path)
        out_path = evals_dir / f"{page}.json"
        out_path.write_text(json.dumps(result, indent=2))
        page_results[page] = result
        print(f"  → {out_path} (score={result['score']:.4f})", flush=True)

    if not page_results:
        print("No pages scored.", file=sys.stderr)
        sys.exit(1)

    report = _task_report(task_dir, page_results)
    report_path = evals_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2))

    print(f"\n{'='*50}")
    print(f"Task: {task_dir.name}")
    print(f"Average score: {report['avg_score']:.4f}")
    print(f"  topology={report['avg_topology']:.3f}  content={report['avg_content']:.3f}  design={report['avg_design']:.3f}")
    for dim, v in report["design_dimensions"].items():
        print(f"  {dim}: {v['avg_score']:.1f}/5 — {v['worst_reason']}")
    print(f"\nPer-page scores:")
    for page, p in report["pages"].items():
        print(f"  {page}: {p['score']:.4f} — {p['explanation']}")
    print(f"\nReport written to: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Visual similarity scorer")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task", type=Path, help="Task directory (auto-discovers pages)")
    group.add_argument("--gt", type=Path, help="Single GT screenshot")
    parser.add_argument("--agent", type=Path)
    parser.add_argument("--out", type=Path, default=Path("reward.json"))
    args = parser.parse_args()

    if args.task:
        run_task(args.task)
    else:
        if not args.agent:
            print("ERROR: --agent required with --gt", file=sys.stderr)
            sys.exit(1)
        if not args.gt.exists():
            print(f"ERROR: GT not found: {args.gt}", file=sys.stderr)
            sys.exit(1)
        if not args.agent.exists():
            print(f"ERROR: agent not found: {args.agent}", file=sys.stderr)
            sys.exit(1)
        print(f"Scoring {args.agent.name} against {args.gt.name}", flush=True)
        result = grade(args.gt, args.agent)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2))
        (args.out.parent / "reward.txt").write_text(f"{result['score']:.6f}\n")
        print(f"\nFinal score: {result['score']:.6f}")
        print(f"Explanation: {result['explanation']}")
        print(f"Written to: {args.out}")


if __name__ == "__main__":
    main()
