"""Face detail: find the face, re-render it at full resolution with FLUX.2, blend it back.

In full-body shots the face covers a few percent of the frame, so the model draws it with a
handful of latent pixels and identity drifts. Cropping the face to 1024 px and re-rendering it
image-to-image (with the character's references) restores detail while keeping the pose.

Faces are found with OpenCV's YuNet (MIT, ~230 KB), downloaded on first use.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from PIL import Image, ImageDraw, ImageFilter

YUNET_FILE = "face_detection_yunet_2023mar.onnx"
YUNET_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/"
             + YUNET_FILE)
CROP_SIZE = 1024  # FLUX.2 renders the face crop at this size
MARGIN = 1.8  # crop side relative to the face box: hair, chin and some neck for context
SMALL_FACE = 0.06  # automatic face detail only when the face covers less of the image than this
DENOISE = 0.4  # enough to redraw eyes and skin, little enough to keep the expression and pose


@dataclass(frozen=True)
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float = 1.0

    @property
    def area(self) -> float:
        return self.w * self.h


Detector = Callable[[Image.Image], list[Face]]


class YuNet:
    """Thread-safe YuNet detector; the model file is fetched into `model_dir` on first use."""

    def __init__(self, model_dir: Path, score_threshold: float = 0.7):
        self.path = model_dir / YUNET_FILE
        self.score_threshold = score_threshold
        self._net = None
        self._lock = threading.Lock()

    def _load(self):
        import cv2

        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            try:
                r = httpx.get(YUNET_URL, follow_redirects=True, timeout=60)
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise RuntimeError(f"could not download the face detector ({e}); put {YUNET_FILE} in {self.path.parent}") from e
            tmp = self.path.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(self.path)
        return cv2.FaceDetectorYN.create(str(self.path), "", (320, 320), self.score_threshold, 0.3, 50)

    def __call__(self, image: Image.Image) -> list[Face]:
        import numpy as np

        scale = min(1.0, 1280 / max(image.size))  # YuNet is fast at ~1 MP and finds faces down to ~10 px
        small = image.convert("RGB")
        if scale < 1:
            small = small.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.BILINEAR)
        bgr = np.ascontiguousarray(np.asarray(small)[:, :, ::-1])
        with self._lock:
            if self._net is None:
                self._net = self._load()
            self._net.setInputSize(small.size)
            _, rows = self._net.detect(bgr)
        return [Face(r[0] / scale, r[1] / scale, r[2] / scale, r[3] / scale, float(r[14])) for r in (rows if rows is not None else [])]


def largest(faces: list[Face]) -> Face | None:
    return max(faces, key=lambda f: f.area, default=None)


def crop_box(face: Face, width: int, height: int, margin: float = MARGIN) -> tuple[int, int, int, int]:
    """Square (left, top, right, bottom) around the face, shifted to stay inside the image."""
    side = min(round(max(face.w, face.h) * margin), width, height)
    cx, cy = face.x + face.w / 2, face.y + face.h / 2
    left = min(max(0, round(cx - side / 2)), width - side)
    top = min(max(0, round(cy - side / 2)), height - side)
    return left, top, left + side, top + side


def blend_mask(side: int) -> Image.Image:
    """Soft ellipse: the re-rendered face fades into the original towards the crop edges."""
    mask = Image.new("L", (side, side), 0)
    inset = round(side * 0.08)
    ImageDraw.Draw(mask).ellipse([inset, inset, side - inset, side - inset], fill=255)
    return mask.filter(ImageFilter.GaussianBlur(max(1, side * 0.06)))


def paste_back(image: Image.Image, face: Image.Image, box: tuple[int, int, int, int]) -> Image.Image:
    side = box[2] - box[0]
    out = image.convert("RGB").copy()
    out.paste(face.convert("RGB").resize((side, side), Image.Resampling.LANCZOS), box[:2], blend_mask(side))
    return out
