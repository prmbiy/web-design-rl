"""
Step 3: Design Plan + Blueprint + DNA → HTML pages
Generates one self-contained HTML file per page.
"""
import json
from pathlib import Path

from .utils import call_model, get_jinja_env


def generate_page(dna: dict, blueprint: dict, design_plan: dict, page: dict) -> str:
    """Generate HTML for a single page. Returns raw HTML string."""
    env = get_jinja_env()
    template = env.get_template("coder.j2")

    # Pull per-page spec from design plan if available
    page_spec = {}
    if "pages" in design_plan and page["slug"] in design_plan["pages"]:
        page_spec = design_plan["pages"][page["slug"]]

    prompt = template.render(
        dna=dna,
        blueprint=blueprint,
        design_plan=design_plan,
        page=page,
        page_spec=page_spec,
    )

    print(f"  [coder] generating {page['slug']} for {dna['name']}...")
    html = call_model(prompt, max_tokens=16384)

    # Strip any accidental markdown fences
    html = html.strip()
    if html.startswith("```"):
        lines = html.split("\n")
        start = 1
        end = len(lines)
        for i, line in enumerate(lines):
            if i > 0 and line.strip() == "```":
                end = i
                break
        html = "\n".join(lines[start:end]).strip()

    return html


def run(dna_path: Path, blueprint_path: Path, design_plan_path: Path, out_dir: Path) -> list[Path]:
    """Run coder step for all pages. Returns list of written HTML paths."""
    dna = json.loads(dna_path.read_text())
    blueprint = json.loads(blueprint_path.read_text())
    design_plan = json.loads(design_plan_path.read_text())

    source_dir = out_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for page in dna["pages"]:
        html = generate_page(dna, blueprint, design_plan, page)
        out_path = source_dir / f"{page['slug']}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"  [coder] written {out_path} ({len(html)} chars)")
        written.append(out_path)

    return written
