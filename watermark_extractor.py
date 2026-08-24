from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

RESIZE_RECOVERY_FACTORS = (
    1.0,
    1.05,
    1.1,
    1.125,
    1.15,
    1.175,
    1.2,
    1.25,
    1.3,
    1.35,
    1.4,
    1.5,
)

try:
    from .utils import (
        BLOCK_SIZE,
        REFERENCE_FINGERPRINT_BYTES,
        RSA_SIGNATURE_BYTES,
        WATERMARK_EXTRACT_COEFFICIENT_LAYOUTS,
        bits_to_bytes,
        block_coordinates,
        bytes_to_bits,
        crop_to_block_grid,
        legacy_watermark_permutation,
        parse_watermark_payload,
        read_image,
        signature_to_base64,
        watermark_payload_bit_length,
        watermark_permutation,
        watermark_repetition,
    )
except ImportError:
    from utils import (
        BLOCK_SIZE,
        REFERENCE_FINGERPRINT_BYTES,
        RSA_SIGNATURE_BYTES,
        WATERMARK_EXTRACT_COEFFICIENT_LAYOUTS,
        bits_to_bytes,
        block_coordinates,
        bytes_to_bits,
        crop_to_block_grid,
        legacy_watermark_permutation,
        parse_watermark_payload,
        read_image,
        signature_to_base64,
        watermark_payload_bit_length,
        watermark_permutation,
        watermark_repetition,
    )


def _extract_bit_votes_from_block(
    block: np.ndarray,
    coefficient_pairs: tuple[tuple[tuple[int, int], tuple[int, int]], ...],
) -> tuple[int, int]:
    """Read one bit by checking which coefficient dominates across carrier pairs."""
    centered = block.astype(np.float32) - 128.0
    dct_block = cv2.dct(centered)
    votes = 0
    total_votes = 0
    for (a_row, a_col), (b_row, b_col) in coefficient_pairs:
        votes += int(dct_block[a_row, a_col] >= dct_block[b_row, b_col])
        total_votes += 1
    return votes, total_votes


def extract_signature(
    image: np.ndarray | str | Path,
    resize_factors: tuple[float, ...] = RESIZE_RECOVERY_FACTORS,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
) -> str:
    """
    Recover the embedded RSA signature from a poster.

    The extractor uses majority voting across repeated payload copies so it can
    tolerate moderate compression noise before reconstructing the base64 string.
    """
    _, signature_b64 = extract_watermark_bundle(
        image,
        resize_factors=resize_factors,
        include_legacy_permutation=include_legacy_permutation,
        coefficient_layouts=coefficient_layouts,
    )
    return signature_b64


def extract_watermark_bundle(
    image: np.ndarray | str | Path,
    resize_factors: tuple[float, ...] = RESIZE_RECOVERY_FACTORS,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
) -> tuple[bytes, str]:
    """
    Recover both the reference fingerprint and the embedded RSA signature.

    Verification uses the reference fingerprint as the signed visual identity of
    the poster, then compares the received image against it with perceptual
    distance thresholds.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)

    last_error: Exception | None = None
    for factor in resize_factors:
        candidate = image
        if factor != 1.0:
            height, width = image.shape[:2]
            candidate = cv2.resize(
                image,
                (int(round(width * factor)), int(round(height * factor))),
                interpolation=cv2.INTER_CUBIC,
            )
        try:
            return _extract_watermark_bundle_from_array(
                candidate,
                include_legacy_permutation=include_legacy_permutation,
                coefficient_layouts=coefficient_layouts,
            )
        except Exception as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("Failed to extract watermark payload.")


def _extract_watermark_bundle_from_array(
    image: np.ndarray,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
) -> tuple[bytes, str]:
    working_image = crop_to_block_grid(image)
    luminance = cv2.cvtColor(working_image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)

    payload_bits = watermark_payload_bit_length()
    blocks_per_row = luminance.shape[1] // BLOCK_SIZE
    total_blocks = (luminance.shape[0] // BLOCK_SIZE) * blocks_per_row
    repetition = watermark_repetition(total_blocks, payload_bits)
    if total_blocks < payload_bits:
        raise ValueError("Poster is too small to contain a valid watermark.")

    last_error: Exception | None = None
    permutations = [watermark_permutation(total_blocks)]
    if include_legacy_permutation:
        permutations.append(legacy_watermark_permutation(total_blocks))

    active_coefficient_layouts = coefficient_layouts or WATERMARK_EXTRACT_COEFFICIENT_LAYOUTS
    for coefficient_pairs in active_coefficient_layouts:
        for permutation in permutations:
            try:
                recovered_bits = np.zeros(payload_bits, dtype=np.uint8)
                for bit_index in range(payload_bits):
                    votes = 0
                    total_votes = 0
                    for repetition_index in range(repetition):
                        block_index = permutation[repetition_index * payload_bits + bit_index]
                        row, col = block_coordinates(block_index, blocks_per_row)
                        block = luminance[row : row + BLOCK_SIZE, col : col + BLOCK_SIZE]
                        block_votes, block_vote_count = _extract_bit_votes_from_block(
                            block,
                            coefficient_pairs,
                        )
                        votes += block_votes
                        total_votes += block_vote_count
                    recovered_bits[bit_index] = 1 if votes > (total_votes / 2.0) else 0

                payload = bits_to_bytes(recovered_bits.tolist())
                fingerprint, signature = parse_watermark_payload(payload)
                if len(fingerprint) != REFERENCE_FINGERPRINT_BYTES:
                    raise ValueError("Recovered fingerprint length does not match the expected size.")
                if len(signature) != RSA_SIGNATURE_BYTES:
                    raise ValueError("Recovered signature length does not match the expected RSA key size.")
                return fingerprint, signature_to_base64(signature)
            except Exception as exc:
                last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("Failed to extract watermark payload.")


def watermark_payload_correlation(
    image: np.ndarray | str | Path,
    expected_payload: bytes,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
    bit_start: int | None = None,
    bit_end: int | None = None,
) -> tuple[float, float]:
    """
    Measure how strongly an image still carries a known watermark payload.

    WhatsApp and screenshots can corrupt a few bits enough to break checksum
    parsing. For already-registered signed assets, this correlation check lets
    verification confirm hidden watermark evidence without re-reading every bit
    perfectly.

    Returns ``(bit_agreement, signed_margin)``. The signed margin is useful for
    rejecting visual-only false positives because it measures whether DCT votes
    lean toward the expected payload bits, not just whether hard-decoded bits
    happen to match.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)

    working_image = crop_to_block_grid(image)
    luminance = cv2.cvtColor(working_image, cv2.COLOR_BGR2YCrCb)[:, :, 0].astype(np.float32)

    expected_bits = bytes_to_bits(expected_payload)
    payload_bits = expected_bits.size
    start = 0 if bit_start is None else max(0, bit_start)
    end = payload_bits if bit_end is None else min(payload_bits, bit_end)
    if start >= end:
        raise ValueError("Invalid watermark correlation bit range.")

    blocks_per_row = luminance.shape[1] // BLOCK_SIZE
    total_blocks = (luminance.shape[0] // BLOCK_SIZE) * blocks_per_row
    repetition = watermark_repetition(total_blocks, payload_bits)
    if total_blocks < payload_bits:
        raise ValueError("Image is too small to compare against the expected watermark.")

    permutations = [watermark_permutation(total_blocks)]
    if include_legacy_permutation:
        permutations.append(legacy_watermark_permutation(total_blocks))

    best_agreement = 0.0
    best_signed_margin = 0.0
    active_coefficient_layouts = coefficient_layouts or WATERMARK_EXTRACT_COEFFICIENT_LAYOUTS
    for coefficient_pairs in active_coefficient_layouts:
        for permutation in permutations:
            matching_bits = 0
            signed_margin_sum = 0.0
            compared_bits = 0
            for bit_index in range(start, end):
                expected_bit = expected_bits[bit_index]
                votes = 0
                total_votes = 0
                for repetition_index in range(repetition):
                    block_index = permutation[repetition_index * payload_bits + bit_index]
                    row, col = block_coordinates(block_index, blocks_per_row)
                    block = luminance[row : row + BLOCK_SIZE, col : col + BLOCK_SIZE]
                    block_votes, block_vote_count = _extract_bit_votes_from_block(
                        block,
                        coefficient_pairs,
                    )
                    votes += block_votes
                    total_votes += block_vote_count
                recovered_bit = 1 if votes > (total_votes / 2.0) else 0
                matching_bits += int(recovered_bit == int(expected_bit))
                raw_margin = (votes - (total_votes / 2.0)) / (total_votes / 2.0)
                signed_margin_sum += raw_margin if int(expected_bit) == 1 else -raw_margin
                compared_bits += 1

            agreement = matching_bits / float(compared_bits)
            signed_margin = signed_margin_sum / float(compared_bits)
            if (agreement, signed_margin) > (best_agreement, best_signed_margin):
                best_agreement = agreement
                best_signed_margin = signed_margin

    return best_agreement, best_signed_margin


def watermark_payload_agreement(
    image: np.ndarray | str | Path,
    expected_payload: bytes,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
    bit_start: int | None = None,
    bit_end: int | None = None,
) -> float:
    agreement, _ = watermark_payload_correlation(
        image,
        expected_payload,
        include_legacy_permutation=include_legacy_permutation,
        coefficient_layouts=coefficient_layouts,
        bit_start=bit_start,
        bit_end=bit_end,
    )
    return agreement
