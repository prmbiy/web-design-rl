"""
Step 4: HTML/CSS → Screenshots + Screen recordings
Invokes Node.js Playwright scripts for capturing.
"""
import json
import subprocess
import sys
from pathlib import Path

# Paths to Node.js capture scripts (sibling to this file)
_HERE = Path(__file__).parent
SCREENSHOT_JS = _HERE / "screenshot_capture.js"
SCREENRECORDING_JS = _HERE / "screenrecording_capture.js"


def _run_node(script: Path, args: list[str], timeout: int = 300) -> tuple[int, str]:
    """Run a Node.js script with given args. Returns (returncode, combined output)."""
    cmd = ["node", str(script)] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    output = result.stdout + result.stderr
    return result.returncode, output


def capture_screenshots(source_dir: Path, out_dir: Path) -> dict:
    """
    Render all HTML pages in source_dir and save full-page PNGs to out_dir.
    Returns the parsed screenshot report.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "screenshot_report.json"

    print(f"  [renderer] capturing screenshots from {source_dir}...")
    returncode, output = _run_node(
        SCREENSHOT_JS,
        [
            "--source-dir", str(source_dir),
            "--out-dir", str(out_dir),
            "--report", str(report_path),
        ],
        timeout=300,
    )

    for line in output.splitlines():
        if line.strip():
            print(f"    {line}")

    if not report_path.exists():
        raise RuntimeError(f"Screenshot capture produced no report. Exit code: {returncode}\n{output}")

    report = json.loads(report_path.read_text())
    if not report.get("valid"):
        failures = report.get("failures", [])
        print(f"  [renderer] WARNING: screenshot failures: {failures}")

    return report


def capture_screenrecordings(source_dir: Path, out_dir: Path, slugs: list[str] | None = None) -> dict:
    """
    Record scroll-through videos for pages. Converts webm → mp4 via ffmpeg.
    Returns the parsed screenrecording report.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "screenrecording_report.json"

    args = [
        "--source-dir", str(source_dir),
        "--out-dir", str(out_dir),
        "--report", str(report_path),
    ]
    if slugs:
        args += ["--slugs", ",".join(slugs)]

    print(f"  [renderer] capturing screen recordings from {source_dir}...")
    returncode, output = _run_node(
        SCREENRECORDING_JS,
        args,
        timeout=600,
    )

    for line in output.splitlines():
        if line.strip():
            print(f"    {line}")

    if not report_path.exists():
        raise RuntimeError(f"Screen recording produced no report. Exit code: {returncode}\n{output}")

    report = json.loads(report_path.read_text())
    if not report.get("valid"):
        failures = report.get("failures", [])
        print(f"  [renderer] WARNING: screen recording failures: {failures}")

    return report


def run(dna_path: Path, out_dir: Path) -> dict:
    """
    Run full rendering step. Takes screenshots for all pages.
    If the DNA has animations, also records screen recordings.
    Returns summary dict with screenshot_report and optionally screenrecording_report.
    """
    dna = json.loads(dna_path.read_text())
    source_dir = out_dir / "source"
    screenshots_dir = out_dir / "screenshots"

    ss_report = capture_screenshots(source_dir, screenshots_dir)

    result = {"screenshot_report": ss_report}

    if dna.get("animations"):
        recordings_dir = out_dir / "screenrecordings"
        # Record all pages for animated sites
        slugs = [p["slug"] for p in dna["pages"]]
        rec_report = capture_screenrecordings(source_dir, recordings_dir, slugs=slugs)
        result["screenrecording_report"] = rec_report

    return result
