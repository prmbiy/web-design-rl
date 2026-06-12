"""COMPARE EVAL: run graders on real agent outputs across tasks.

Usage:
    # Run 10 tasks (task_001 through task_010):
    python -m src.evaluator.bench.run_compare --method content_only --n-tasks 10

    # Resume / extend to all 30 (already-done tasks are skipped):
    python -m src.evaluator.bench.run_compare --method content_only

    # Aggregate all method results into compare/summary.json:
    python -m src.evaluator.bench.run_compare --aggregate
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from ..methods.content_only import ContentOnlyMethod
from ..methods.vlm_only import VLMOnlyMethod

ROOT = Path(__file__).parent.parent.parent.parent

AVAILABLE_METHODS = {
    "content_only": ContentOnlyMethod,
    "vlm_only": VLMOnlyMethod,
}


def build_pairs(n_tasks: int | None = None) -> list[tuple[Path, Path, str, str]]:
    pairs = []
    tasks = sorted(p for p in (ROOT / "tasks").iterdir() if p.name.startswith("task_"))
    if n_tasks:
        tasks = tasks[:n_tasks]
    for task_dir in tasks:
        gt_dir = task_dir / "harbor" / "environment" / "task_screenshots"
        agent_dir = task_dir / "agent_result" / "agent_screenshots"
        if not gt_dir.exists() or not agent_dir.exists():
            continue
        for gt_path in sorted(gt_dir.glob("*.png")):
            agent_path = agent_dir / gt_path.name
            if agent_path.exists():
                pairs.append((gt_path, agent_path, task_dir.name, gt_path.stem))
    return pairs


def score_pair(gt_path, agent_path, task, slug, method) -> dict:
    r = method.score_safely(gt_path, agent_path)
    return {"task": task, "slug": slug, "score": round(r.score, 4), "components": r.components}


def write_task_report(task: str, rows: list, method_name: str, out_dir: Path) -> None:
    scores = [r["score"] for r in rows]
    avg = round(sum(scores) / len(scores), 6) if scores else 0.0
    task_out = out_dir / task
    task_out.mkdir(exist_ok=True)
    (task_out / "report.json").write_text(json.dumps({
        "task": task, "method": method_name, "avg_score": avg,
        "pages": {r["slug"]: {"score": r["score"], "components": r["components"]} for r in rows},
    }, indent=2))


def write_summary(by_task: dict, method_name: str, out_dir: Path) -> None:
    task_avgs = {t: round(sum(r["score"] for r in rows) / len(rows), 4) for t, rows in by_task.items()}
    overall = round(sum(task_avgs.values()) / len(task_avgs), 4) if task_avgs else 0.0
    (out_dir / "summary.json").write_text(json.dumps({
        "method": method_name,
        "total_pairs": sum(len(v) for v in by_task.values()),
        "task_avgs": task_avgs,
        "overall_avg": overall,
    }, indent=2))
    print(f"\nOverall avg ({method_name}): {overall:.4f}  [{len(task_avgs)} tasks]")
    print(f"Written to {out_dir}")


def run_method(method_name: str, out_dir: Path, concurrency: int, n_tasks: int | None) -> None:
    method = AVAILABLE_METHODS[method_name]()
    all_pairs = build_pairs(n_tasks)

    out_dir.mkdir(parents=True, exist_ok=True)

    # Load already-finished tasks
    by_task: dict[str, list] = {}
    for task_dir in sorted(out_dir.iterdir()):
        rp = task_dir / "report.json"
        if rp.exists():
            d = json.loads(rp.read_text())
            by_task[d["task"]] = [
                {"task": d["task"], "slug": s, "score": p["score"], "components": p["components"]}
                for s, p in d["pages"].items()
            ]

    done_tasks = set(by_task.keys())
    pending = [(gt, ag, t, s) for gt, ag, t, s in all_pairs if t not in done_tasks]

    if done_tasks:
        print(f"Resuming: {len(done_tasks)} tasks done, {len(pending)} pairs remaining")
    print(f"Running {method_name} on {len(pending)} pairs ({concurrency} workers)")

    if pending:
        new_by_task: dict[str, list] = {}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(score_pair, gt, ag, t, s, method): (t, s) for gt, ag, t, s in pending}
            with tqdm(total=len(pending), unit="pair", desc=method_name) as bar:
                for future in as_completed(futures):
                    row = future.result()
                    new_by_task.setdefault(row["task"], []).append(row)
                    bar.update(1)
                    bar.set_postfix({"last": f"{row['task'][-10:]}/{row['slug']}={row['score']:.3f}"})

        # Write per-task reports as they complete
        for task, rows in new_by_task.items():
            write_task_report(task, rows, method_name, out_dir)
            by_task[task] = rows

    write_summary(by_task, method_name, out_dir)


def aggregate(out_root: Path) -> None:
    methods = ["ours", "content_only", "vlm_only"]
    compare_dir = out_root / "compare"
    compare_dir.mkdir(exist_ok=True)

    all_tasks = sorted(p.name for p in (ROOT / "tasks").iterdir() if p.name.startswith("task_"))
    table: dict[str, dict] = {t: {} for t in all_tasks}

    for m in methods:
        if m == "ours":
            for task in all_tasks:
                rp = ROOT / "tasks" / task / "evals" / "report.json"
                if rp.exists():
                    table[task]["ours"] = json.loads(rp.read_text()).get("avg_score")
        else:
            sp = out_root / m / "summary.json"
            if sp.exists():
                for task, avg in json.loads(sp.read_text()).get("task_avgs", {}).items():
                    table[task][m] = avg

    (compare_dir / "summary.json").write_text(json.dumps({"methods": methods, "tasks": table}, indent=2))

    print(f"\n{'Task':<35} " + "  ".join(f"{m:>14}" for m in methods))
    print("-" * (35 + 16 * len(methods)))
    for task in all_tasks:
        row = "  ".join(
            f"{table[task].get(m):>14.4f}" if table[task].get(m) is not None else f"{'N/A':>14}"
            for m in methods
        )
        print(f"{task:<35} {row}")
    print(f"\nAggregated → {compare_dir / 'summary.json'}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", choices=list(AVAILABLE_METHODS.keys()))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--n-tasks", type=int, default=None,
                        help="Limit to first N tasks (omit for all 30). Resume is seamless.")
    parser.add_argument("--aggregate", action="store_true")
    parser.add_argument("--results-root", type=Path, default=Path("bench_results"))
    args = parser.parse_args()

    if args.aggregate:
        aggregate(args.results_root)
        return

    if not args.method:
        parser.error("--method required unless --aggregate")
    out = args.out or (Path("bench_results") / args.method)
    run_method(args.method, out, args.concurrency, args.n_tasks)


if __name__ == "__main__":
    main()
