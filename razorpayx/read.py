"""Read the printed values back off an advice.

Why reading, and not comparing pixels
-------------------------------------
Three pixel-based approaches were built and measured against a repainted
amount (29,30,217 -> 99,30,217, 1.98% of the page) that had then been sent
through a messaging app. All three failed, for the same reason:

  1. The engine's whole-page fingerprint returned AUTHENTIC. Its tolerance is
     what lets a signature survive recompression, and a 2% edit sits inside it.
  2. Per-zone perceptual hashing: JPEG q95 moved the amount field's hash 41
     bits; the forgery moved it 30. Honest compression beat the forgery.
  3. Per-zone pixel differencing: on a WhatsApp copy, compression noise across
     every zone measured 0.069 while the forgery contributed 0.047. The signal
     sat below the noise floor.

The common cause is that lossy compression damages glyph *appearance* more
than a forgery does. What it does not damage is glyph *identity* — a person
can still read a blurry screenshot, and a 9 stays a 9. So the way through is
to recover the characters rather than the pixels.

Why a glyph matcher rather than an OCR engine
---------------------------------------------
This is not general text recognition. RazorpayX renders these advices itself,
so the typeface, the point size and the pixel position of every field are all
known before a single document is read. That turns the problem from "what
does this say" into "which of these known glyphs is this", which template
matching answers deterministically, in a few megabytes, with no model to ship
and no inference to pay for. It also fits the 256 MB container the free tier
allows, where torch is not an option.

It reports a confidence per character, so a read that has degraded past
usefulness is visible as a low score rather than as a confident wrong answer —
which matters, because a wrong read on a genuine advice is a false accusation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw

from .fonts import font

# Characters that appear in the fields worth checking. Deliberately small:
# every glyph added is another chance to confuse a 0 for an O.
DIGITS = "0123456789,."
ALNUM = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,-/&"

#: Every glyph is normalised to this box before matching.
CELL = 32


@dataclass(frozen=True)
class ReadResult:
    """What the reader made of one field."""

    text: str
    #: Mean template correlation across matched characters, 0..1.
    confidence: float
    #: Per-character scores, for spotting a single bad glyph.
    scores: tuple[float, ...] = ()

    @property
    def usable(self) -> bool:
        """Whether this read is worth acting on.

        Below this the reader is guessing, and a guess that disagrees with the
        signed value would accuse an honest payer of forgery.
        """
        return self.confidence >= 0.55


def _normalise(patch: np.ndarray) -> np.ndarray:
    """Fit one glyph into a fixed cell, preserving aspect ratio."""
    h, w = patch.shape
    if h == 0 or w == 0:
        return np.zeros((CELL, CELL), np.float32)
    scale = (CELL - 6) / max(h, w)
    resized = cv2.resize(
        patch, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
        interpolation=cv2.INTER_AREA,
    )
    canvas = np.zeros((CELL, CELL), np.float32)
    rh, rw = resized.shape
    top, left = (CELL - rh) // 2, (CELL - rw) // 2
    canvas[top:top + rh, left:left + rw] = resized
    total = canvas.sum()
    return canvas / total if total else canvas


@lru_cache(maxsize=16)
def _templates(
    alphabet: str, size: int, bold: bool, mono: bool = False
) -> tuple[tuple[str, np.ndarray], ...]:
    """Render each character once and keep its normalised bitmap.

    `mono` is not optional decoration. The UTR and the account number are
    printed in a monospaced face, and matching those against proportional
    templates read every 1 as a 2 — on a pristine, uncompressed file. Every
    genuine advice in the first benchmark run was called a forgery because of
    it. The templates have to be rendered in the same face the document was.
    """
    built: list[tuple[str, np.ndarray]] = []
    face = font(size, bold=bold, mono=mono)
    for char in alphabet:
        if char == " ":
            continue
        image = Image.new("L", (size * 3, size * 3), 0)
        ImageDraw.Draw(image).text((size, size // 2), char, font=face, fill=255)
        arr = np.array(image)
        ys, xs = np.nonzero(arr > 40)
        if len(xs) == 0:
            continue
        glyph = arr[ys.min():ys.max() + 1, xs.min():xs.max() + 1].astype(np.float32)
        built.append((char, _normalise(glyph)))
    return tuple(built)


def _segment(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Character boxes, left to right.

    Connected components rather than a projection profile: after a downscale
    the gaps between characters narrow, but proportional text still leaves
    them disconnected, while a projection profile starts merging columns as
    soon as any ink overlaps horizontally.
    """
    count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    boxes = []
    height = binary.shape[0]
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        # Drop specks and rules; keep anything with the proportions of a glyph.
        if area < 8 or h < height * 0.12 or w > binary.shape[1] * 0.5:
            continue
        boxes.append((x, y, w, h))
    return sorted(boxes, key=lambda b: b[0])


def read_field(
    image: np.ndarray,
    box: tuple[int, int, int, int],
    *,
    size: int,
    bold: bool = False,
    alphabet: str = DIGITS,
    mono: bool = False,
    canon: tuple[int, int] = (1000, 1400),
) -> ReadResult:
    """Read one field's text out of a full advice image.

    `box` is in the canonical frame; the image is resized to that frame first
    so a rescaled or forwarded copy still lines up.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    gray = cv2.resize(gray, canon, interpolation=cv2.INTER_AREA)

    left, top, right, bottom = box
    patch = gray[top:bottom, left:right]
    if patch.size == 0:
        return ReadResult("", 0.0)

    # Upscale before thresholding: the glyphs may have arrived from a 960px
    # copy, and Otsu on a blurred small patch loses thin strokes.
    patch = cv2.resize(patch, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    patch = cv2.GaussianBlur(patch, (3, 3), 0)
    _, binary = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)

    templates = _templates(alphabet, size * 2, bold, mono)
    chars: list[str] = []
    scores: list[float] = []
    previous_right: int | None = None

    for x, y, w, h in _segment(binary):
        glyph = _normalise(binary[y:y + h, x:x + w].astype(np.float32))
        best_char, best_score = "", -1.0
        for char, template in templates:
            score = float((glyph * template).sum() / (
                np.linalg.norm(glyph) * np.linalg.norm(template) + 1e-9))
            if score > best_score:
                best_char, best_score = char, score
        # A wide gap is a space, and spaces carry meaning in a beneficiary name.
        if previous_right is not None and x - previous_right > w * 0.9:
            chars.append(" ")
        chars.append(best_char)
        scores.append(best_score)
        previous_right = x + w

    if not scores:
        return ReadResult("", 0.0)
    return ReadResult("".join(chars).strip(), float(np.mean(scores)), tuple(scores))
