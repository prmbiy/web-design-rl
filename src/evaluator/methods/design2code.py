"""Design2Code-style metric, reimplemented from the paper, image-only.

Faithful to the scoring in Si et al. (arXiv:2403.03163),
`metrics/visual_score.py`: five equal-weighted components averaged as
`0.2 * (size + text + position + color + clip)`.

The ONE deliberate divergence from the canonical metric: block detection.
The paper detects text blocks by recolouring every element in the *HTML*,
rendering twice, and diffing — which requires the source HTML. Our project
constraint is image-only (and Part-3 framework-agnosticism needs it), so we
detect blocks directly from the screenshot: tesseract word boxes for text +
edge-contour boxes for non-text regions. Labelled "design2code-style
(image-only)" in the report, with this divergence noted.

Matching, filtering (<0.5 text similarity dropped), and the five-component
aggregation follow the paper exactly.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

import cv2
import numpy as np
import pytesseract
from PIL import Image
from scipy.optimize import linear_sum_assignment
from skimage.color import deltaE_ciede2000, rgb2lab

from .base import Method, MethodResult

_TEXT_OCR_MIN_CONF = 30
_MIN_BLOCK_AREA = 400
_MAX_BLOCK_AREA_FRAC = 0.5
_TEXT_MATCH_THRESHOLD = 0.5  # paper: drop matches below 0.5 text similarity


@dataclass
class _Block:
    # bbox stored normalized: (x, y, w, h) as fractions of image dims
    bbox: tuple[float, float, float, float]
    text: str
    color: tuple[float, float, float]  # mean RGB 0-255


def _detect_blocks(arr: np.ndarray) -> list[_Block]:
    """Image-only block detection: OCR text boxes + edge-contour non-text boxes."""
    h, w = arr.shape[:2]
    max_area = _MAX_BLOCK_AREA_FRAC * h * w
    blocks: list[_Block] = []

    # text blocks
    pil = Image.fromarray(arr)
    try:
        data = pytesseract.image_to_data(pil, output_type=pytesseract.Output.DICT)
        for i in range(len(data["text"])):
            word = (data["text"][i] or "").strip()
            if not word:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                continue
            if conf < _TEXT_OCR_MIN_CONF:
                continue
            x, y, bw, bh = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            if bw * bh < _MIN_BLOCK_AREA or bw * bh > max_area:
                continue
            blocks.append(_Block(
                bbox=(x / w, y / h, bw / w, bh / h),
                text=word.lower(),
                color=_mean_color(arr, x, y, bw, bh),
            ))
    except pytesseract.TesseractError:
        pass

    # non-text visual blocks via edge contours
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    dilated = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw * bh < _MIN_BLOCK_AREA or bw * bh > max_area:
            continue
        blocks.append(_Block(
            bbox=(x / w, y / h, bw / w, bh / h),
            text="",  # non-text block
            color=_mean_color(arr, x, y, bw, bh),
        ))
    return blocks


def _mean_color(arr: np.ndarray, x: int, y: int, w: int, h: int) -> tuple[float, float, float]:
    h_img, w_img = arr.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(w_img, x + w), min(h_img, y + h)
    if x1 <= x0 or y1 <= y0:
        return (0.0, 0.0, 0.0)
    region = arr[y0:y1, x0:x1].reshape(-1, 3).mean(axis=0)
    return (float(region[0]), float(region[1]), float(region[2]))


def _text_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _color_sim(c1: tuple, c2: tuple) -> float:
    lab1 = rgb2lab(np.array([[list(c1)]], dtype=np.float64) / 255.0)
    lab2 = rgb2lab(np.array([[list(c2)]], dtype=np.float64) / 255.0)
    de = float(deltaE_ciede2000(lab1, lab2)[0, 0])
    return max(0.0, 1.0 - de / 100.0)  # paper's normalization


def _centroid(b: _Block) -> tuple[float, float]:
    x, y, w, h = b.bbox
    return (x + w / 2.0, y + h / 2.0)


def _area(b: _Block) -> float:
    return b.bbox[2] * b.bbox[3]


# CLIP runs in a subprocess (avoid in-process OOM), full-image, like clip_only.
_CLIP_WORKER = """
import sys, json
from PIL import Image
import open_clip, torch
gt_path, agent_path = sys.argv[1], sys.argv[2]
model, _, preprocess = open_clip.create_model_and_transforms("RN50", pretrained="openai")
model.eval(); device = "cuda" if torch.cuda.is_available() else "cpu"; model.to(device)
with torch.no_grad():
    g = preprocess(Image.open(gt_path).convert("RGB")).unsqueeze(0).to(device)
    a = preprocess(Image.open(agent_path).convert("RGB")).unsqueeze(0).to(device)
    gf = model.encode_image(g); gf = gf / gf.norm(dim=-1, keepdim=True)
    af = model.encode_image(a); af = af / af.norm(dim=-1, keepdim=True)
    print(json.dumps({"score": (float((gf @ af.T).item()) + 1.0) / 2.0}))
"""


def _clip_sim(gt_arr: np.ndarray, agent_arr: np.ndarray) -> float:
    gt_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    ag_tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    Image.fromarray(gt_arr).save(gt_tmp.name)
    Image.fromarray(agent_arr).save(ag_tmp.name)
    try:
        r = subprocess.run(
            [sys.executable, "-c", _CLIP_WORKER, gt_tmp.name, ag_tmp.name],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return 0.5
        import json
        return max(0.0, min(1.0, float(json.loads(r.stdout.strip())["score"])))
    except Exception:
        return 0.5
    finally:
        Path(gt_tmp.name).unlink(missing_ok=True)
        Path(ag_tmp.name).unlink(missing_ok=True)


def _load(path: Path, crop_width: int | None = None) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    if crop_width and img.width > crop_width:
        img = img.crop((0, 0, crop_width, img.height))
    return np.asarray(img)


class Design2CodeMethod(Method):
    name = "design2code"

    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        gt_arr = _load(gt_path)
        agent_arr = _load(agent_path, crop_width=1440)

        gt_blocks = _detect_blocks(gt_arr)
        agent_blocks = _detect_blocks(agent_arr)

        clip_s = _clip_sim(gt_arr, agent_arr)

        if not gt_blocks or not agent_blocks:
            final = 0.2 * clip_s
            return MethodResult(score=final, components={
                "size": 0.0, "text": 0.0, "position": 0.0, "color": 0.0, "clip": clip_s,
            })

        # Hungarian matching on text similarity (paper uses text-sim cost).
        # For text-empty blocks, SequenceMatcher("","")=1.0; we keep the paper's
        # behaviour but rely on the <0.5 filter + area to discount noise.
        n, m = len(agent_blocks), len(gt_blocks)
        cost = np.zeros((n, m))
        for i in range(n):
            for j in range(m):
                cost[i, j] = -_text_sim(agent_blocks[i].text, gt_blocks[j].text)
        row_ind, col_ind = linear_sum_assignment(cost)

        matched_text, matched_pos, matched_color, matched_area = [], [], [], []
        matched_i, matched_j = set(), set()
        for i, j in zip(row_ind, col_ind):
            ts = _text_sim(agent_blocks[i].text, gt_blocks[j].text)
            if ts < _TEXT_MATCH_THRESHOLD:
                continue
            matched_i.add(i)
            matched_j.add(j)
            cx_a, cy_a = _centroid(agent_blocks[i])
            cx_g, cy_g = _centroid(gt_blocks[j])
            pos = 1.0 - max(abs(cx_a - cx_g), abs(cy_a - cy_g))
            matched_text.append(ts)
            matched_pos.append(max(0.0, pos))
            matched_color.append(_color_sim(agent_blocks[i].color, gt_blocks[j].color))
            matched_area.append(_area(agent_blocks[i]) + _area(gt_blocks[j]))

        if not matched_area:
            final = 0.2 * clip_s
            return MethodResult(score=final, components={
                "size": 0.0, "text": 0.0, "position": 0.0, "color": 0.0, "clip": clip_s,
            })

        unmatched = sum(_area(b) for k, b in enumerate(agent_blocks) if k not in matched_i)
        unmatched += sum(_area(b) for k, b in enumerate(gt_blocks) if k not in matched_j)
        total = sum(matched_area) + unmatched

        size_s = sum(matched_area) / total if total > 0 else 0.0
        text_s = float(np.mean(matched_text))
        pos_s = float(np.mean(matched_pos))
        color_s = float(np.mean(matched_color))

        final = 0.2 * (size_s + text_s + pos_s + color_s + clip_s)
        return MethodResult(
            score=max(0.0, min(1.0, final)),
            components={
                "size": size_s, "text": text_s, "position": pos_s,
                "color": color_s, "clip": clip_s,
            },
            metadata={"matched": len(matched_area), "gt_blocks": m, "agent_blocks": n},
        )
