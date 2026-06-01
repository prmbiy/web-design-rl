#!/usr/bin/env python3
"""
Run Harbor tasks against the claude-code agent.

Spawns one harbor process per task, running up to -n tasks in parallel.
Results are collected into tasks/task_NNN_name/agent_result/ after each run.

Usage:
    python scripts/run.py                         # all 30 tasks
    python scripts/run.py --ids 001               # single task
    python scripts/run.py --ids 001 002 016       # specific tasks
    python scripts/run.py -k 3                    # 3 attempts per task
    python scripts/run.py -n 8                    # 8 concurrent tasks
"""

import json
import os
import shutil
import subprocess
import sys
import argparse
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
ENV_FILE = REPO_ROOT / ".env"
MODEL = "claude-opus-4-7"
AGENT = "claude-code"
PROXY_URL = "http://169.254.0.1:9000"


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
            print(f"  [skip] {d.name}: not packed yet")
    return harbor_dirs


def collect_result(task_jobs_dir: Path, task_dir: Path) -> bool:
    """Copy verifier outputs from harbor's scratch dir into task_dir/agent_result/."""
    trial_dirs = [d for d in task_jobs_dir.rglob("harbor__*") if d.is_dir()]
    if not trial_dirs:
        return False

    # Pick the trial with the most recent mtime
    trial_dir = max(trial_dirs, key=lambda d: d.stat().st_mtime)

    agent_result = task_dir / "agent_result"
    if agent_result.exists():
        shutil.rmtree(agent_result)
    agent_result.mkdir()

    # Agent screenshots
    src_screenshots = trial_dir / "verifier" / "agent_screenshots"
    if src_screenshots.exists():
        shutil.copytree(src_screenshots, agent_result / "agent_screenshots")

    # Score
    src_reward = trial_dir / "verifier" / "reward.json"
    if src_reward.exists():
        shutil.copy2(src_reward, agent_result / "reward.json")

    # Checker detail (per-page breakdown)
    src_detail = trial_dir / "verifier" / "checker_detail.json"
    if src_detail.exists():
        shutil.copy2(src_detail, agent_result / "checker_detail.json")

    # Agent trajectory log
    src_log = trial_dir / "agent" / "claude-code.txt"
    if src_log.exists():
        shutil.copy2(src_log, agent_result / "agent_log.jsonl")

    return True


def main():
    parser = argparse.ArgumentParser(description="Run Harbor tasks against claude-code.")
    parser.add_argument("--ids", nargs="+", metavar="ID", help="Task IDs to run (e.g. 001 003). Omit for all tasks.")
    parser.add_argument("-k", "--attempts", type=int, default=1, metavar="N", help="Attempts per task (default: 1).")
    parser.add_argument("-n", "--concurrency", type=int, default=4, metavar="N", help="Concurrent tasks (default: 4).")
    args = parser.parse_args()

    api_key = load_api_key()
    harbor_dirs = find_harbor_dirs(args.ids)

    if not harbor_dirs:
        print("No packaged tasks found. Run `python scripts/pack.py` first.")
        sys.exit(1)

    print(f"Running {len(harbor_dirs)} task(s), {args.attempts} attempt(s) each, {args.concurrency} concurrent...")

    env = os.environ.copy()
    for candidate in [
        Path.home() / ".local" / "bin",
        Path("/local/mnt/workspace/.local/bin"),
        Path("/local/mnt/workspace/.local/share/uv/tools/harbor/bin"),
    ]:
        if candidate.exists() and str(candidate) not in env.get("PATH", ""):
            env["PATH"] = f"{candidate}:{env.get('PATH', '')}"
    env["PYTHONUTF8"] = "1"

    def run_one(harbor_dir: Path) -> tuple[str, int, bool]:
        task_dir = harbor_dir.parent
        task_name = task_dir.name
        # Unique scratch dir per run — no timestamp collisions
        task_jobs_dir = REPO_ROOT / "jobs" / "scratch" / uuid.uuid4().hex
        task_jobs_dir.mkdir(parents=True, exist_ok=True)

        try:
            cmd = [
                "harbor", "run",
                "-p", str(harbor_dir),
                "-a", AGENT,
                "-m", MODEL,
                "--ae", f"ANTHROPIC_API_KEY={api_key}",
                "--ae", f"ANTHROPIC_BASE_URL={PROXY_URL}",
                "-k", str(args.attempts),
                "-n", "1",
                "--force-build",
                "-o", str(task_jobs_dir),
            ]
            result = subprocess.run(cmd, env=env)
            collected = collect_result(task_jobs_dir, task_dir)
            return task_name, result.returncode, collected
        except Exception as e:
            print(f"  [ERROR] {task_name}: {e}")
            return task_name, -1, False

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(run_one, d): d for d in harbor_dirs}
        for future in as_completed(futures):
            task_name, code, collected = future.result()
            if code == 0 and collected:
                score = None
                reward_path = TASKS_DIR / task_name / "agent_result" / "reward.json"
                if reward_path.exists():
                    score = json.loads(reward_path.read_text()).get("score")
                print(f"  [done] {task_name}  score={score}")
            else:
                print(f"  [FAILED] {task_name}  exit={code}  collected={collected}")


if __name__ == "__main__":
    main()
