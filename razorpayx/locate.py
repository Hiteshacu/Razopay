"""Point at the part of the page that was edited.

Deliberately separate from the decision. `check` already says whether an
advice was altered, at full recall, by reading the printed characters and
comparing them to the record. This module is never asked that question, and
the distinction is what makes it work.

Detection needs a threshold no honest copy ever crosses. Measured on the
evaluation corpus, no such threshold exists for this signal: a photo of a
screen concentrates carrier damage 22x above its own mean, while the weakest
forgery concentrates it 13x. Used as a detector it would call honest
photographs forgeries. Used as a pointer, given that something is already
known to be wrong, it is an argmax over the page, and an argmax has no
threshold to be wrong about. On the same corpus it put the peak on a repainted
field in 30 of 30 forgeries, including the single changed digit.

The signal is the carrier. Every 8x8 block holds one bit of the payload, and
the payload survives locally destroyed blocks because it is repeated across
the page and majority-voted. So the payload can still be recovered from an
edited page, and every block can then be asked whether it still agrees with
what was recovered. Repainting a field destroys the carrier in a contiguous
patch. Recompression damages it thinly, everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

import utils as u
from watermark_extractor import _votes_per_block

#: Side of the averaging window, in 8x8 blocks. Seven blocks is 56 pixels,
#: which is about the height of a printed value on these advices — wide enough
#: to average out one unlucky block, narrow enough not to blur a field into
#: its neighbour.
WINDOW = 7


@dataclass(frozen=True)
class Region:
    """Where the damage is concentrated, in the coordinates of the image given."""

    left: int
    top: int
    right: int
    bottom: int
    #: The peak block itself, in pixels. This is the answer; the box around it
    #: is for drawing. Kept separately because the box is clamped to the page,
    #: and near an edge its centre is no longer where the peak actually was —
    #: scoring against the clamped centre marked correct localisations wrong.
    peak_x: int
    peak_y: int
    #: Peak local disagreement over the page's own mean. Comparative, not
    #: absolute: it says this patch is unlike the rest of *this* page, which
    #: is the only comparison that survives an image already damaged all over.
    concentration: float
    #: Fraction of carrier blocks that disagree across the whole page.
    background_rate: float

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


def disagreement_map(image: np.ndarray, payload_bits: np.ndarray) -> np.ndarray:
    """Per carrier block: 1 where it contradicts the recovered payload."""
    cropped = u.crop_to_block_grid(image)
    luminance = cv2.cvtColor(cropped, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)

    votes, votes_per_pair = _votes_per_block(luminance, u.WATERMARK_EMBED_COEFFICIENT_PAIRS)
    rows = luminance.shape[0] // u.BLOCK_SIZE
    cols = luminance.shape[1] // u.BLOCK_SIZE
    total = rows * cols

    permutation = u.watermark_permutation(total)
    repetition = u.watermark_repetition(total, payload_bits.size)
    carriers = permutation[: repetition * payload_bits.size].reshape(repetition, payload_bits.size)

    expected = payload_bits[None, :].repeat(repetition, axis=0).astype(bool)
    disagrees = (votes[carriers] > votes_per_pair / 2) != expected

    grid = np.zeros(total, dtype=np.float32)
    grid[carriers.ravel()] = disagrees.ravel().astype(np.float32)
    return grid.reshape(rows, cols)


def locate(image: np.ndarray, payload_bits: np.ndarray, *, window: int = WINDOW) -> Region | None:
    """The densest patch of carrier damage, or None if there is no carrier.

    Returns a region for any image, including an untouched one — it is a
    pointer, not a verdict, and it is the caller's job to have established
    that something is wrong before showing a reader where.
    """
    grid = disagreement_map(image, payload_bits)
    if grid.size == 0:
        return None

    background = float(grid.mean())
    density = cv2.blur(grid, (window, window))
    _, peak, _, (px, py) = cv2.minMaxLoc(density)

    half = window // 2
    left = max(0, px - half) * u.BLOCK_SIZE
    top = max(0, py - half) * u.BLOCK_SIZE
    right = min(grid.shape[1], px + half + 1) * u.BLOCK_SIZE
    bottom = min(grid.shape[0], py + half + 1) * u.BLOCK_SIZE

    return Region(
        left=int(left),
        top=int(top),
        right=int(right),
        bottom=int(bottom),
        peak_x=int(px * u.BLOCK_SIZE + u.BLOCK_SIZE // 2),
        peak_y=int(py * u.BLOCK_SIZE + u.BLOCK_SIZE // 2),
        concentration=float(peak / background) if background > 0 else 0.0,
        background_rate=background,
    )


def payload_bits_for(image: np.ndarray) -> np.ndarray | None:
    """Recover the payload from an image so its own blocks can be judged.

    Recovered from the image in hand rather than from the issuing record, so
    localisation needs nothing but the file — and because a payload that
    cannot be recovered means there is no carrier left to reason about, which
    is a `None` rather than a guess.
    """
    from watermark_extractor import extract_watermark_bundle

    try:
        fingerprint, signature_b64 = extract_watermark_bundle(image)
    except Exception:
        return None
    payload = u.build_watermark_payload(u.signature_from_base64(signature_b64), fingerprint)
    return u.bytes_to_bits(payload)


def locate_in_file(path: str | Path, *, window: int = WINDOW) -> Region | None:
    """Convenience: read an image, recover its payload, and point."""
    image = u.read_image(path)
    bits = payload_bits_for(image)
    if bits is None:
        return None
    return locate(image, bits, window=window)
