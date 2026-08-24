from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

try:
    from .utils import (
        BASE_EMBED_STRENGTH,
        BLOCK_SIZE,
        SIGNED_POSTER_PATH,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        block_coordinates,
        build_watermark_payload,
        bytes_to_bits,
        crop_to_block_grid,
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
        SIGNED_POSTER_PATH,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        block_coordinates,
        build_watermark_payload,
        bytes_to_bits,
        crop_to_block_grid,
        generate_image_fingerprint,
        read_image,
        signature_from_base64,
        watermark_payload_bit_length,
        watermark_permutation,
        watermark_repetition,
        write_image,
    )


def _embed_bit_in_block(block: np.ndarray, bit: int, base_strength: float) -> np.ndarray:
    """Embed one bit by reinforcing its ordering across several DCT carrier pairs."""
    centered = block.astype(np.float32) - 128.0
    dct_block = cv2.dct(centered)

    strength = base_strength + min(6.0, float(np.std(block)) / 16.0)
    for (a_row, a_col), (b_row, b_col) in WATERMARK_EMBED_COEFFICIENT_PAIRS:
        coeff_a = float(dct_block[a_row, a_col])
        coeff_b = float(dct_block[b_row, b_col])

        if bit == 1:
            gap = coeff_a - coeff_b
            if gap < strength:
                shift = (strength - gap) / 2.0
                dct_block[a_row, a_col] += shift
                dct_block[b_row, b_col] -= shift
        else:
            gap = coeff_b - coeff_a
            if gap < strength:
                shift = (strength - gap) / 2.0
                dct_block[a_row, a_col] -= shift
                dct_block[b_row, b_col] += shift

    watermarked = cv2.idct(dct_block) + 128.0
    return np.clip(watermarked, 0, 255)


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
    for repetition_index in range(repetition):
        for bit_index, bit in enumerate(payload_bits):
            block_index = permutation[repetition_index * payload_bits.size + bit_index]
            row, col = block_coordinates(block_index, blocks_per_row)
            block = luminance[row : row + BLOCK_SIZE, col : col + BLOCK_SIZE]
            luminance[row : row + BLOCK_SIZE, col : col + BLOCK_SIZE] = _embed_bit_in_block(
                block,
                int(bit),
                base_strength,
            )

    ycrcb[:, :, 0] = np.clip(luminance, 0, 255).astype(np.uint8)
    signed_image = cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)
    if signed_image.shape[:2] != original_image.shape[:2]:
        original_image[: signed_image.shape[0], : signed_image.shape[1]] = signed_image
        signed_image = original_image

    if output_path is not None:
        write_image(output_path, signed_image)
    return signed_image
