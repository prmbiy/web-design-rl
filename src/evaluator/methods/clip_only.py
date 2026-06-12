"""CLIP-only baseline: cosine similarity of CLIP embeddings on the full images.

Runs CLIP in a subprocess to avoid in-process OOM on this machine (the same
pattern the project used before). Agent images wider than 1440px are cropped
from the left first. Known to suffer dynamic-range collapse — that's exactly
what the bench should expose.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from .base import Method, MethodResult

_CLIP_WORKER = """
import sys, json
from PIL import Image
import open_clip, torch

gt_path, agent_path = sys.argv[1], sys.argv[2]
model, _, preprocess = open_clip.create_model_and_transforms("RN50", pretrained="openai")
model.eval()
device = "cuda" if torch.cuda.is_available() else "cpu"
model.to(device)
with torch.no_grad():
    gt_t = preprocess(Image.open(gt_path).convert("RGB")).unsqueeze(0).to(device)
    ag_t = preprocess(Image.open(agent_path).convert("RGB")).unsqueeze(0).to(device)
    gf = model.encode_image(gt_t); gf = gf / gf.norm(dim=-1, keepdim=True)
    af = model.encode_image(ag_t); af = af / af.norm(dim=-1, keepdim=True)
    cos = float((gf @ af.T).item())
print(json.dumps({"score": (cos + 1.0) / 2.0}))
"""


def _prep(path: Path, crop_width: int | None) -> str:
    """Write a (possibly left-cropped) copy to a temp PNG, return its path."""
    img = Image.open(path).convert("RGB")
    if crop_width and img.width > crop_width:
        img = img.crop((0, 0, crop_width, img.height))
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    img.save(tmp.name)
    return tmp.name


class CLIPOnlyMethod(Method):
    name = "clip_only"

    def score(self, gt_path: Path, agent_path: Path) -> MethodResult:
        gt_tmp = _prep(gt_path, None)
        agent_tmp = _prep(agent_path, 1440)
        try:
            result = subprocess.run(
                [sys.executable, "-c", _CLIP_WORKER, gt_tmp, agent_tmp],
                capture_output=True, text=True, timeout=180,
            )
            if result.returncode != 0:
                raise RuntimeError(f"clip worker failed: {result.stderr[-500:]}")
            data = json.loads(result.stdout.strip())
            s = max(0.0, min(1.0, float(data["score"])))
            return MethodResult(score=s, components={"clip": s})
        finally:
            Path(gt_tmp).unlink(missing_ok=True)
            Path(agent_tmp).unlink(missing_ok=True)
