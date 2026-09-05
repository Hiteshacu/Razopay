"""Read the carrier back, and ask it whether the page was edited and where.

The signal is the carrier itself. Every 8x8 block holds one bit of a payload
that survives locally destroyed blocks, because it is repeated across the page
and majority-voted. So the payload can be recovered from a damaged page, and
every block then asked whether it still carries what was recovered.
Recompression weakens blocks thinly and independently, everywhere. An edit
flattens a contiguous patch of them.

Two statistics were wrong before this one, and both are worth keeping in view.

Peak local density over the page's own mean — an amplitude — does not separate
anything: a photograph of a screen concentrates damage 22x and the weakest
forgery 13x, so a detector built on it would call honest photographs forged.
That is why `locate` is a pointer that never decides anything.

Sign disagreement — counting the blocks whose bit now reads back wrong — is
better, and it is what this module decided on for a while. It catches an edit
that covers a whole field, and it misses small ones almost completely: 33 of 65
measurable edits went through, including erasing a single digit from the
headline amount. The reason is in what an edit does to a block. Painting over
a value leaves a flat block whose two mid-frequency coefficients are both near
zero, so which one is larger is a coin toss: about half of the blocks inside
an erased digit still read back correctly, the patch arrives as speckle rather
than a solid piece, and a 2x2 opening dissolves it.

What decides now is the *margin*: how far each block's coefficient pair still
leans the way the payload says it should. The embedder pushes every pair apart
by at least 36 DCT units, and nothing enforces that on pixels a forger paints,
so the margin collapses across every block they touched whether they erased
the digit or typed a new one over it. Measured against the page's own median
margin — relative, so a dimmed or brightened or heavily recompressed copy is
judged against itself — the same edits become solid patches of 10 to 580
blocks while honest journeys reach 8 at worst. On a held-out set that is 0
false accusations in 72 honest copies and 8 misses in 104 edits, against 52
misses for sign disagreement on the same files. `inspect_carrier` decides on
it, and it is the only thing in this module allowed to decide anything.

The 8 that still get through are one case: a single digit in the small
secondary amount row, replaced by a same-width glyph. Drawing text back in
restores contrast, which puts those blocks back on the coin toss, and three
blocks by three is too little to survive the opening at half strength. An edit
to the headline the reader actually looks at is caught at every size tested.

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
    #: Peak local weakness over the page's own mean. Comparative, not
    #: absolute: it says this patch is unlike the rest of *this* page, which
    #: is the only comparison that survives an image already damaged all over.
    concentration: float
    #: Fraction of carrier blocks weakened across the whole page.
    background_rate: float
    #: How many carrier blocks this patch covers. What decides whether it is
    #: an edit at all, and what the regions are ordered by.
    blocks: int = 0

    @property
    def box(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.right, self.bottom)


def carrier_margin(image: np.ndarray, payload_bits: np.ndarray) -> np.ndarray:
    """Per carrier block: how hard it still leans the way the payload says.

    The embedder does not merely set the sign of each coefficient pair, it
    pushes the pair apart by at least `strength` — 36 DCT units, plus a little
    more on a detailed block. So every block of a signed page carries a margin
    of roughly that size in a known direction, and nothing whatsoever enforces
    that on pixels a forger paints.

    Reading the sign alone, which is what the extractor does and what this
    module used to do, throws that away. It matters because of how an edit
    fails. Painting over a value replaces a modulated block with a flat one,
    and a flat block's two mid-frequency coefficients are both near zero — so
    its sign is a coin toss. Half the blocks inside an erased digit still
    "agree" by luck, the patch arrives as speckle rather than a solid piece,
    and a 2x2 opening dissolves it. Measured: erasing one digit of the headline
    amount left a largest patch of 0 to 8 blocks, inside the range honest JPEGs
    produce, so it was called clean.

    The margin does not toss a coin. It collapses to about zero across every
    block the forger touched, whether they erased the digit or typed a new one
    over it, which turns the same edit into a solid patch.

    NaN marks a block no bit was written to: the payload is repeated a whole
    number of times and the remainder blocks carry nothing to be judged by.
    """
    cropped = u.crop_to_block_grid(image)
    luminance = cv2.cvtColor(cropped, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)

    blocks = u.image_to_blocks(luminance) - 128.0
    coefficients = (u.DCT_MATRIX @ blocks @ u.DCT_MATRIX.T).reshape(-1, u.BLOCK_SIZE, u.BLOCK_SIZE)

    rows = luminance.shape[0] // u.BLOCK_SIZE
    cols = luminance.shape[1] // u.BLOCK_SIZE
    total = rows * cols

    permutation = u.watermark_permutation(total)
    repetition = u.watermark_repetition(total, payload_bits.size)
    carriers = permutation[: repetition * payload_bits.size].reshape(repetition, payload_bits.size)

    # True where the payload wants the first coefficient of the pair to be the
    # larger one, which is exactly the convention the embedder writes under.
    wants_a_larger = payload_bits[None, :].repeat(repetition, axis=0).astype(bool)

    gaps = np.zeros(carriers.shape, dtype=np.float32)
    for (a_row, a_col), (b_row, b_col) in u.WATERMARK_EMBED_COEFFICIENT_PAIRS:
        a = coefficients[:, a_row, a_col][carriers]
        b = coefficients[:, b_row, b_col][carriers]
        gaps += np.where(wants_a_larger, a - b, b - a)
    gaps /= len(u.WATERMARK_EMBED_COEFFICIENT_PAIRS)

    grid = np.full(total, np.nan, dtype=np.float32)
    grid[carriers.ravel()] = gaps.ravel()
    return grid.reshape(rows, cols)


#: A block is called weak when its margin falls below this fraction of the
#: page's own median margin.
#:
#: Relative rather than absolute, and that is the whole of what makes it usable
#: on a copy that has been through something. A hard cut-off in DCT units gets
#: the small edits right and then accuses honest pages that have been dimmed,
#: brightened or heavily recompressed, because those shrink the margin
#: everywhere at once: a 3% brightness lift clips the near-white paper the
#: carrier is written on and drops the page median from 22 to 2, at which point
#: every block on a perfectly honest page sits under any fixed threshold.
#:
#: Measured against the page's own median, that same brightened page produces a
#: largest weak patch of 0 to 6 — because what changed was the whole page, not
#: one part of it. An edit is defined by being unlike the rest of its own page,
#: and this is the only comparison that says so.
WEAK_MARGIN_FRACTION = 0.35

#: Below this page median margin, in DCT units, no claim is made at all.
#:
#: The fraction above is a ratio, and a ratio of something that has essentially
#: vanished is noise. A page whose carrier has been flattened this far is one
#: the detector cannot see into, and saying so is the honest answer.
MIN_PAGE_MARGIN = 1.5


def carrier_weakness(image: np.ndarray, payload_bits: np.ndarray) -> tuple[np.ndarray, float]:
    """Blocks whose carrier has been flattened, and the page's own margin.

    Returns a 0/1 grid over blocks and the median margin it was judged
    against. A margin below MIN_PAGE_MARGIN means the page cannot be judged;
    callers check for it rather than reading the grid.
    """
    margin = carrier_margin(image, payload_bits)
    written = ~np.isnan(margin)
    if not written.any():
        return np.zeros(margin.shape, dtype=np.uint8), 0.0

    page_margin = float(np.nanmedian(margin))
    weak = written & (margin < page_margin * WEAK_MARGIN_FRACTION)
    return weak.astype(np.uint8), page_margin


def disagreement_map(image: np.ndarray, payload_bits: np.ndarray) -> np.ndarray:
    """Per carrier block: 1 where its sign contradicts the recovered payload.

    Kept because it is the plainest statement of what the carrier is for, and
    still what `read` and the field check reason about. It is no longer what
    decides whether a page was edited — see `carrier_margin` for why the sign
    alone loses half of a small edit.
    """
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


#: A connected patch smaller than this is not reported as a region.
#:
#: Four is what an honest page produces at most — the smallest component a 2x2
#: opening can leave — so anything at or below it is the scatter that
#: recompression makes everywhere, not an edit. Kept below
#: EDIT_BLOB_THRESHOLD on purpose: what decides is the largest patch, and once
#: a page has been called edited the reader is better served by seeing every
#: piece of it than by having the smaller ones hidden.
MIN_REGION_BLOCKS = 5

#: How far apart two torn fragments may be and still count as one edit, in
#: blocks: (vertical, horizontal).
#:
#: Deliberately not square, because an edited field is not square. A printed
#: value is about 62px tall and several hundred wide — eight blocks by seventy
#: — so its fragments land tens of blocks apart across the line and only a few
#: apart down it. A square bridge wide enough to join them vertically would
#: swallow the field above and below; this one reaches along a line without
#: reaching to the next.
BRIDGE_BLOCKS = (3, 25)

#: Horizontal gap, in pixels, below which two boxes on the same line are folded
#: into one. A printed value can tear either side of a run of blocks that
#: happened to survive, leaving a hole the dilation does not quite close.
MERGE_GAP_PX = 120


def locate_all(
    image: np.ndarray,
    payload_bits: np.ndarray,
    *,
    min_blocks: int = MIN_REGION_BLOCKS,
    pad: int = 2,
) -> list[Region]:
    """Every flattened patch of carrier, largest first.

    One box was not enough, and it was the wrong shape as well as the wrong
    count. Reporting the densest fixed window meant a 7x7 square drawn wherever
    the peak fell, so an edit spanning a whole row of the page was marked with
    a small square somewhere inside it while the rest went unmarked — and a
    second edit elsewhere was never mentioned at all.

    Each patch is now its own connected component, and its box is that
    component's own extent rather than a fixed window, padded slightly so the
    highlight reads as covering the change rather than sitting inside it.
    """
    weak, page_margin = carrier_weakness(image, payload_bits)
    if weak.size == 0 or page_margin < MIN_PAGE_MARGIN:
        return []

    grid = weak.astype(np.float32)
    background = float(grid.mean())
    opened = cv2.morphologyEx(weak, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))

    # Bridge the gaps inside one edit before counting patches.
    #
    # A repainted field does not tear the carrier evenly: some blocks inside it
    # still happen to decode correctly, so the damage arrives as a handful of
    # fragments a few blocks apart. Taken literally that is eighteen patches
    # for three edits, and eighteen overlapping boxes drawn on the page is
    # worse than one — the reader cannot tell how many things were changed.
    #
    # Dilating joins fragments belonging to the same field. The kernel is
    # wide and short because the thing being rejoined is: a printed value runs
    # along a line, so its fragments are far apart across the page and close
    # together down it.
    merged = cv2.dilate(opened, np.ones(BRIDGE_BLOCKS, np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)

    regions: list[Region] = []
    for index in range(1, count):
        # Counted on the undilated map: dilation is there to group fragments,
        # not to inflate how much damage was found.
        area = int(opened[labels == index].sum())
        if area < min_blocks:
            continue
        x = int(stats[index, cv2.CC_STAT_LEFT])
        y = int(stats[index, cv2.CC_STAT_TOP])
        w = int(stats[index, cv2.CC_STAT_WIDTH])
        h = int(stats[index, cv2.CC_STAT_HEIGHT])

        left = max(0, x - pad) * u.BLOCK_SIZE
        top = max(0, y - pad) * u.BLOCK_SIZE
        right = min(grid.shape[1], x + w + pad) * u.BLOCK_SIZE
        bottom = min(grid.shape[0], y + h + pad) * u.BLOCK_SIZE

        # Density inside this patch against the page's own error rate, which
        # is the only comparison that survives an image damaged all over.
        patch = grid[y:y + h, x:x + w]
        density = float(patch.mean()) if patch.size else 0.0

        regions.append(Region(
            left=int(left), top=int(top), right=int(right), bottom=int(bottom),
            peak_x=int((x + w / 2) * u.BLOCK_SIZE),
            peak_y=int((y + h / 2) * u.BLOCK_SIZE),
            concentration=float(density / background) if background > 0 else 0.0,
            background_rate=background,
            blocks=area,
        ))

    return _merge_overlapping(regions)


def _merge_overlapping(regions: list[Region]) -> list[Region]:
    """Fold together regions whose boxes intersect.

    The dilation joins fragments along a line, but a fragment sitting directly
    above or below the rest of its field is reached by neither the horizontal
    bridge nor the short vertical one — so it survives as its own component and
    is drawn as a second box inside the first. Two overlapping highlights are
    one region to whoever is looking at them.

    Blocks add up across a merge, so the count still says how much of the
    carrier was torn rather than how many pieces it arrived in.
    """
    ordered = sorted(regions, key=lambda r: -r.blocks)
    merged: list[Region] = []
    for candidate in ordered:
        for index, kept in enumerate(merged):
            # Near counts as overlapping, and only along the line. Two boxes
            # on the same row with a small gap between them are one changed
            # value to whoever is looking; two boxes in the same column are
            # two different fields, so the vertical tolerance stays at zero.
            near = not (
                candidate.right + MERGE_GAP_PX <= kept.left
                or candidate.left >= kept.right + MERGE_GAP_PX
                or candidate.bottom <= kept.top
                or candidate.top >= kept.bottom
            )
            if near:
                left, top = min(kept.left, candidate.left), min(kept.top, candidate.top)
                right = max(kept.right, candidate.right)
                bottom = max(kept.bottom, candidate.bottom)
                merged[index] = Region(
                    left=left, top=top, right=right, bottom=bottom,
                    peak_x=(left + right) // 2, peak_y=(top + bottom) // 2,
                    concentration=max(kept.concentration, candidate.concentration),
                    background_rate=kept.background_rate,
                    blocks=kept.blocks + candidate.blocks,
                )
                break
        else:
            merged.append(candidate)

    merged.sort(key=lambda r: -r.blocks)
    return merged


def locate(image: np.ndarray, payload_bits: np.ndarray, *, window: int = WINDOW) -> Region | None:
    """The largest flattened patch, or None if there is none worth reporting."""
    found = locate_all(image, payload_bits)
    return found[0] if found else None


def payload_bits_for(image: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Recover the payload, and return the image it was recovered from.

    Both, and that is the point. The extractor retries at several scales — a
    forwarded copy is often a resized copy, and the carrier only reads back
    when the 8x8 grid lines up with the one it was written on. So the payload
    may well come from a rescaled version of what was uploaded.

    Returning only the bits, as this did, silently paired them with the
    original: the disagreement map then compared a payload recovered at 0.5x
    against blocks measured at 1.0x, so every block disagreed and the result
    was noise dressed up as a finding. The scale has to travel with the bits.

    None means the payload could not be recovered at any scale — no carrier
    left to reason about, which is a refusal rather than a guess.
    """
    from watermark_extractor import (
        RESIZE_RECOVERY_FACTORS,
        _extract_watermark_bundle_from_array,
    )

    for factor in RESIZE_RECOVERY_FACTORS:
        candidate = image
        if factor != 1.0:
            height, width = image.shape[:2]
            candidate = cv2.resize(
                image,
                (int(round(width * factor)), int(round(height * factor))),
                interpolation=cv2.INTER_CUBIC,
            )
        try:
            fingerprint, signature_b64 = _extract_watermark_bundle_from_array(candidate)
        except Exception:
            continue
        payload = u.build_watermark_payload(u.signature_from_base64(signature_b64), fingerprint)
        return u.bytes_to_bits(payload), candidate
    return None


#: Largest connected patch of weakened carrier blocks, after a 2x2 opening, at
#: or above which a page is called edited.
#:
#: Nine, measured on the weak map. The number moved with the signal underneath
#: it: it was 7 when the map was sign disagreement, and that pairing let 33 of
#: 65 measurable edits through — every one of them a small edit, because a
#: repainted digit only flips half the signs it touches. On the margin map the
#: same edits produce solid patches of 10 to 580 blocks, and honest journeys
#: reach 8 at the very worst (a sharpened copy; JPEG down to quality 35, a
#: brightened page and a dimmed one all sit at 4 or below).
#:
#: The fraction the weak map is cut at barely matters — anything from 0.20 to
#: 0.50 of the page median gives the same answer on every sample — so the one
#: number that does matter is this one.
#:
#: If it has to move again it should move up. The two errors are not equal:
#: missing a smaller edit costs one consignment of goods, while calling an
#: honest payer's advice forged costs them the customer they were paying.
EDIT_BLOB_THRESHOLD = 9


@dataclass(frozen=True)
class CarrierFinding:
    """What the carrier's own error pattern says about a page."""

    #: Whether the page could be judged at all. False means no claim is being
    #: made — not that the page is clean. Either the payload did not come back,
    #: or the carrier is too flattened everywhere to say anything about one
    #: part of the page.
    measurable: bool
    #: Largest connected patch of weakened blocks, after opening.
    blob: int
    #: Fraction of carrier blocks weakened across the whole page.
    background_rate: float
    #: Every flattened patch, largest first. Empty when nothing crosses the floor.
    regions: tuple[Region, ...] = ()
    #: Width and height of the image the carrier was actually read from, which
    #: is not the uploaded size when recovery succeeded at another scale. Boxes
    #: are in these coordinates, so a caller drawing them needs this to convert.
    read_width: int = 0
    read_height: int = 0

    @property
    def region(self) -> Region | None:
        return self.regions[0] if self.regions else None

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
    recovered = payload_bits_for(image)
    if recovered is None:
        return CarrierFinding(measurable=False, blob=0, background_rate=0.0)
    bits, read_image = recovered

    weak, page_margin = carrier_weakness(read_image, bits)
    if weak.size == 0 or page_margin < MIN_PAGE_MARGIN:
        # The carrier is there — the payload came back — but flattened far
        # enough that a patch of flattened blocks says nothing about which part
        # of the page a forger touched. Declining is the honest answer.
        return CarrierFinding(measurable=False, blob=0, background_rate=0.0)

    background = float(weak.mean())
    # Opening drops lone blocks and keeps solid patches, which is the whole
    # distinction being measured.
    opened = cv2.morphologyEx(weak, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    count, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    blob = int(stats[1:, cv2.CC_STAT_AREA].max()) if count > 1 else 0

    height, width = read_image.shape[:2]
    return CarrierFinding(
        measurable=True,
        blob=blob,
        background_rate=background,
        regions=tuple(locate_all(read_image, bits)),
        read_width=int(width),
        read_height=int(height),
    )


def locate_in_file(path: str | Path, *, window: int = WINDOW) -> Region | None:
    """Convenience: read an image, recover its payload, and point."""
    image = u.read_image(path)
    recovered = payload_bits_for(image)
    if recovered is None:
        return None
    bits, read_image = recovered
    return locate(read_image, bits, window=window)
