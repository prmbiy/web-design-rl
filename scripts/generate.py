#!/usr/bin/env python3
import os
os.environ.pop("ANTHROPIC_BASE_URL", None)
os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
"""
scripts/generate.py — CLI for Phase 1 pipeline

Usage:
  python scripts/generate.py                          # generate all 30 sites
  python scripts/generate.py --ids 001 002 003        # generate specific sites
  python scripts/generate.py --concurrency 3          # run 3 sites in parallel
  python scripts/generate.py --force                  # regenerate even if cached
  python scripts/generate.py --ids 001 --step blueprint  # re-run only one step
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.generate.steps.utils import get_client

def check_connection():
    print("Checking API connection...", flush=True)
    try:
        client = get_client()
        msg = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=5,
            messages=[{"role": "user", "content": "say hello"}],
        )
        print(f"OK: {msg.content[0].text}", flush=True)
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

check_connection()

from src.generate.pipeline import DNAS_DIR, TASKS_DIR, generate_all, generate_site
from src.generate.steps import content_spec as bp_step
from src.generate.steps import coder as co_step
from src.generate.steps import visual_spec as ds_step
from src.generate.steps import renderer as re_step


def run_single_step(dna_path: Path, step: str, force: bool = False):
    """Re-run a single step for a given DNA file."""
    import json as _json
    dna = _json.loads(dna_path.read_text())
    from src.generate.pipeline import task_dir_for
    out_dir = task_dir_for(dna)
    out_dir.mkdir(parents=True, exist_ok=True)

    if step == "content_spec":
        bp_step.run(dna_path, out_dir)
    elif step == "designer":
        bp_path = out_dir / "content_spec.json"
        if not bp_path.exists():
            print("content_spec.json not found, run blueprint step first")
            sys.exit(1)
        ds_step.run(dna_path, bp_path, out_dir)
    elif step == "coder":
        bp_path = out_dir / "content_spec.json"
        dp_path = out_dir / "visual_spec.json"
        if not bp_path.exists() or not dp_path.exists():
            print("Run blueprint and designer steps first")
            sys.exit(1)
        co_step.run(dna_path, bp_path, dp_path, out_dir)
    elif step == "renderer":
        re_step.run(dna_path, out_dir)
    else:
        print(f"Unknown step: {step}. Choose from: blueprint, designer, coder, renderer")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Phase 1: Generate ground-truth websites from DNA files")
    parser.add_argument(
        "--ids", nargs="+", metavar="ID",
        help="DNA IDs to generate (e.g. 001 002). Omit to generate all.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=1,
        help="Number of sites to generate in parallel (default: 1)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate even if output already exists",
    )
    parser.add_argument(
        "--step", choices=["content_spec", "designer", "coder", "renderer"],
        help="Run only a specific step (requires --ids to identify the site)",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all available DNA files and exit",
    )
    args = parser.parse_args()

    if args.list:
        for p in sorted(DNAS_DIR.glob("*.json")):
            dna = json.loads(p.read_text())
            anim = "🎬" if dna.get("animations") else "  "
            print(f"  {anim} {dna['id']} {dna['name']:30s} [{dna['source']}] {dna['archetype']}")
        return

    if args.step:
        if not args.ids:
            print("--step requires --ids to identify which site to re-run")
            sys.exit(1)
        dna_paths = sorted(DNAS_DIR.glob("*.json"))
        for id_ in args.ids:
            matches = [p for p in dna_paths if p.name.startswith(id_)]
            if not matches:
                print(f"No DNA file found for id {id_}")
                sys.exit(1)
            run_single_step(matches[0], args.step, force=args.force)
        return

    results = generate_all(
        dna_dir=DNAS_DIR,
        concurrency=args.concurrency,
        force=args.force,
        filter_ids=args.ids,
    )

    print("\n--- Summary ---")
    ok = [r for r in results if r["status"] == "ok"]
    skipped = [r for r in results if r["status"] == "skipped"]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"  OK:      {len(ok)}")
    print(f"  Skipped: {len(skipped)}")
    print(f"  Failed:  {len(failed)}")
    if failed:
        print("\nFailed sites:")
        for r in failed:
            print(f"  {r['dna_id']} {r['dna_name']}: {r['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
