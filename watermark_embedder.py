from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np

try:
    from .utils import (
        BASE_EMBED_STRENGTH,
        BLOCK_SIZE,
        DCT_MATRIX,
        SIGNED_POSTER_PATH,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        blocks_to_image,
        build_watermark_payload,
        bytes_to_bits,
        crop_to_block_grid,
        image_to_blocks,
        generate_image_fingerprint,
        read_image,
        signature_from_base64,
        watermark_payload_bit_length,
        watermark_permutation,
        watermark_repetition,
        write_image,
    )
except ImportError:
    from utils import (
        BASE_EMBED_STRENGTH,
        BLOCK_SIZE,
        DCT_MATRIX,
        SIGNED_POSTER_PATH,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        blocks_to_image,
        build_watermark_payload,
        bytes_to_bits,
        crop_to_block_grid,
        image_to_blocks,
        generate_image_fingerprint,
        read_image,
        signature_from_base64,
        watermark_payload_bit_length,
        watermark_permutation,
        watermark_repetition,
        write_image,
    )


# Set DTS_SUBTLE_EMBEDDING=1 to mark flat areas gently. Off by default —
# see _embed_bits_in_blocks for why the visible carrier is the point.
_SUBTLE_EMBEDDING = os.getenv("DTS_SUBTLE_EMBEDDING", "").strip().lower() in {"1", "true", "yes", "on"}


def _embed_bits_in_blocks(
    blocks: np.ndarray,
    bits: np.ndarray,
    base_strength: float,
) -> np.ndarray:
    """Embed one bit into each block of a stack, in a single batched pass.

    Writing a payload used to transform one 8x8 block per bit per repetition —
    around 25,000 cv2.dct/cv2.idct pairs for a two-megapixel page, nearly all
    of it interpreter and call overhead rather than arithmetic. Reading was
    given the batched treatment already (see _votes_per_block); writing was
    not, which is why signing cost several times what verifying did.

    Every block is independent — the permutation assigns each carrier index
    exactly once, so no block is written twice and order cannot matter. That
    makes the whole schedule one matrix product.

    The transform is the same one the extractor and the canonical hash use, so
    fingerprints and recovered payloads are unchanged.
    """
    activity = blocks.std(axis=(1, 2))
    strength = base_strength + np.minimum(6.0, activity / 16.0)

    # Optional, and off by default.
    #
    # Marking a flat block as hard as a detailed one is visible on blank
    # paper: the carrier shows as faint diagonal hatching in the margins.
    # Scaling the strength down there cuts that from about six levels to two
    # on a scanned page.
    #
    # It stays off because the visible carrier is the product. This scheme
    # exists to survive a screenshot, and a screenshot keeps exactly what you
    # can see — so a mark quiet enough to disappear from a margin is a mark
    # closer to disappearing from the screenshot too. That trade belongs to
    # whoever is signing, not to this function, and the honest default is the
    # one that survives.
    #
    # Extraction is identical either way: the extractor reads the sign of the
    # coefficient difference, never its magnitude.
    if _SUBTLE_EMBEDDING:
        strength = strength * np.minimum(1.0, 0.30 + activity / 18.0)

    coefficients = DCT_MATRIX @ (blocks - 128.0) @ DCT_MATRIX.T

    # Which coefficient the bit wants to be the larger of the pair.
    wants_a_larger = bits.astype(bool)

    for (a_row, a_col), (b_row, b_col) in WATERMARK_EMBED_COEFFICIENT_PAIRS:
        coeff_a = coefficients[:, a_row, a_col]
        coeff_b = coefficients[:, b_row, b_col]

        # One expression for both bit values: the pair is pushed apart only
        # where it does not already clear `strength` in the wanted direction,
        # which is what the per-block branch did one block at a time.
        gap = np.where(wants_a_larger, coeff_a - coeff_b, coeff_b - coeff_a)
        shift = np.where(gap < strength, (strength - gap) / 2.0, 0.0)
        toward_a = np.where(wants_a_larger, shift, -shift)

        coefficients[:, a_row, a_col] = coeff_a + toward_a
        coefficients[:, b_row, b_col] = coeff_b - toward_a

    return np.clip(DCT_MATRIX.T @ coefficients @ DCT_MATRIX + 128.0, 0, 255)


def embed_signature(
    image: np.ndarray | str | Path,
    signature: bytes | str,
    fingerprint: bytes | None = None,
    output_path: str | Path | None = SIGNED_POSTER_PATH,
    base_strength: float = BASE_EMBED_STRENGTH,
) -> np.ndarray:
    """
    Embed the RSA signature invisibly in DCT blocks across the luminance channel.

    Repeating each bit across many blocks and reinforcing it across multiple DCT
    carrier pairs makes extraction much more tolerant to messaging-app
    recompression and mild phone screenshot blur than direct metadata or simple
    LSB storage.
    """
    if isinstance(image, (str, Path)):
        image = read_image(image)
    if isinstance(signature, str):
        signature = signature_from_base64(signature)
    if fingerprint is None:
        fingerprint = generate_image_fingerprint(image)

    original_image = image.copy()
    working_image = crop_to_block_grid(image)
    payload_bits = bytes_to_bits(build_watermark_payload(signature, fingerprint))
    expected_bits = watermark_payload_bit_length()
    if payload_bits.size != expected_bits:
        raise ValueError("Unexpected payload size for watermark embedding.")

    ycrcb = cv2.cvtColor(working_image, cv2.COLOR_BGR2YCrCb)
    luminance = ycrcb[:, :, 0].astype(np.float32)

    blocks_per_row = luminance.shape[1] // BLOCK_SIZE
    total_blocks = (luminance.shape[0] // BLOCK_SIZE) * blocks_per_row
    repetition = watermark_repetition(total_blocks, payload_bits.size)
    if total_blocks < payload_bits.size:
        raise ValueError(
            "Poster is too small to hold the signature watermark. "
            "Use a larger poster or reduce the key size."
        )

    permutation = watermark_permutation(total_blocks)

    # The schedule the nested loop walked: carrier i holds payload bit
    # i % payload_bits.size, at block permutation[i]. Laid out flat, it is a
    # gather, one batched embed, and a scatter.
    carrier_count = repetition * payload_bits.size
    carriers = permutation[:carrier_count]
    carrier_bits = np.tile(payload_bits, repetition)

    stack = image_to_blocks(luminance)
    grid = stack.shape
    stack = stack.reshape(-1, BLOCK_SIZE, BLOCK_SIZE)
    stack[carriers] = _embed_bits_in_blocks(stack[carriers], carrier_bits, base_strength)
    luminance = blocks_to_image(stack.reshape(grid))

    ycrcb[:, :, 0] = np.clip(luminance, 0, 255).astype(np.uint8)
    signed_image = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
    if signed_image.shape[:2] != original_image.shape[:2]:
        original_image[: signed_image.shape[0], : signed_image.shape[1]] = signed_image
        signed_image = original_image

    if output_path is not None:
        write_image(output_path, signed_image)
    return signed_image
