"""
Main orchestrator: DNA → Blueprint → Design Plan → HTML/CSS → Screenshots (+recordings)

For one site, the pipeline runs:
  1. content_spec.py  (1 Opus call)
  2. designer.py   (1 Opus call)
  3. coder.py      (N Opus calls, one per page)
  4. renderer.py   (Node.js Playwright — no model calls)

All intermediate artifacts are written to the task output directory so any
step can be re-run independently if it fails.
"""
import json
import shutil
import traceback
from pathlib import Path

from .steps import content_spec as bp_step
from .steps import visual_spec as ds_step
from .steps import coder as co_step
from .steps import renderer as re_step


TASKS_DIR = Path(__file__).parent.parent.parent / "tasks"
DNAS_DIR = Path(__file__).parent.parent.parent / "assets" / "dnas"


def task_dir_for(dna: dict) -> Path:
    return TASKS_DIR / f"task_{dna['id']}_{dna['name']}"


def generate_site(dna_path: Path, force: bool = False) -> dict:
    """
    Run the full Phase 1 pipeline for a single DNA file.

    Returns a result dict:
      {
        "dna_id": "001",
        "dna_name": "indian_govt",
        "status": "ok" | "failed" | "skipped",
        "task_dir": "...",
        "error": "..." (only on failure),
        "steps_completed": ["content_spec", "designer", "coder", "renderer"],
      }
    """
    dna = json.loads(dna_path.read_text())
    out_dir = task_dir_for(dna)
    result = {
        "dna_id": dna["id"],
        "dna_name": dna["name"],
        "task_dir": str(out_dir),
        "steps_completed": [],
    }

    # Skip if already completed and not forcing
    completion_marker = out_dir / "generation_complete.json"
    if completion_marker.exists() and not force:
        print(f"[{dna['name']}] already complete, skipping (use --force to regenerate)")
        result["status"] = "skipped"
        return result

    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy DNA into task dir for self-contained reference
    shutil.copy2(dna_path, out_dir / "site_dna.json")

    try:
        # Step 1: Blueprint
        blueprint_path = out_dir / "content_spec.json"
        if not blueprint_path.exists() or force:
            print(f"\n[{dna['name']}] Step 1/4: Blueprint")
            bp_step.run(dna_path, out_dir)
        else:
            print(f"\n[{dna['name']}] Step 1/4: Blueprint (cached)")
        result["steps_completed"].append("content_spec")

        # Step 2: Design plan
        design_plan_path = out_dir / "visual_spec.json"
        if not design_plan_path.exists() or force:
            print(f"[{dna['name']}] Step 2/4: Design plan")
            ds_step.run(dna_path, blueprint_path, out_dir)
        else:
            print(f"[{dna['name']}] Step 2/4: Design plan (cached)")
        result["steps_completed"].append("designer")

        # Step 3: HTML/CSS pages
        source_dir = out_dir / "source"
        expected_pages = {p["slug"] for p in dna["pages"]}
        existing_pages = {f.stem for f in source_dir.glob("*.html")} if source_dir.exists() else set()
        if not expected_pages.issubset(existing_pages) or force:
            print(f"[{dna['name']}] Step 3/4: HTML/CSS generation ({len(dna['pages'])} pages)")
            co_step.run(dna_path, blueprint_path, design_plan_path, out_dir)
        else:
            print(f"[{dna['name']}] Step 3/4: HTML/CSS (cached)")
        result["steps_completed"].append("coder")

        # Step 4: Rendering (screenshots + optional recordings)
        screenshots_dir = out_dir / "screenshots"
        expected_pngs = {p["slug"] + ".png" for p in dna["pages"]}
        existing_pngs = {f.name for f in screenshots_dir.glob("*.png")} if screenshots_dir.exists() else set()
        if not expected_pngs.issubset(existing_pngs) or force:
            print(f"[{dna['name']}] Step 4/4: Rendering")
            re_step.run(dna_path, out_dir)
        else:
            print(f"[{dna['name']}] Step 4/4: Rendering (cached)")
        result["steps_completed"].append("renderer")

        # Write completion marker
        completion_marker.write_text(json.dumps({
            "dna_id": dna["id"],
            "dna_name": dna["name"],
            "pages": [p["slug"] for p in dna["pages"]],
            "has_animations": bool(dna.get("animations")),
        }, indent=2))

        result["status"] = "ok"
        print(f"[{dna['name']}] Done.")

    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)
        result["traceback"] = traceback.format_exc()
        print(f"[{dna['name']}] FAILED: {e}")

    return result


def generate_all(
    dna_dir: Path = DNAS_DIR,
    concurrency: int = 1,
    force: bool = False,
    filter_ids: list[str] | None = None,
) -> list[dict]:
    """
    Run the pipeline for all DNA files in dna_dir.
    concurrency=1 runs sequentially (safe for rate limits).
    filter_ids limits to specific DNA ids e.g. ['001', '002'].
    Returns list of result dicts.
    """
    dna_paths = sorted(dna_dir.glob("*.json"))
    if filter_ids:
        dna_paths = [p for p in dna_paths if any(p.name.startswith(id_) for id_ in filter_ids)]

    print(f"Generating {len(dna_paths)} sites (concurrency={concurrency})...")

    if concurrency == 1:
        return [generate_site(p, force=force) for p in dna_paths]

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(generate_site, p, force): p for p in dna_paths}
        results = []
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
        return results
