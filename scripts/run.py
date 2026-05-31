#!/usr/bin/env python3
"""
Run Harbor tasks against the claude-code agent.

Usage:
    python scripts/run.py --ids 001               # single task
    python scripts/run.py --ids 001 002 016       # multiple tasks
    python scripts/run.py                         # all packaged tasks
    python scripts/run.py --ids 001 -k 3          # 3 attempts per task
    python scripts/run.py --ids 001 002 -n 8      # 8 concurrent trials
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
ENV_FILE = REPO_ROOT / ".env"
MODEL = "claude-opus-4-7"
AGENT = "claude-code"


def load_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    print("ERROR: ANTHROPIC_API_KEY not set in environment or .env", file=sys.stderr)
    sys.exit(1)


def find_harbor_dirs(ids: list[str] | None) -> list[Path]:
    task_dirs = sorted(d for d in TASKS_DIR.iterdir() if d.is_dir() and d.name.startswith("task_"))

    if ids:
        task_dirs = [d for d in task_dirs if any(d.name.startswith(f"task_{i}") for i in ids)]

    harbor_dirs = []
    for d in task_dirs:
        harbor = d / "harbor"
        if harbor.exists():
            harbor_dirs.append(harbor)
        else:
            print(f"  [skip] {d.name}: harbor/ not found — run `python scripts/pack.py --ids {d.name.split('_')[1]}` first")

    return harbor_dirs


def main():
    parser = argparse.ArgumentParser(description="Run Harbor tasks against claude-code.")
    parser.add_argument("--ids", nargs="+", metavar="ID", help="Task IDs to run (e.g. 001 003). Omit for all packaged tasks.")
    parser.add_argument("-k", "--attempts", type=int, default=1, metavar="N", help="Number of attempts per task (default: 1).")
    parser.add_argument("-n", "--concurrency", type=int, default=4, metavar="N", help="Max concurrent trials (default: 4).")
    parser.add_argument("--jobs-dir", type=Path, default=REPO_ROOT / "jobs", help="Where to store job results (default: jobs/).")
    args = parser.parse_args()

    api_key = load_api_key()
    harbor_dirs = find_harbor_dirs(args.ids)

    if not harbor_dirs:
        print("No packaged tasks found. Run `python scripts/pack.py` first.")
        sys.exit(1)

    print(f"Running {len(harbor_dirs)} task(s), {args.attempts} attempt(s) each, {args.concurrency} concurrent...")

    cmd = ["harbor", "run"]
    for d in harbor_dirs:
        cmd += ["-p", str(d)]
    cmd += [
        "-a", AGENT,
        "-m", MODEL,
        "--ae", f"ANTHROPIC_API_KEY={api_key}",
        "-k", str(args.attempts),
        "-n", str(args.concurrency),
        "-o", str(args.jobs_dir),
    ]

    # Ensure harbor is on PATH (uv tools location)
    env = os.environ.copy()
    uv_bin = Path.home() / ".local" / "bin"
    if str(uv_bin) not in env.get("PATH", ""):
        env["PATH"] = f"{uv_bin}:{env.get('PATH', '')}"

    subprocess.run(cmd, env=env, check=True)


if __name__ == "__main__":
    main()
