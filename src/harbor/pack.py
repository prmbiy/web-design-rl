import shutil
from pathlib import Path

from .container import render_dockerfile
from .instruction import render_instruction
from .oracle import render_solve_sh, render_test_sh
from .task_config import render_task_toml


def pack_task(task_dir: Path, force: bool = False) -> bool:
    """
    Package a single Phase 1 task directory into a Harbor task.

    Returns True if packaging succeeded, False if skipped.
    """
    if not (task_dir / "generation_complete.json").exists():
        print(f"  [skip] {task_dir.name}: generation_complete.json not found")
        return False

    harbor_dir = task_dir / "harbor"
    if harbor_dir.exists() and not force:
        print(f"  [skip] {task_dir.name}: harbor/ already exists (use --force to overwrite)")
        return False

    screenshots_dir = task_dir / "screenshots"
    slugs = sorted(p.stem for p in screenshots_dir.glob("*.png"))
    if not slugs:
        print(f"  [skip] {task_dir.name}: no screenshots found")
        return False

    recordings_dir = task_dir / "screenrecordings"
    has_animations = recordings_dir.exists() and any(recordings_dir.glob("*.mp4"))

    # Parse task id and name from directory name (format: task_NNN_name)
    parts = task_dir.name.split("_", 2)
    task_id = parts[1] if len(parts) >= 2 else task_dir.name
    task_name = parts[2] if len(parts) >= 3 else task_dir.name

    if harbor_dir.exists():
        shutil.rmtree(harbor_dir)
    harbor_dir.mkdir()

    # Top-level files
    (harbor_dir / "instruction.md").write_text(render_instruction(slugs, has_animations))
    (harbor_dir / "task.toml").write_text(render_task_toml(task_id, task_name, len(slugs)))

    # environment/
    env_dir = harbor_dir / "environment"
    env_dir.mkdir()

    # Ground-truth screenshots baked into image (agent-readable)
    task_ss_dir = env_dir / "task_screenshots"
    task_ss_dir.mkdir()
    for slug in slugs:
        src = screenshots_dir / f"{slug}.png"
        if src.exists():
            shutil.copy2(src, task_ss_dir / f"{slug}.png")

    # Screen recordings (agent-readable, animated sites only)
    if has_animations:
        task_rec_dir = env_dir / "task_screenrecordings"
        task_rec_dir.mkdir()
        for slug in slugs:
            src = recordings_dir / f"{slug}.mp4"
            if src.exists():
                shutil.copy2(src, task_rec_dir / f"{slug}.mp4")

    # Completeness checker
    checker_dir = env_dir / "checker"
    checker_dir.mkdir()
    checker_src = Path(__file__).parent / "checker.js"
    shutil.copy2(checker_src, checker_dir / "run.js")
    (checker_dir / "package.json").write_text('{"name":"checker","dependencies":{"playwright":"*"}}')

    # Dockerfile
    (env_dir / "Dockerfile").write_text(render_dockerfile(has_animations))

    # solution/ — oracle HTML files (slug-named, same as source)
    solution_dir = harbor_dir / "solution"
    solution_site_dir = solution_dir / "site"
    solution_site_dir.mkdir(parents=True)
    for slug in slugs:
        src = task_dir / "source" / f"{slug}.html"
        if src.exists():
            shutil.copy2(src, solution_site_dir / f"{slug}.html")
    solve_sh = solution_dir / "solve.sh"
    solve_sh.write_text(render_solve_sh())
    solve_sh.chmod(0o755)

    # tests/
    tests_dir = harbor_dir / "tests"
    tests_dir.mkdir()
    test_sh = tests_dir / "test.sh"
    test_sh.write_text(render_test_sh())
    test_sh.chmod(0o755)

    print(f"  [done] {task_dir.name}: {len(slugs)} pages, animations={has_animations}")
    return True


def pack_all(tasks_root: Path, ids: list[str] | None = None, force: bool = False) -> None:
    task_dirs = sorted(d for d in tasks_root.iterdir() if d.is_dir() and d.name.startswith("task_"))

    if ids:
        task_dirs = [d for d in task_dirs if any(d.name.startswith(f"task_{i}") for i in ids)]

    if not task_dirs:
        print("No matching task directories found.")
        return

    print(f"Packaging {len(task_dirs)} task(s)...")
    succeeded = 0
    for task_dir in task_dirs:
        if pack_task(task_dir, force=force):
            succeeded += 1

    print(f"\nDone: {succeeded}/{len(task_dirs)} tasks packaged.")
