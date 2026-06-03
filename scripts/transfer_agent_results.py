#!/usr/bin/env python3
"""Transfer real agent outputs from scratch jobs into task agent_result/ folders.

For each matched scratch job → task:
  verifier/agent_screenshots/*.png  → agent_result/agent_screenshots/
  verifier/reward.json              → agent_result/reward.json
  verifier/checker_detail.json      → agent_result/checker_detail.json
  agent/trajectory.json             → agent_result/agent_log/trajectory.json
  agent/claude-code.txt             → agent_result/agent_log/claude-code.txt
  config.json                       → agent_result/config.json
  result.json                       → agent_result/result.json
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent


def match_jobs() -> dict[Path, Path]:
    """Return {scratch_harbor_dir: task_dir} for all 28 jobs."""
    tasks = {
        p.name: (p, frozenset(s.stem for s in (p / "screenshots").glob("*.png")))
        for p in (ROOT / "tasks").iterdir()
        if (p / "screenshots").exists()
    }

    mapping: dict[Path, Path] = {}
    scratch = ROOT / "jobs" / "scratch"
    for job_id in sorted(scratch.iterdir()):
        for run in job_id.iterdir():
            for harbor in run.iterdir():
                if not harbor.name.startswith("harbor__"):
                    continue
                agent_ss = harbor / "verifier" / "agent_screenshots"
                if not agent_ss.exists():
                    continue
                pages = frozenset(p.stem for p in agent_ss.glob("*.png"))
                matches = [name for name, (_, tp) in tasks.items() if tp == pages]
                if len(matches) == 1:
                    mapping[run] = tasks[matches[0]][0]
                elif len(matches) == 0:
                    print(f"  WARNING: no task match for {job_id.name} pages={sorted(pages)}")
                else:
                    print(f"  WARNING: multiple matches for {job_id.name}: {matches}")
    return mapping


def transfer(run_dir: Path, task_dir: Path, dry_run: bool = False) -> None:
    harbor = next(d for d in run_dir.iterdir() if d.name.startswith("harbor__"))
    agent_result = task_dir / "agent_result"

    ops: list[tuple[Path, Path]] = []

    # Agent screenshots
    src_ss = harbor / "verifier" / "agent_screenshots"
    dst_ss = agent_result / "agent_screenshots"
    for png in sorted(src_ss.glob("*.png")):
        ops.append((png, dst_ss / png.name))

    # Verifier files
    for fname in ("reward.json", "checker_detail.json"):
        src = harbor / "verifier" / fname
        if src.exists():
            ops.append((src, agent_result / fname))

    # Run-level files
    for fname in ("config.json", "result.json"):
        src = run_dir / fname
        if src.exists():
            ops.append((src, agent_result / fname))

    # Agent log
    for fname in ("trajectory.json", "claude-code.txt"):
        src = harbor / "agent" / fname
        if src.exists():
            ops.append((src, agent_result / "agent_log" / fname))

    if dry_run:
        for src, dst in ops:
            print(f"  {src.relative_to(ROOT)} → {dst.relative_to(ROOT)}")
        return

    for src, dst in ops:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    mapping = match_jobs()
    print(f"Matched {len(mapping)} jobs\n")

    for run_dir, task_dir in sorted(mapping.items(), key=lambda x: x[1].name):
        print(f"{task_dir.name}")
        transfer(run_dir, task_dir, dry_run=dry_run)
        if not dry_run:
            print(f"  done")

    if dry_run:
        print("\n(dry run — no files written)")
    else:
        print(f"\nAll {len(mapping)} tasks updated.")


if __name__ == "__main__":
    main()
