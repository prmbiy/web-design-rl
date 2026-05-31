#!/usr/bin/env python3
"""
CLI for Phase 2: package Phase 1 task directories into Harbor tasks.

Usage:
    python scripts/pack.py                    # all completed tasks
    python scripts/pack.py --ids 001 003      # specific tasks only
    python scripts/pack.py --force            # overwrite existing harbor/ dirs
"""

import argparse
import sys
from pathlib import Path

# Ensure src/ is importable when running from project root
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from harbor.pack import pack_all


def main():
    parser = argparse.ArgumentParser(description="Package Phase 1 tasks into Harbor format.")
    parser.add_argument(
        "--ids",
        nargs="+",
        metavar="ID",
        help="Task IDs to package (e.g. 001 003). Omit to package all completed tasks.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing harbor/ directories.",
    )
    args = parser.parse_args()

    tasks_root = Path(__file__).parent.parent / "tasks"
    if not tasks_root.exists():
        print(f"ERROR: tasks directory not found at {tasks_root}", file=sys.stderr)
        sys.exit(1)

    pack_all(tasks_root, ids=args.ids, force=args.force)


if __name__ == "__main__":
    main()
