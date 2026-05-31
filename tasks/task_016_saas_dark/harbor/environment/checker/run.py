"""
Completeness checker for web-design-rl Harbor tasks.

This script is copied verbatim into environment/checker/run.py for each task.
It runs as root inside the verifier container after the agent has finished.

Usage:
    python3 run.py \\
        --agent-site /app/site \\
        --ground-truth-screenshots /task/screenshots \\
        --captures-out /logs/verifier/agent_screenshots \\
        --reward-out /logs/verifier/reward.json
"""

import argparse
import json
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--agent-site", required=True)
    p.add_argument("--ground-truth-screenshots", required=True)
    p.add_argument("--captures-out", required=True)
    p.add_argument("--reward-out", required=True)
    return p.parse_args()


def start_server(site_dir: str, port: int) -> HTTPServer:
    os.chdir(site_dir)

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def check_pages(slugs, site_dir, base_url, captures_out):
    from playwright.sync_api import sync_playwright

    results = []
    captures_out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        for slug in slugs:
            html_path = Path(site_dir) / f"{slug}.html"
            result = {"slug": slug, "file_exists": False, "rendered": False, "screenshot": None}

            if not html_path.exists():
                results.append(result)
                continue

            if html_path.stat().st_size < 200:
                result["file_exists"] = True
                results.append(result)
                continue

            result["file_exists"] = True

            try:
                page.goto(f"{base_url}/{slug}.html", wait_until="networkidle", timeout=15000)
                body_text = page.inner_text("body").strip()
                if len(body_text) < 50:
                    results.append(result)
                    continue

                capture_path = captures_out / f"{slug}.png"
                page.screenshot(path=str(capture_path), full_page=True)
                result["rendered"] = True
                result["screenshot"] = str(capture_path)
            except Exception as e:
                result["error"] = str(e)

            results.append(result)

        browser.close()

    return results


def main():
    args = parse_args()

    site_dir = Path(args.agent_site)
    gt_screenshots = Path(args.ground_truth_screenshots)
    captures_out = Path(args.captures_out)
    reward_out = Path(args.reward_out)

    slugs = sorted(p.stem for p in gt_screenshots.glob("*.png"))

    if not slugs:
        reward = {"score": 0.0, "checker": "completeness-v1", "error": "no ground truth screenshots found"}
        reward_out.write_text(json.dumps(reward, indent=2))
        return

    port = 9731
    server = start_server(str(site_dir), port)
    base_url = f"http://127.0.0.1:{port}"

    try:
        results = check_pages(slugs, str(site_dir), base_url, captures_out)
    finally:
        server.shutdown()

    rendered = sum(1 for r in results if r["rendered"])
    score = rendered / len(slugs)

    reward = {
        "score": round(score, 6),
        "checker": "completeness-v1",
        "total_pages": len(slugs),
        "rendered_pages": rendered,
        "results": results,
    }

    reward_out.parent.mkdir(parents=True, exist_ok=True)
    reward_out.write_text(json.dumps(reward, indent=2))

    reward_txt = reward_out.parent / "reward.txt"
    reward_txt.write_text(f"{score:.6f}\n")

    print(f"Checker done: {rendered}/{len(slugs)} pages rendered. Score: {score:.4f}")


if __name__ == "__main__":
    main()
