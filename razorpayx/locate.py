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

How much of a page carries a bit at all turns out to matter as much as the
statistic. The payload is repeated at most eleven times however large the page
is, so a 1000x1400 advice writes a bit into 93% of its blocks while a 2000x2600
photograph of a letter writes into 31%. A window that cannot tell an unwritten
block from an intact one reads two thirds of a large page as evidence of
innocence, and a small edit falls apart inside it. The window is therefore
sized to the page's carrier density, which leaves dense pages exactly as they
were and halves the misses on large ones.

There is a floor under all of this, and on a large page a small edit sits on
it. RSA-PSS salts every signature, so signing one page twice writes two
different payloads into it and a different set of blocks ends up carrying each
bit. Signing the same letter eight times and making the same one-date edit each
time gives largest patches of 6, 8, 8, 10, 10, 14, 16 and 17, against 0 to 6 for
the untouched and sharpened copies of those same eight. The edit is real every
time; whether it clears the threshold depends on which blocks happened to carry
a bit near it. Anything smaller than a printed value is therefore a coin weighted
by the signing, not a measurement, and the numbers quoted here have that spread
in them.

The fix for that is not a threshold. It is carrying more bits on a large page:
the payload is repeated at most MAX_REPETITION times whatever the page size, so
a 2000x2600 scan leaves 69% of its blocks empty. Raising that cap changes how
every already-signed document reads back, so it needs a reader that tries both.

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


def carrier_weakness(
    image: np.ndarray, payload_bits: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Blocks whose carrier has been flattened, which blocks carry one, and
    the page's own margin.

    The written mask travels with the weak map because on a large page most
    blocks are not written at all, and morphology that cannot tell a block
    carrying nothing from a block carrying an intact bit reads the first as
    evidence of innocence. See `opened_weak`.

    A margin below MIN_PAGE_MARGIN means the page cannot be judged; callers
    check for it rather than reading the grid.
    """
    margin = carrier_margin(image, payload_bits)
    written = ~np.isnan(margin)
    if not written.any():
        empty = np.zeros(margin.shape, dtype=np.uint8)
        return empty, empty, 0.0

    page_margin = float(np.nanmedian(margin))
    weak = written & (margin < page_margin * WEAK_MARGIN_FRACTION)
    return weak.astype(np.uint8), written.astype(np.uint8), page_margin


#: How many blocks carrying a bit an opening window has to hold before the
#: patch under it counts as solid rather than as scatter.
#:
#: Four, because that is what a 2x2 opening asked for on the page this was
#: first measured on, and the point of the window sizing below is to keep
#: asking for the same thing as the page grows.
MIN_CORE_CARRIERS = 4

#: Expected carriers a window must hold before it is wide enough. Sized so a
#: page like the payout advice, where 93.5% of blocks carry a bit, still gets
#: the 2x2 window every threshold here was measured against.
_WINDOW_CARRIER_TARGET = 3.7


def opened_weak(weak: np.ndarray, written: np.ndarray) -> tuple[np.ndarray, float]:
    """Solid patches of flattened carrier, and the page's carrier density.

    An opening keeps a block only if it sits inside a solid piece, and that is
    the whole distinction being measured: recompression thins the carrier in
    scattered blocks, an edit flattens a contiguous piece of it. The trouble is
    what "solid" means when a third of the page carries no bit at all.

    The payload is repeated at most eleven times however large the page is, so
    the share of blocks carrying a bit falls as the page grows: 93.5% on a
    1000x1400 payout advice, 65% on a 1400x1750 scanned letter, 31% on a
    2000x2600 phone photograph of one. A fixed 2x2 opening treats every block
    carrying nothing as a block that is fine, so on those larger pages an edit
    arrives as a sieve and dissolves. Measured on letters at three sizes, on
    the same files: 18 of 21 edits went through on the development split and 32
    of 42 on the held-out one, and the ones that survived did so at the
    smallest size.

    So the window grows until it expects to hold as many carriers as a 2x2
    window held on the page this was calibrated on, and only blocks carrying a
    bit are allowed to vote. A window passes when every carrier under it is
    weak and there are at least MIN_CORE_CARRIERS of them, which on a dense
    page is exactly the old rule and on a sparse one is the same question asked
    over a wider patch of paper.

    Only the window that decides whether a patch is solid grows with the page.
    What puts the patch back together afterwards stays a 2x2, because that is a
    reconnection and not a measurement: dilating by the wide window instead
    inflates every unavoidable speck by its own area — sixteen blocks on the
    sparsest pages — and an honest letter then reads larger than a real edit of
    a date. Masking the result back down to blocks that carry a bit was also
    measured and is worse again, in the other direction: it shrinks every patch
    on a dense page and cost nine payout-advice edits for nothing.

    Measured across four splits, two page shapes: this pairing accuses nobody
    and misses 27 of 232 edits. A fixed 2x2 doing both jobs misses 61, almost
    all of them on the larger pages.
    """
    density = float(written.mean())
    if density <= 0:
        return np.zeros_like(weak), 0.0

    side = 2
    while side < 8 and side * side * density < _WINDOW_CARRIER_TARGET:
        side += 1

    kernel = np.ones((side, side), np.uint8)
    carriers_near = cv2.filter2D(written.astype(np.float32), -1, kernel,
                                 borderType=cv2.BORDER_CONSTANT)
    weak_near = cv2.filter2D(weak.astype(np.float32), -1, kernel,
                             borderType=cv2.BORDER_CONSTANT)

    core = ((carriers_near >= MIN_CORE_CARRIERS) & (weak_near >= carriers_near))
    reconnect = np.ones((2, 2), np.uint8)
    return cv2.dilate(core.astype(np.uint8), reconnect), density


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
    weak, written, page_margin = carrier_weakness(image, payload_bits)
    if weak.size == 0 or page_margin < MIN_PAGE_MARGIN:
        return []

    grid = weak.astype(np.float32)
    background = float(grid.mean())
    opened, _ = opened_weak(weak, written)

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
        # Counted on the undilated map: bridging is there to group fragments,
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


#: Largest connected patch of weakened carrier blocks, after the opening, at or
#: above which a page is called edited.
#:
#: Nine, measured over two corpora at once and on both their splits: payout
#: advices at 1000x1400, where 93% of blocks carry a bit, and scanned-letter
#: pages at 1400x1750 through 2000x2500, where a third or less do. Honest
#: journeys across all four reach 8 at the very worst — a sharpened copy — and
#: nine is the lowest value that accuses none of them.
#:
#: Eight was measured too. It costs one false accusation, on a sharpened advice,
#: and buys ten edits. Not taken: the errors are not equal, and the rule below
#: about which way this moves was written before there was a case for breaking
#: it.
#:
#: The number has moved twice, each time because the signal under it changed.
#: It was 7 against sign disagreement, which let 33 of 65 measurable edits
#: through; 9 against the margin map with a fixed 2x2 opening, which was right
#: for advices and let 16 of 21 letter edits through because most blocks of a
#: large page carry nothing and a fixed window reads them as intact.
#:
#: The fraction the weak map is cut at barely matters — anything from 0.20 to
#: 0.50 of the page median gives the same answer on every sample — so this and
#: the window sizing are the numbers that do.
#:
#: If it has to move again it should move up. The two errors are not equal:
#: missing a smaller edit costs one consignment of goods, while calling an
#: honest payer's advice forged costs them the customer they were paying.
EDIT_BLOB_THRESHOLD = 9

#: Share of the page inside reported regions, and how many regions, above which
#: the damage stops being an edit to part of a page and becomes something that
#: happened to all of it.
#:
#: Both conditions together, because either alone misfires. A single repainted
#: headline amount on a small advice covers 10% of it, which is why coverage
#: alone cannot be the test; an honest page occasionally produces two specks,
#: which is why a count alone cannot be either.
#:
#: Measured through the same path a caller uses. Honest journeys cover at most
#: 1% in at most 2 regions. Local edits reach 14.2% — a doubled headline amount
#: repaints both the hero and the table row of a small advice — but never in
#: more than 2 regions. A page an online "image text editor" has re-typeset
#: covers 38% to 67% in 6 to 10 regions.
#:
#: The coverage bar sits at 20% rather than just above 14.2% because the two
#: populations are far apart there and the cost of being wrong is asymmetric:
#: calling a real edit page-wide would soften language that should stay sharp.
PAGE_WIDE_COVERAGE = 0.20
PAGE_WIDE_REGIONS = 3


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
    #: Share of the page lying inside a reported region.
    coverage: float = 0.0

    @property
    def region(self) -> Region | None:
        return self.regions[0] if self.regions else None

    @property
    def edited(self) -> bool:
        return self.measurable and self.blob >= EDIT_BLOB_THRESHOLD

    @property
    def page_wide(self) -> bool:
        """Was this done to the whole page rather than to part of it?

        Worth telling apart because the two mean different things to whoever is
        holding the page, and because only one of them can be pointed at. An
        edit is somewhere; this is everywhere, and thirty boxes covering half a
        page tell a reader nothing they can act on.

        The usual cause is not a forger at all. An online image-text editor
        runs OCR over the page, erases the text it found and redraws it, then
        exports. Every redrawn line is new pixels, so the proof is broken along
        all of them — and there is no way to tell, from the carrier alone, that
        the editor redrew a line unchanged while a forger changed one. Both are
        the same act on the same pixels. What can be said is that the page is
        no longer the one that was signed, which is the answer either way.
        """
        return (self.edited
                and len(self.regions) >= PAGE_WIDE_REGIONS
                and self.coverage >= PAGE_WIDE_COVERAGE)


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

    weak, written, page_margin = carrier_weakness(read_image, bits)
    if weak.size == 0 or page_margin < MIN_PAGE_MARGIN:
        # The carrier is there — the payload came back — but flattened far
        # enough that a patch of flattened blocks says nothing about which part
        # of the page a forger touched. Declining is the honest answer.
        return CarrierFinding(measurable=False, blob=0, background_rate=0.0)

    background = float(weak.mean())
    # Opening drops lone blocks and keeps solid patches, which is the whole
    # distinction being measured, over a window sized to how much of this page
    # carries a bit at all.
    opened, _ = opened_weak(weak, written)
    count, _, stats, _ = cv2.connectedComponentsWithStats(opened, connectivity=8)
    blob = int(stats[1:, cv2.CC_STAT_AREA].max()) if count > 1 else 0

    height, width = read_image.shape[:2]
    regions = tuple(locate_all(read_image, bits))
    page_area = float(width * height)
    covered = sum((r.right - r.left) * (r.bottom - r.top) for r in regions)
    return CarrierFinding(
        measurable=True,
        blob=blob,
        background_rate=background,
        regions=regions,
        read_width=int(width),
        read_height=int(height),
        coverage=(covered / page_area) if page_area else 0.0,
    )


def locate_in_file(path: str | Path, *, window: int = WINDOW) -> Region | None:
    """Convenience: read an image, recover its payload, and point."""
    image = u.read_image(path)
    recovered = payload_bits_for(image)
    if recovered is None:
        return None
    bits, read_image = recovered
    return locate(read_image, bits, window=window)
