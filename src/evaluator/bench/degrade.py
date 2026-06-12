"""Fabricate degraded variants of a GT page at known relative quality levels.

Every variant is a PNG that can be fed directly to any Method.score() call.
Two mechanisms:

- PIL image-space: fast, no renderer needed. Works on any GT PNG.
- HTML-space: mutate the GT source HTML and re-render via screenshot_capture.js.
  Requires the GT HTML (harbor/solution/site/<slug>.html) and Node 20 on PATH.
  Produces more realistic structural degradations (section delete, font swap, etc.)

Each variant carries a tier_index (lower = better quality). Variants at the same
tier_index are considered tied in quality — the metrics will not penalize ties.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image

_RENDERER = Path(__file__).parent.parent.parent.parent / "src" / "generate" / "steps" / "screenshot_capture.js"
_NODE = Path.home() / ".nvm" / "versions" / "node" / "v20.20.0" / "bin" / "node"

# If node not at the nvm path, fall back to PATH
if not _NODE.exists():
    _NODE = Path("node")


@dataclass
class Variant:
    name: str
    tier_index: int       # lower = higher quality; same index = tie
    is_trap: bool         # trap (adversarial) cases are outside the main ranking
    trap_kind: str | None # "standard" or "llm_specific"
    png_path: Path


# ── PIL image-space degradations ──────────────────────────────────────────────

def _pil_load(gt_path: Path, crop_width: int | None = 1440) -> Image.Image:
    img = Image.open(gt_path).convert("RGB")
    if crop_width and img.width > crop_width:
        img = img.crop((0, 0, crop_width, img.height))
    return img


def identity(gt_path: Path, out_dir: Path) -> Variant:
    out = out_dir / "identity.png"
    shutil.copy2(gt_path, out)
    return Variant("identity", tier_index=1, is_trap=False, trap_kind=None, png_path=out)


def recolor(gt_path: Path, out_dir: Path, hue_shift: int = 80) -> Variant:
    """Rotate hue by hue_shift degrees — brand colors are wrong, structure intact."""
    img = _pil_load(gt_path)
    arr = np.array(img, dtype=np.uint8)
    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV).astype(np.int32)
    hsv[:, :, 0] = (hsv[:, :, 0] + hue_shift) % 180
    result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB)
    out = out_dir / "recolor.png"
    Image.fromarray(result).save(out)
    return Variant("recolor", tier_index=2, is_trap=False, trap_kind=None, png_path=out)


def grayscale(gt_path: Path, out_dir: Path) -> Variant:
    img = _pil_load(gt_path).convert("L").convert("RGB")
    out = out_dir / "grayscale.png"
    img.save(out)
    return Variant("grayscale", tier_index=3, is_trap=False, trap_kind=None, png_path=out)


def band_delete(gt_path: Path, out_dir: Path, frac: float = 0.25) -> Variant:
    """Blank a horizontal band (simulates a missing section)."""
    img = _pil_load(gt_path)
    arr = np.array(img, dtype=np.uint8).copy()
    h = arr.shape[0]
    start = int(h * 0.35)
    end = int(h * (0.35 + frac))
    arr[start:end, :] = 255
    out = out_dir / "band_delete.png"
    Image.fromarray(arr).save(out)
    return Variant("band_delete", tier_index=4, is_trap=False, trap_kind=None, png_path=out)


def band_shuffle(gt_path: Path, out_dir: Path, n_bands: int = 6) -> Variant:
    """Cut into horizontal bands and reverse their order."""
    img = _pil_load(gt_path)
    arr = np.array(img, dtype=np.uint8)
    h = arr.shape[0]
    band_h = h // n_bands
    bands = [arr[i * band_h:(i + 1) * band_h] for i in range(n_bands)]
    bands.reverse()
    result = np.concatenate(bands, axis=0)
    if result.shape[0] < h:
        result = np.concatenate([result, arr[n_bands * band_h:]], axis=0)
    out = out_dir / "band_shuffle.png"
    Image.fromarray(result).save(out)
    return Variant("band_shuffle", tier_index=5, is_trap=False, trap_kind=None, png_path=out)


def blank_white(gt_path: Path, out_dir: Path) -> Variant:
    img = _pil_load(gt_path)
    out = out_dir / "blank_white.png"
    Image.new("RGB", img.size, "white").save(out)
    return Variant("blank_white", tier_index=6, is_trap=False, trap_kind=None, png_path=out)


# ── HTML-space degradations ───────────────────────────────────────────────────

def _render_html_dir(src_dir: Path, slug: str, out_dir: Path) -> Path | None:
    """Render <slug>.html from src_dir → out_dir/<slug>.png via screenshot_capture.js."""
    if not _NODE.exists() and not shutil.which("node"):
        return None
    node = str(_NODE) if _NODE.exists() else "node"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [node, str(_RENDERER),
         "--source-dir", str(src_dir),
         "--out-dir", str(out_dir)],
        capture_output=True, timeout=60,
    )
    out_png = out_dir / f"{slug}.png"
    return out_png if out_png.exists() else None


def _mutate_and_render(
    html_path: Path,
    mutate_fn,
    out_dir: Path,
    name: str,
    tier_index: int,
) -> Variant | None:
    slug = html_path.stem
    with tempfile.TemporaryDirectory() as tmp:
        site_dir = Path(tmp) / "site"
        site_dir.mkdir()
        html_text = html_path.read_text(encoding="utf-8")
        mutated = mutate_fn(html_text)
        (site_dir / html_path.name).write_text(mutated, encoding="utf-8")
        render_out = Path(tmp) / "out"
        png = _render_html_dir(site_dir, slug, render_out)
        if png is None:
            return None
        final = out_dir / f"{name}.png"
        shutil.copy2(png, final)
    return Variant(name, tier_index=tier_index, is_trap=False, trap_kind=None, png_path=final)


def _inject_head(html: str, style: str) -> str:
    if "</head>" in html:
        return html.replace("</head>", style + "</head>", 1)
    if "<body" in html:
        return html.replace("<body", f"<head>{style}</head>\n<body", 1)
    return style + html


def section_delete(html_path: Path, out_dir: Path) -> Variant | None:
    """Remove the last <section> element and re-render."""
    def mutate(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        sections = soup.find_all("section")
        if sections:
            sections[-1].decompose()
        return str(soup)
    return _mutate_and_render(html_path, mutate, out_dir, "section_delete", tier_index=4)


def font_swap(html_path: Path, out_dir: Path) -> Variant | None:
    """Inject a drastically different font family stack."""
    def mutate(html: str) -> str:
        style = (
            "<style>"
            "html,body,*{font-family:'Times New Roman',Georgia,serif!important;}"
            "h1,h2,h3,h4,h5,h6{font-family:'Courier New',monospace!important;font-weight:900!important;}"
            "</style>"
        )
        return _inject_head(html, style)
    return _mutate_and_render(html_path, mutate, out_dir, "font_swap", tier_index=2)


def typography_drift(html_path: Path, out_dir: Path) -> Variant | None:
    """Change heading size hierarchy and weights significantly."""
    def mutate(html: str) -> str:
        style = (
            "<style>"
            "h1{font-size:1.2rem!important;font-weight:300!important;}"
            "h2{font-size:2.4rem!important;font-weight:900!important;}"
            "h3{font-size:0.8rem!important;text-transform:uppercase!important;letter-spacing:.2em!important;}"
            "body{font-size:90%!important;}"
            "</style>"
        )
        return _inject_head(html, style)
    return _mutate_and_render(html_path, mutate, out_dir, "typography_drift", tier_index=2)


def dim_assets(html_path: Path, out_dir: Path) -> Variant | None:
    """Replace all <img> and <svg> with grey placeholder boxes."""
    def mutate(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")
        for img in soup.find_all("img"):
            img["src"] = ""
            img["style"] = (img.get("style", "") + ";background:#bdbdbd;min-width:40px;min-height:40px;display:inline-block;").lstrip(";")
        for svg in soup.find_all("svg"):
            for child in list(svg.children):
                child.extract()
            svg["style"] = (svg.get("style", "") + ";background:#bdbdbd;").lstrip(";")
        return str(soup)
    return _mutate_and_render(html_path, mutate, out_dir, "dim_assets", tier_index=2)


def dim_proportion(html_path: Path, out_dir: Path) -> Variant | None:
    """Inflate all padding/margin/font-size to drift spacing density."""
    def mutate(html: str) -> str:
        style = (
            "<style>"
            "*{padding:2em!important;margin:1.5em!important;}"
            "body{font-size:140%!important;}"
            "button,a,input{padding:1.2em 2em!important;}"
            "</style>"
        )
        return _inject_head(html, style)
    return _mutate_and_render(html_path, mutate, out_dir, "dim_proportion", tier_index=2)


def dim_states(html_path: Path, out_dir: Path) -> Variant | None:
    """Strip active/selected/current state styling — all interactive states look same."""
    def mutate(html: str) -> str:
        style = (
            "<style>"
            ".active,.selected,.current,[aria-current],[aria-selected],"
            ".is-active,.nav-active{background:transparent!important;color:inherit!important;"
            "border:none!important;font-weight:inherit!important;}"
            "</style>"
        )
        return _inject_head(html, style)
    return _mutate_and_render(html_path, mutate, out_dir, "dim_states", tier_index=2)


# ── Convenience: build all PIL variants ──────────────────────────────────────

PIL_FABRICATORS = [
    identity,
    recolor,
    grayscale,
    band_delete,
    band_shuffle,
    blank_white,
]

HTML_FABRICATORS = [
    section_delete,
    font_swap,
    typography_drift,
    dim_assets,
    dim_proportion,
    dim_states,
]


def build_all_variants(
    gt_path: Path,
    html_path: Path | None,
    out_dir: Path,
) -> list[Variant]:
    out_dir.mkdir(parents=True, exist_ok=True)
    variants: list[Variant] = []
    for fn in PIL_FABRICATORS:
        try:
            variants.append(fn(gt_path, out_dir))
        except Exception as e:
            print(f"  WARN degrade.{fn.__name__}: {e}")
    if html_path and html_path.exists():
        for fn in HTML_FABRICATORS:
            try:
                v = fn(html_path, out_dir)
                if v is not None:
                    variants.append(v)
            except Exception as e:
                print(f"  WARN degrade.{fn.__name__}: {e}")
    return variants
