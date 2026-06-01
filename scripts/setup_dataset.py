#!/usr/bin/env python3
"""
Create the Harbor dataset from all packed tasks.
Run this once after pack.py, or any time tasks are re-packed.

Usage:
    python scripts/setup_dataset.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
TASKS_DIR = REPO_ROOT / "tasks"
DATASET_DIR = REPO_ROOT / "dataset"


def main():
    env = os.environ.copy()
    for candidate in [
        Path.home() / ".local" / "bin",
        Path("/local/mnt/workspace/.local/bin"),
        Path("/local/mnt/workspace/.local/share/uv/tools/harbor/bin"),
    ]:
        if candidate.exists() and str(candidate) not in env.get("PATH", ""):
            env["PATH"] = f"{candidate}:{env.get('PATH', '')}"

    harbor_dirs = sorted(
        d / "harbor" for d in TASKS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("task_") and (d / "harbor" / "task.toml").exists()
    )

    if not harbor_dirs:
        print("No packed tasks found. Run `python scripts/pack.py` first.")
        sys.exit(1)

    if DATASET_DIR.exists():
        shutil.rmtree(DATASET_DIR)

    subprocess.run(
        ["harbor", "dataset", "init", "web-design-rl", "-o", str(DATASET_DIR), "--org", "prmbiy"],
        env=env, check=True, capture_output=True,
    )

    subprocess.run(
        ["harbor", "add"] + [str(d) for d in harbor_dirs] + ["--to", str(DATASET_DIR)],
        env=env, check=True,
    )

    print(f"Dataset ready: {len(harbor_dirs)} tasks in {DATASET_DIR}/dataset.toml")


if __name__ == "__main__":
    main()
