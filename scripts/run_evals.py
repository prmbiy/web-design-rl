#!/usr/bin/env python3
"""Run the visual similarity scorer across multiple tasks in parallel.

Usage:
    python scripts/run_evals.py [--concurrency 15] [--skip-existing]

Discovers all tasks under tasks/, skips task_001 (already done),
runs up to --concurrency tasks simultaneously.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent
TASKS_DIR = ROOT / "tasks"
PYTHON = ROOT / ".venv" / "bin" / "python"


def find_tasks(skip_existing: bool) -> list[Path]:
    tasks = sorted(p for p in TASKS_DIR.iterdir() if p.is_dir() and p.name.startswith("task_"))
    if skip_existing:
        tasks = [t for t in tasks if not (t / "evals" / "report.json").exists()]
    return tasks


def run_task(task_dir: Path) -> tuple[str, bool, str]:
    result = subprocess.run(
        [str(PYTHON), "-m", "src.evaluator.scorer", "--task", str(task_dir)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0
    output = result.stdout + result.stderr
    # Extract final summary line
    summary = ""
    for line in output.splitlines():
        if "Average score:" in line:
            summary = line.strip()
    return task_dir.name, ok, summary or output.splitlines()[-1] if output else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=15)
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip tasks that already have evals/report.json")
    args = parser.parse_args()

    tasks = find_tasks(args.skip_existing)
    if not tasks:
        print("No tasks to run.")
        return

    print(f"Running {len(tasks)} tasks with {args.concurrency} workers...")

    done, failed = 0, 0
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_task, t): t for t in tasks}
        for future in as_completed(futures):
            name, ok, summary = future.result()
            done += 1
            status = "OK" if ok else "FAIL"
            failed += 0 if ok else 1
            print(f"[{done}/{len(tasks)}] {status} {name}: {summary}", flush=True)

    print(f"\nDone — {done - failed} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
