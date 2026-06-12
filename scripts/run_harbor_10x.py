#!/usr/bin/env python3
"""Run a Harbor task N times in parallel and collect results.

Usage:
    python scripts/run_harbor_10x.py \
        --task tasks/task_028_research_lab/harbor \
        --n 10 \
        --jobs-dir jobs/ten_x/task_028 \
        --concurrency 3
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run_once(task_path: Path, jobs_dir: Path, run_index: int) -> dict:
    run_jobs_dir = jobs_dir / f"run_{run_index:02d}"
    run_jobs_dir.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, "ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY", "")}

    result = subprocess.run(
        [
            "harbor", "run",
            "--path", str(task_path),
            "--agent", "claude-code",
            "--model", "claude-opus-4-7",
            "--jobs-dir", str(run_jobs_dir),
            "--n-attempts", "1",
            "--ae", "NODE_TLS_REJECT_UNAUTHORIZED=0",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=1800,
    )

    # harbor writes <run_jobs_dir>/<timestamp>/harbor__XXX/
    harbor_dirs = list(run_jobs_dir.glob("*/harbor__*"))
    agent_screenshots = None
    reward = None
    if harbor_dirs:
        h = harbor_dirs[0]
        ss_dir = h / "verifier" / "agent_screenshots"
        rj = h / "verifier" / "reward.json"
        if ss_dir.exists():
            agent_screenshots = str(ss_dir)
        if rj.exists():
            reward = json.loads(rj.read_text()).get("score")

    return {
        "run_index": run_index,
        "returncode": result.returncode,
        "agent_screenshots": agent_screenshots,
        "reward": reward,
        "run_dir": str(run_jobs_dir),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", type=Path, required=True)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--jobs-dir", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=3)
    args = parser.parse_args()

    args.jobs_dir.mkdir(parents=True, exist_ok=True)
    print(f"Running {args.n}× on {args.task.name}, concurrency={args.concurrency}")

    results = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_once, args.task, args.jobs_dir, i): i for i in range(1, args.n + 1)}
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            print(f"  run_{r['run_index']:02d}: rc={r['returncode']} reward={r['reward']}", flush=True)

    results.sort(key=lambda x: x["run_index"])
    manifest = args.jobs_dir / "manifest.json"
    manifest.write_text(json.dumps(results, indent=2))
    print(f"\nManifest written to {manifest}")

    # Print summary
    rewards = [r["reward"] for r in results if r["reward"] is not None]
    if rewards:
        print(f"Reward range: {min(rewards):.3f} – {max(rewards):.3f}")


if __name__ == "__main__":
    main()
