"""
Step 1: DNA → Blueprint
Generates fictional brand + content spec from a site DNA file.
"""
import json
from pathlib import Path

from .utils import call_model, get_jinja_env, parse_json_response


def generate_blueprint(dna: dict) -> dict:
    """Given a site DNA dict, return a blueprint dict."""
    env = get_jinja_env()
    template = env.get_template("blueprint.j2")
    prompt = template.render(dna=dna)

    print(f"  [blueprint] calling model for {dna['name']}...")
    raw = call_model(prompt)

    blueprint = parse_json_response(raw)
    return blueprint


def run(dna_path: Path, out_dir: Path) -> Path:
    """Run blueprint step for a DNA file. Returns path to written content_spec.json."""
    dna = json.loads(dna_path.read_text())
    blueprint = generate_blueprint(dna)

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "content_spec.json"
    out_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False))
    print(f"  [blueprint] written to {out_path}")
    return out_path
