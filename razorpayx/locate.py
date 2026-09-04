"""Read the carrier back, and ask it whether the page was edited and where.

The signal is the carrier itself. Every 8x8 block holds one bit of a payload
that survives locally destroyed blocks, because it is repeated across the page
and majority-voted. So the payload can be recovered from a damaged page, and
every block then asked whether it still agrees with what was recovered.
Recompression disagrees thinly and independently, everywhere. An edit destroys
a contiguous patch.

Which statistic is asked matters more than it looks, and the first one tried
was the wrong one. Peak local density over the page's own mean — an amplitude
— does not separate: a photograph of a screen concentrates damage 22x and the
weakest forgery 13x, so a detector built on it would call honest photographs
forged. That measurement stands, and is why `locate` is a pointer that never
decides anything.

The difference between an edit and recompression is not amplitude but shape,
and the largest connected patch measures shape. Over 48 honest journeys and 32
edits, honest pages produced a blob of 0 or exactly 4 and never more, while
edits produced 6 to 27. Four is structural rather than lucky: after a 2x2
opening the smallest surviving component is one 2x2 block, so an honest page
holds at most one isolated cluster and an edit leaves a real patch. That is
what `inspect_carrier` decides on, and it is the only thing in this module
allowed to decide anything.

What it cannot do is read a page whose payload will not come back — a heavy
downscale, or a messaging-app re-encode, where recovery needs the registry
rather than a direct read. Those return measurable=False and make no claim,
because a detector that reports "I could not look" as "nothing is wrong" is
worse than one that declines to answer.
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


#: Largest connected patch of disagreeing carrier blocks, after a 2x2 opening,
#: above which a page is called edited.
#:
#: Measured over 48 honest journeys and 32 edits on rendered advices. Honest
#: pages produced a blob of 0 (30 times) or exactly 4 (18 times) and never
#: more; edits produced 6 to 27. Four is not a coincidence — the opening's
#: smallest surviving component is one 2x2 block, so an honest page has at
#: most one isolated cluster, while an edit leaves a patch.
#:
#: Set at the observed floor of the edited range rather than midway. The two
#: errors are not equal: missing a smaller edit costs one consignment of
#: goods, and calling an honest payer's advice forged costs them the customer
#: they were trying to pay. The margin belongs on the honest side.
EDIT_BLOB_THRESHOLD = 6


@dataclass(frozen=True)
class CarrierFinding:
    """What the carrier's own error pattern says about a page."""

    #: Whether the payload could be recovered at all. False means no claim is
    #: being made — not that the page is clean.
    measurable: bool
    #: Largest connected patch of disagreeing blocks, after opening.
    blob: int
    #: Fraction of carrier blocks disagreeing across the whole page.
    background_rate: float
    #: Where that patch is, when there is one.
    region: Region | None

    @property
    def edited(self) -> bool:
        return self.measurable and self.blob >= EDIT_BLOB_THRESHOLD


def inspect_carrier(image: np.ndarray, *, window: int = WINDOW) -> CarrierFinding:
    """Ask the carrier whether this page was edited, and where.

    This is the question the whole-page fingerprint cannot answer. That
    fingerprint is 128 bits of global structure and its tolerance — the thing
    that lets a signature survive a messaging app — is the same tolerance that
    absorbs a repainted figure: a measured 4.1% edit passed as authentic on one
    page and was caught on another, because size is not what decides.

    The carrier is a different signal and answers a different question. Every
    8x8 block holds one bit of a payload that survives locally destroyed blocks
    because it is repeated and majority-voted, so the payload is recovered from
    the damaged page and every block asked whether it still agrees.
    Recompression disagrees thinly and independently. An edit destroys a
    contiguous patch. That is a difference of shape, not of amount, which is
    why measuring amplitude — peak density over the mean — did not separate
    them and measuring the largest connected patch does.

    A payload that cannot be recovered returns measurable=False. That happens
    for a heavy downscale or a messaging-app re-encode, where recovery needs
    the registry rather than a direct read. No claim is made there, because a
    detector that treats "I could not look" as "I saw nothing wrong" is worse
    than one that declines.
    """
    bits = payload_bits_for(image)
    if bits is None:
        return CarrierFinding(measurable=False, blob=0, background_rate=0.0, region=None)

    grid = disagreement_map(image, bits)
    if grid.size == 0:
        return CarrierFinding(measurable=False, blob=0, background_rate=0.0, region=None)

    background = float(grid.mean())
    binary = (grid > 0.5).astype(np.uint8)
    # Opening drops lone blocks and keeps solid patches, which is the whole
    # distinction being measured.
    opened = cv2.morphologyEx(binary, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    blob = int(stats[1:, cv2.CC_STAT_AREA].max()) if count > 1 else 0

    return CarrierFinding(
        measurable=True,
        blob=blob,
        background_rate=background,
        region=locate(image, bits, window=window),
    )


def locate_in_file(path: str | Path, *, window: int = WINDOW) -> Region | None:
    """Convenience: read an image, recover its payload, and point."""
    image = u.read_image(path)
    bits = payload_bits_for(image)
    if bits is None:
        return None
    return locate(image, bits, window=window)
