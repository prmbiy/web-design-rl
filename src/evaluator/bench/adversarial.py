"""Adversarial trap cases for the synthetic bench.

Standard traps: designed to fool cheap pixel/CLIP metrics.
LLM-specific traps: designed to prove our LLM rubric catches things
  content-only, CLIP, and design2code miss.
Per-dimension traps: one HTML mutation per design rubric dimension to prove
  the LLM judge actually responds to each dimension independently.
"""
from __future__ import annotations

import shutil
import tempfile
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from bs4 import BeautifulSoup
from PIL import Image

from .degrade import Variant, _inject_head, _mutate_and_render, _pil_load


# ── Standard traps ────────────────────────────────────────────────────────────

def trap_bg_color_blank(gt_path: Path, out_dir: Path) -> Variant:
    """Blank page painted with GT's dominant background color.
    Fools naive color/CLIP metrics that reward matching the dominant hue."""
    img = _pil_load(gt_path)
    arr = np.array(img.resize((64, 64)))
    flat = arr.reshape(-1, 3)
    c = Counter(map(tuple, flat.tolist()))
    dominant, _ = c.most_common(1)[0]
    out = out_dir / "trap_bg_color.png"
    Image.new("RGB", img.size, dominant).save(out)
    return Variant("trap_bg_color", tier_index=99, is_trap=True, trap_kind="standard", png_path=out)


def trap_solid_block(gt_path: Path, out_dir: Path) -> Variant:
    """A single mid-grey full-page rectangle. Generic non-content."""
    img = _pil_load(gt_path)
    out = out_dir / "trap_solid_block.png"
    Image.new("RGB", img.size, (200, 200, 200)).save(out)
    return Variant("trap_solid_block", tier_index=99, is_trap=True, trap_kind="standard", png_path=out)


def trap_text_dump(gt_path: Path, html_path: Path | None, out_dir: Path) -> Variant:
    """GT's OCR text poured into unstyled black-on-white paragraphs.
    Fools content-F1 metrics — text is there, design is completely wrong."""
    img = _pil_load(gt_path)

    if html_path and html_path.exists():
        # Extract text from HTML (richer than OCR)
        soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
        chunks = []
        for tag in soup.find_all(["h1","h2","h3","p","li","a","button","span","td"]):
            t = tag.get_text(strip=True)
            if t:
                chunks.append(t)
        chunks = chunks[:200]
    else:
        # Fall back to OCR
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        chunks = [w.strip() for w, c in zip(data["text"], data["conf"])
                  if w.strip() and float(c) >= 30]

    body = "\n".join(f"<p>{t}</p>" for t in chunks)
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>body{font-family:Arial;font-size:14px;color:#000;background:#fff;}"
        "p{margin:4px 0;}</style></head>"
        f"<body>{body}</body></html>"
    )

    from .degrade import _NODE, _RENDERER
    with tempfile.TemporaryDirectory() as tmp:
        site_dir = Path(tmp) / "site"
        site_dir.mkdir()
        (site_dir / "page.html").write_text(html, encoding="utf-8")
        import subprocess
        render_out = Path(tmp) / "out"
        node = str(_NODE) if _NODE.exists() else "node"
        r = subprocess.run(
            [node, str(_RENDERER), "--source-dir", str(site_dir), "--out-dir", str(render_out)],
            capture_output=True, timeout=60,
        )
        png = render_out / "page.png"
        out = out_dir / "trap_text_dump.png"
        if png.exists():
            # Resize to match GT dimensions so methods compare same-size images
            rendered = Image.open(png).convert("RGB")
            rendered.save(out)
        else:
            # Fallback: generate the text as an image with Pillow
            from PIL import ImageDraw, ImageFont
            canvas = Image.new("RGB", img.size, "white")
            draw = ImageDraw.Draw(canvas)
            draw.text((10, 10), "\n".join(chunks[:100]), fill="black")
            canvas.save(out)
    return Variant("trap_text_dump", tier_index=99, is_trap=True, trap_kind="standard", png_path=out)


# ── LLM-specific composite traps ──────────────────────────────────────────────

def trap_layout_content_wrong(gt_path: Path, html_path: Path | None, out_dir: Path) -> Variant:
    """Same layout/colors, all text replaced with filler.
    CLIP stays high (visual structure preserved), content-F1 collapses.
    Proves cheap visual metrics over-score. Our grader should penalise via
    the content component."""
    if html_path is None or not html_path.exists():
        return None  # needs HTML

    def mutate(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(text=True):
            s = tag.strip()
            if s and tag.parent.name not in ["script", "style", "head"]:
                # Replace with same-length filler word
                words = s.split()
                filler = " ".join("Lorem" if len(w) > 4 else "et" for w in words)
                tag.replace_with(filler)
        return str(soup)

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_layout_content_wrong", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


def trap_content_design_broken(html_path: Path | None, out_dir: Path) -> Variant:
    """Same text content, but typography + colors wildly drifted.
    content-F1 stays high, our design dims drop.
    Proves content-only metric over-scores."""
    if html_path is None or not html_path.exists():
        return None

    def mutate(html: str) -> str:
        style = (
            "<style>"
            "html{filter:hue-rotate(180deg) saturate(3.0);}"
            "html,body,*{font-family:'Comic Sans MS',cursive!important;font-size:80%!important;}"
            "h1,h2,h3{font-family:'Papyrus',fantasy!important;font-weight:100!important;"
            "text-transform:uppercase!important;letter-spacing:.5em!important;}"
            "a,button{background:lime!important;color:red!important;border:4px dashed purple!important;}"
            "</style>"
        )
        return _inject_head(html, style)

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_content_design_broken", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


def trap_polished_but_different(gt_path: Path, task_dir: Path, out_dir: Path) -> Variant:
    """A well-designed but *different* page from the same task (another slug).
    Everything should score low — proves grader rewards *similarity* not generic quality."""
    task_screenshots = task_dir / "harbor" / "environment" / "task_screenshots"
    gt_slug = gt_path.stem
    others = [p for p in task_screenshots.glob("*.png") if p.stem != gt_slug]
    if not others:
        return None
    other = sorted(others)[0]
    out = out_dir / "trap_polished_different.png"
    shutil.copy2(other, out)
    return Variant("trap_polished_different", tier_index=99, is_trap=True, trap_kind="llm_specific", png_path=out)


# ── Per-dimension rubric traps (HTML-space, content unchanged) ─────────────────

def trap_dim_color(html_path: Path | None, out_dir: Path) -> Variant:
    """Hue-rotate the whole page — brand colors wrong, everything else intact."""
    if html_path is None or not html_path.exists():
        return None

    def mutate(html: str) -> str:
        return _inject_head(html, "<style>html{filter:hue-rotate(140deg) saturate(0.7);}</style>")

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_dim_color", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


def trap_dim_typography(html_path: Path | None, out_dir: Path) -> Variant:
    """Font-family + heading-weight swap. Targets the typography rubric dimension."""
    if html_path is None or not html_path.exists():
        return None

    def mutate(html: str) -> str:
        style = (
            "<style>"
            "html,body,*{font-family:'Times New Roman',Georgia,serif!important;}"
            "h1,h2,h3,h4,h5,h6{font-family:'Courier New',monospace!important;font-weight:900!important;}"
            "</style>"
        )
        return _inject_head(html, style)

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_dim_typography", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


def trap_dim_proportion(html_path: Path | None, out_dir: Path) -> Variant:
    """Inflate all padding/margin — structure intact, spacing density wrong."""
    if html_path is None or not html_path.exists():
        return None

    def mutate(html: str) -> str:
        return _inject_head(html, "<style>*{padding:2.5em!important;margin:2em!important;}</style>")

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_dim_proportion", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


def trap_dim_states(html_path: Path | None, out_dir: Path) -> Variant:
    """Strip all active/selected styling — interactive states look inactive."""
    if html_path is None or not html_path.exists():
        return None

    def mutate(html: str) -> str:
        style = (
            "<style>"
            ".active,.selected,.current,[aria-current],[aria-selected],"
            ".is-active,.nav-active,.btn-primary,.btn-filled"
            "{background:transparent!important;color:inherit!important;"
            "border-color:transparent!important;font-weight:inherit!important;}"
            "</style>"
        )
        return _inject_head(html, style)

    v = _mutate_and_render(html_path, mutate, out_dir, "trap_dim_states", tier_index=99)
    if v:
        v = Variant(v.name, v.tier_index, is_trap=True, trap_kind="llm_specific", png_path=v.png_path)
    return v


# ── Convenience ───────────────────────────────────────────────────────────────

def build_all_traps(
    gt_path: Path,
    html_path: Path | None,
    task_dir: Path,
    out_dir: Path,
) -> list[Variant]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Variant] = []
    fns = [
        lambda: trap_bg_color_blank(gt_path, out_dir),
        lambda: trap_solid_block(gt_path, out_dir),
        lambda: trap_text_dump(gt_path, html_path, out_dir),
        lambda: trap_layout_content_wrong(gt_path, html_path, out_dir),
        lambda: trap_content_design_broken(html_path, out_dir),
        lambda: trap_polished_but_different(gt_path, task_dir, out_dir),
        lambda: trap_dim_color(html_path, out_dir),
        lambda: trap_dim_typography(html_path, out_dir),
        lambda: trap_dim_proportion(html_path, out_dir),
        lambda: trap_dim_states(html_path, out_dir),
    ]
    for fn in fns:
        try:
            v = fn()
            if v is not None:
                results.append(v)
        except Exception as e:
            print(f"  WARN adversarial: {e}")
    return results
