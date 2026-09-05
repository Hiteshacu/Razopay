"""Compare a document against the copy that was filed when it was signed.

Why this exists alongside the carrier
-------------------------------------
The carrier in `locate` answers a question the file can answer alone: has any
part of this page been repainted since it was signed. That is the right answer
for most of what arrives, and it needs no database, no lookup and no account.

It cannot answer the question a page which has been through an online image
editor asks. Those editors run OCR, erase every line of text they find and
redraw it, so the carrier is broken along all of them — and nothing in the
signature distinguishes a line the editor redrew unchanged from a line a forger
changed. Both are new pixels. Measured on such a page, the carrier reports 68%
to 100% of it as damaged, which is true and useless.

What separates them is the content, and the content can only be checked against
something. That something is the copy filed at signing time, which the object
store already holds. This module is that comparison: align the two, ask each
block whether it still shows the same thing, and report where it does not.

Why not glyph reading
---------------------
`read` recovers characters, and it is the better answer where it applies —
RazorpayX renders those advices itself, so the typeface and the position of
every field are known. Nothing is known about a scanned government circular in
Kannada, and a general OCR engine is both a large dependency and a source of
confident wrong answers on exactly the degraded copies that matter. Comparing
against the filed original needs no model and no assumption about the language,
the fonts or the layout.

Why block matching and not a pixel difference
---------------------------------------------
A straight difference reports everything: a JPEG re-encode, a resize, a
half-pixel shift from a redraw. The distinction wanted here is whether a block
still *shows* what it showed, so each block is matched against a small
neighbourhood of the reference rather than against the single pixel-aligned
block underneath it, and scored on the best match found. A line the editor
redrew a pixel to the left matches itself one pixel to the left. A changed
digit matches nothing.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .locate import BRIDGE_BLOCKS, Region, _merge_overlapping

#: Side of the comparison block, in pixels. Sixteen rather than the carrier's
#: eight: this is asking whether a block still shows the same thing, and eight
#: pixels of a printed page is often a single stroke, which matches too many
#: other single strokes to mean anything.
BLOCK = 16

#: How far, in pixels, a block may be found from where it was and still count
#: as the same block.
#:
#: Three. An editor that redraws a line does not put it back in exactly the
#: same place, and neither does a resize followed by a resize back. Larger
#: search windows start finding a different digit that happens to look like
#: the one being searched for, which is a miss rather than a false alarm and
#: therefore the direction that matters.
SEARCH = 3

#: Below this correlation with its best match in the reference, a block is
#: reporting different content.
#:
#: Measured over honest journeys of a signed page — JPEG down to quality 55, a
#: resize round trip, an editor's re-typeset of the whole page — against pages
#: with one field changed. Honest blocks with any ink in them score above 0.86
#: even when redrawn; a changed digit scores below 0.5. The bar sits low in the
#: gap because the cost of the two errors is not equal here either.
MATCH_FLOOR = 0.72

#: Blocks flatter than this carry no content to compare — blank paper, whose
#: correlation with other blank paper is noise divided by noise.
MIN_BLOCK_CONTRAST = 6.0

#: A patch smaller than this many blocks is not reported.
MIN_REGION_BLOCKS = 3


@dataclass(frozen=True)
class ComparisonFinding:
    """What the filed copy says about the page in hand."""

    #: False when the two could not be put on the same footing at all.
    comparable: bool
    #: Regions whose content differs, largest first, in candidate pixels.
    regions: tuple[Region, ...] = ()
    #: Share of the compared page inside a region.
    coverage: float = 0.0
    #: Fraction of blocks holding enough ink to be worth comparing.
    inked_fraction: float = 0.0
    width: int = 0
    height: int = 0

    @property
    def differs(self) -> bool:
        return self.comparable and bool(self.regions)


def _to_gray(image: np.ndarray) -> np.ndarray:
    if image.ndim == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


#: Largest rotation, in degrees, the aligner will take out before comparing.
#:
#: A photograph of a screen or a page on a desk arrives a fraction of a degree
#: off square, and a fraction of a degree is enough: 0.7 degrees moves the
#: corners of a 1400px page by eight pixels, which is past anything a per-block
#: search should be asked to absorb. Uncorrected it put five boxes and 73% of
#: the page on a photograph of an untouched document — the worst kind of false
#: alarm this can make.
MAX_ROTATION_DEGREES = 3.0


def align(candidate: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Put the candidate on the reference's grid.

    Scale first, because the usual difference between the two is that one has
    been through something that resized it. Then take out rotation and shift,
    because the second usual difference is that somebody photographed it.

    What is deliberately *not* corrected is anything per-line: a re-typeset
    page is not shifted as a whole, it is shifted a line at a time, and that is
    left to the per-block search. Fitting a global transform to it would drag
    the whole page toward whichever lines happen to dominate.

    Estimation runs on a downscaled pair for speed and stability, and any
    failure to converge leaves the plain rescale in place. An alignment that
    could not be found is better handled as a comparison that finds
    differences than as an exception in a verification path.
    """
    height, width = reference.shape[:2]
    scaled = candidate
    if candidate.shape[:2] != (height, width):
        scaled = cv2.resize(
            candidate, (width, height),
            interpolation=cv2.INTER_AREA if candidate.shape[0] > height else cv2.INTER_CUBIC)

    try:
        small = 720.0 / max(height, width)
        small = min(1.0, small)
        size = (max(2, int(width * small)), max(2, int(height * small)))
        a = cv2.resize(_to_gray(scaled), size).astype(np.float32)
        b = cv2.resize(_to_gray(reference), size).astype(np.float32)
        warp = np.eye(2, 3, dtype=np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 60, 1e-5)
        cv2.findTransformECC(b, a, warp, cv2.MOTION_EUCLIDEAN, criteria, None, 5)
        angle = abs(np.degrees(np.arctan2(warp[1, 0], warp[0, 0])))
        if angle > MAX_ROTATION_DEGREES:
            return scaled
        # Estimated small, applied full size: the rotation carries over, the
        # translation is in the small image's pixels and has to be scaled back.
        warp[0, 2] /= small
        warp[1, 2] /= small
        return cv2.warpAffine(scaled, warp, (width, height),
                              flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
                              borderMode=cv2.BORDER_REPLICATE)
    except cv2.error:
        return scaled


def _block_match_scores(candidate: np.ndarray, reference: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per block: the best correlation found nearby, and whether it had content.

    Every offset in the search window is applied to the whole reference at once
    and scored for every block in one pass, so the cost is the number of
    offsets rather than the number of blocks. A per-block template match over a
    2000x2600 page would be about fifty thousand calls into OpenCV; this is
    forty-nine array operations.
    """
    cand = _to_gray(candidate).astype(np.float32)
    ref = _to_gray(reference).astype(np.float32)
    rows, cols = cand.shape[0] // BLOCK, cand.shape[1] // BLOCK
    cand = cand[: rows * BLOCK, : cols * BLOCK]

    def blocks_of(plane: np.ndarray) -> np.ndarray:
        return (plane.reshape(rows, BLOCK, cols, BLOCK)
                     .transpose(0, 2, 1, 3)
                     .reshape(rows, cols, BLOCK * BLOCK))

    cand_blocks = blocks_of(cand)
    cand_mean = cand_blocks.mean(axis=2, keepdims=True)
    cand_centred = cand_blocks - cand_mean
    cand_norm = np.sqrt((cand_centred ** 2).sum(axis=2))

    # Contrast decides whether a block is worth an opinion at all, and it is
    # the *reference* that decides. Blank paper correlates with blank paper at
    # whatever the noise happens to do, so a block that was blank when the
    # document was filed can only ever produce a score built out of noise.
    #
    # This also settles what to do about an editor's own watermark, which is
    # ink laid over blank margin. Judged from the candidate, every one of those
    # blocks is content that does not match and the page comes back covered in
    # boxes. Judged from the reference, they are margin that stayed margin
    # under something faint, which is what a reader means by "ignore the
    # watermark". What it does not excuse is ink laid over a printed value:
    # that block had content, and if the value no longer matches, it is boxed.
    ref_contrast_blocks = blocks_of(np.ascontiguousarray(ref[: rows * BLOCK, : cols * BLOCK]))
    contrast = ref_contrast_blocks.std(axis=2)

    padded = cv2.copyMakeBorder(ref, SEARCH, SEARCH, SEARCH, SEARCH,
                                cv2.BORDER_REPLICATE)
    best = np.full((rows, cols), -1.0, dtype=np.float32)
    for dy in range(0, 2 * SEARCH + 1):
        for dx in range(0, 2 * SEARCH + 1):
            shifted = padded[dy:dy + rows * BLOCK, dx:dx + cols * BLOCK]
            if shifted.shape != cand.shape:
                continue
            ref_blocks = blocks_of(np.ascontiguousarray(shifted))
            ref_centred = ref_blocks - ref_blocks.mean(axis=2, keepdims=True)
            ref_norm = np.sqrt((ref_centred ** 2).sum(axis=2))
            denominator = cand_norm * ref_norm
            with np.errstate(invalid="ignore", divide="ignore"):
                score = np.where(denominator > 1e-6,
                                 (cand_centred * ref_centred).sum(axis=2) / denominator,
                                 1.0)
            np.maximum(best, score.astype(np.float32), out=best)

    return best, contrast


def compare(candidate: np.ndarray, reference: np.ndarray) -> ComparisonFinding:
    """Where does this page show something the filed copy does not?"""
    if candidate.size == 0 or reference.size == 0:
        return ComparisonFinding(comparable=False)

    aligned = align(candidate, reference)
    rows = aligned.shape[0] // BLOCK
    cols = aligned.shape[1] // BLOCK
    if rows < 2 or cols < 2:
        return ComparisonFinding(comparable=False)

    scores, contrast = _block_match_scores(aligned, reference)
    inked = contrast >= MIN_BLOCK_CONTRAST
    if not inked.any():
        return ComparisonFinding(comparable=False)

    changed = (inked & (scores < MATCH_FLOOR)).astype(np.uint8)

    # The same shape machinery the carrier uses, for the same reason: a changed
    # value tears along a line, and its pieces have to be gathered into one box
    # before they are drawn or counted.
    opened = cv2.morphologyEx(changed, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    merged = cv2.dilate(opened, np.ones(BRIDGE_BLOCKS, np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)

    height, width = aligned.shape[:2]
    scale_x = candidate.shape[1] / float(width)
    scale_y = candidate.shape[0] / float(height)

    regions: list[Region] = []
    for index in range(1, count):
        area = int(opened[labels == index].sum())
        if area < MIN_REGION_BLOCKS:
            continue
        x = int(stats[index, cv2.CC_STAT_LEFT])
        y = int(stats[index, cv2.CC_STAT_TOP])
        w = int(stats[index, cv2.CC_STAT_WIDTH])
        h = int(stats[index, cv2.CC_STAT_HEIGHT])
        # Reported in the coordinates of the page the reader uploaded, not of
        # the reference it was compared against.
        left = int(max(0, x - 1) * BLOCK * scale_x)
        top = int(max(0, y - 1) * BLOCK * scale_y)
        right = int(min(cols, x + w + 1) * BLOCK * scale_x)
        bottom = int(min(rows, y + h + 1) * BLOCK * scale_y)
        regions.append(Region(
            left=left, top=top, right=right, bottom=bottom,
            peak_x=(left + right) // 2, peak_y=(top + bottom) // 2,
            concentration=0.0, background_rate=float(changed.mean()),
            blocks=area,
        ))

    regions = _merge_overlapping(regions)

    covered = np.zeros((rows, cols), dtype=bool)
    for r in regions:
        covered[max(0, int(r.top / scale_y) // BLOCK):int(r.bottom / scale_y) // BLOCK + 1,
                max(0, int(r.left / scale_x) // BLOCK):int(r.right / scale_x) // BLOCK + 1] = True

    return ComparisonFinding(
        comparable=True,
        regions=tuple(regions),
        coverage=float(covered.mean()),
        inked_fraction=float(inked.mean()),
        width=int(candidate.shape[1]),
        height=int(candidate.shape[0]),
    )
