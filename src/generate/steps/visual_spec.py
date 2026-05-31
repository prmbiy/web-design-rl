"""
Step 2: Blueprint + DNA → Design Plan
Generates per-page visual specification and global design system.
"""
import json
from pathlib import Path

from .utils import call_model, get_jinja_env, parse_json_response


def generate_design_plan(dna: dict, blueprint: dict) -> dict:
    """Generate design plan from DNA + blueprint."""
    env = get_jinja_env()
    template = env.get_template("designer.j2")
    prompt = template.render(dna=dna, blueprint=blueprint)

    print(f"  [designer] calling model for {dna['name']}...")
    raw = call_model(prompt, max_tokens=8192)

    design_plan = parse_json_response(raw)
    return design_plan


def run(dna_path: Path, blueprint_path: Path, out_dir: Path) -> Path:
    """Run designer step. Returns path to written visual_spec.json."""
    dna = json.loads(dna_path.read_text())
    blueprint = json.loads(blueprint_path.read_text())

    design_plan = generate_design_plan(dna, blueprint)

    out_path = out_dir / "visual_spec.json"
    out_path.write_text(json.dumps(design_plan, indent=2, ensure_ascii=False))
    print(f"  [designer] written to {out_path}")
    return out_path
