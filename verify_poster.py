from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

try:
    from .utils import (
        SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE,
        SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE,
        SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE,
        REFERENCE_FINGERPRINT_BYTES,
        RSA_SIGNATURE_BYTES,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        WATERMARK_CHECKSUM_BYTES,
        WATERMARK_MAGIC,
        build_watermark_payload,
        find_registry_matches,
        fingerprint_distance,
        fingerprint_digest,
        fingerprint_from_base64,
        fingerprint_matches,
        generate_fast_image_fingerprint,
        generate_image_fingerprint,
        load_public_key,
        log_verification_event,
        read_image,
        signature_from_base64,
        verify_digest_signature,
    )
    from .video_support import is_supported_video_path, verify_video
    from .watermark_extractor import extract_watermark_bundle, watermark_payload_correlation
except ImportError:
    from utils import (
        SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE,
        SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE,
        SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE,
        REFERENCE_FINGERPRINT_BYTES,
        RSA_SIGNATURE_BYTES,
        WATERMARK_EMBED_COEFFICIENT_PAIRS,
        WATERMARK_CHECKSUM_BYTES,
        WATERMARK_MAGIC,
        build_watermark_payload,
        find_registry_matches,
        fingerprint_distance,
        fingerprint_digest,
        fingerprint_from_base64,
        fingerprint_matches,
        generate_fast_image_fingerprint,
        generate_image_fingerprint,
        load_public_key,
        log_verification_event,
        read_image,
        signature_from_base64,
        verify_digest_signature,
    )
    from video_support import is_supported_video_path, verify_video
    from watermark_extractor import extract_watermark_bundle, watermark_payload_correlation


def _verify_embedded_watermark_detailed(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    resize_factors: tuple[float, ...] | None = None,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
    use_fast_fingerprint: bool = False,
) -> tuple[bool, str, bool, bool]:
    if resize_factors is None:
        reference_fingerprint, signature_b64 = extract_watermark_bundle(
            image,
            include_legacy_permutation=include_legacy_permutation,
            coefficient_layouts=coefficient_layouts,
        )
    else:
        reference_fingerprint, signature_b64 = extract_watermark_bundle(
            image,
            resize_factors=resize_factors,
            include_legacy_permutation=include_legacy_permutation,
            coefficient_layouts=coefficient_layouts,
        )
    signature = signature_from_base64(signature_b64)
    current_fingerprint = (
        generate_fast_image_fingerprint(image)
        if use_fast_fingerprint
        else generate_image_fingerprint(image)
    )
    public_key = load_public_key(public_key_path)
    signature_ok = verify_digest_signature(public_key, fingerprint_digest(reference_fingerprint), signature)
    fingerprint_ok = fingerprint_matches(reference_fingerprint, current_fingerprint)
    is_valid = signature_ok and fingerprint_ok
    return is_valid, signature_b64, signature_ok, fingerprint_ok


def _verify_embedded_watermark(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    resize_factors: tuple[float, ...] | None = None,
    include_legacy_permutation: bool = True,
    coefficient_layouts=None,
    use_fast_fingerprint: bool = False,
) -> tuple[bool, str]:
    is_valid, signature_b64, _, _ = _verify_embedded_watermark_detailed(
        image,
        public_key_path=public_key_path,
        resize_factors=resize_factors,
        include_legacy_permutation=include_legacy_permutation,
        coefficient_layouts=coefficient_layouts,
        use_fast_fingerprint=use_fast_fingerprint,
    )
    return is_valid, signature_b64


def _verify_modern_watermark_fast(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    *,
    use_fast_fingerprint: bool = False,
) -> tuple[bool, str]:
    return _verify_embedded_watermark(
        image,
        public_key_path=public_key_path,
        resize_factors=(1.0,),
        include_legacy_permutation=False,
        coefficient_layouts=(WATERMARK_EMBED_COEFFICIENT_PAIRS,),
        use_fast_fingerprint=use_fast_fingerprint,
    )


def _trim_uniform_border(image: np.ndarray, threshold: int) -> np.ndarray | None:
    if min(image.shape[:2]) < 64:
        return None

    border_pixels = np.concatenate(
        [
            image[0, :, :],
            image[-1, :, :],
            image[:, 0, :],
            image[:, -1, :],
        ],
        axis=0,
    ).astype(np.int16)
    background = np.median(border_pixels, axis=0)
    difference = np.max(np.abs(image.astype(np.int16) - background), axis=2)
    rows, cols = np.where(difference > threshold)
    if rows.size == 0 or cols.size == 0:
        return None

    top = int(rows.min())
    bottom = int(rows.max()) + 1
    left = int(cols.min())
    right = int(cols.max()) + 1
    if top == 0 and bottom == image.shape[0] and left == 0 and right == image.shape[1]:
        return None

    trimmed = image[top:bottom, left:right]
    if min(trimmed.shape[:2]) < 64:
        return None
    return trimmed.copy()


def _safe_crop(
    image: np.ndarray,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> np.ndarray | None:
    height, width = image.shape[:2]
    left = max(0, min(width, int(left)))
    right = max(0, min(width, int(right)))
    top = max(0, min(height, int(top)))
    bottom = max(0, min(height, int(bottom)))
    if right - left < 64 or bottom - top < 64:
        return None
    if left == 0 and top == 0 and right == width and bottom == height:
        return None
    return image[top:bottom, left:right].copy()


def _append_unique_candidate(
    candidates: list[tuple[str, np.ndarray]],
    label: str,
    candidate: np.ndarray | None,
) -> None:
    if candidate is None:
        return
    if any(
        candidate.shape == existing.shape and np.array_equal(candidate, existing)
        for _, existing in candidates
    ):
        return
    candidates.append((label, candidate))


def _candidate_boxes_from_mask(
    image: np.ndarray,
    mask: np.ndarray,
    *,
    scale: float,
    max_boxes: int = 4,
) -> list[tuple[int, int, int, int]]:
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_height, image_width = image.shape[:2]
    image_area = float(image_width * image_height)
    boxes: list[tuple[int, int, int, int, int]] = []

    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        left = int(round(x / scale))
        top = int(round(y / scale))
        right = int(round((x + width) / scale))
        bottom = int(round((y + height) / scale))
        box_width = right - left
        box_height = bottom - top
        area = box_width * box_height
        if box_width < 96 or box_height < 96:
            continue
        if area < image_area * 0.08:
            continue
        if area > image_area * 0.96:
            continue
        boxes.append((area, left, top, right, bottom))

    boxes.sort(reverse=True)
    return [(left, top, right, bottom) for _, left, top, right, bottom in boxes[:max_boxes]]


def _add_box_crop_variants(
    image: np.ndarray,
    candidates: list[tuple[str, np.ndarray]],
    label: str,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    box_width = right - left
    box_height = bottom - top
    base_crop = _safe_crop(image, left, top, right, bottom)

    if base_crop is not None:
        for threshold in (2, 5, 12):
            _append_unique_candidate(
                candidates,
                f"{label}_tight_{threshold}",
                _trim_uniform_border(base_crop, threshold),
            )
    _append_unique_candidate(candidates, label, base_crop)

    # Desktop viewers often add shadows or thin UI padding around the actual image.
    for fraction in (0.008, 0.015, 0.025):
        inset_x = max(1, int(round(box_width * fraction)))
        inset_y = max(1, int(round(box_height * fraction)))
        _append_unique_candidate(
            candidates,
            f"{label}_inset_{int(fraction * 1000)}",
            _safe_crop(image, left + inset_x, top + inset_y, right - inset_x, bottom - inset_y),
        )


def _iter_visual_crop_candidates(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    if min(image.shape[:2]) < 160:
        return []

    image_height, image_width = image.shape[:2]
    max_side = max(image_height, image_width)
    scale = min(1.0, 900.0 / float(max_side))
    working = image
    if scale < 1.0:
        working = cv2.resize(
            image,
            (int(round(image_width * scale)), int(round(image_height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    work_height, work_width = working.shape[:2]
    patch = max(8, min(work_height, work_width) // 28)
    border_width = max(3, min(work_height, work_width) // 80)
    background_patches = [
        working[:patch, :patch],
        working[:patch, work_width - patch :],
        working[work_height - patch :, :patch],
        working[work_height - patch :, work_width - patch :],
        working[:border_width, :],
        working[work_height - border_width :, :],
        working[:, :border_width],
        working[:, work_width - border_width :],
    ]
    palette = [
        np.median(pixels.reshape(-1, 3), axis=0)
        for pixels in background_patches
        if pixels.size
    ]

    working_i16 = working.astype(np.int16)
    distances = [
        np.max(np.abs(working_i16 - color.astype(np.int16)), axis=2)
        for color in palette
    ]
    background_distance = np.min(np.stack(distances, axis=0), axis=0)
    foreground_mask = (background_distance > 22).astype(np.uint8) * 255
    foreground_mask = cv2.morphologyEx(
        foreground_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (19, 19)),
    )
    foreground_mask = cv2.morphologyEx(
        foreground_mask,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
    )

    gray = cv2.cvtColor(working, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 40, 120)
    edge_mask = cv2.dilate(
        edges,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        iterations=1,
    )
    edge_mask = cv2.morphologyEx(
        edge_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21)),
    )

    candidates: list[tuple[str, np.ndarray]] = []
    for index, box in enumerate(_candidate_boxes_from_mask(image, foreground_mask, scale=scale)):
        _add_box_crop_variants(image, candidates, f"foreground_box_{index}", box)
    for index, box in enumerate(_candidate_boxes_from_mask(image, edge_mask, scale=scale)):
        _add_box_crop_variants(image, candidates, f"edge_box_{index}", box)

    return candidates[:24]


def _iter_screenshot_candidates(image: np.ndarray) -> list[tuple[str, np.ndarray]]:
    trimmed_candidates: list[tuple[str, np.ndarray]] = []
    for threshold in (5, 12):
        trimmed = _trim_uniform_border(image, threshold)
        _append_unique_candidate(trimmed_candidates, f"trimmed_border_{threshold}", trimmed)

    for label, candidate in _iter_visual_crop_candidates(image):
        _append_unique_candidate(trimmed_candidates, label, candidate)

    if not trimmed_candidates:
        return [("full_frame", image)]

    return [*trimmed_candidates, ("full_frame", image)]


def _padding_splits(total_padding: int) -> list[tuple[int, int]]:
    if total_padding <= 0:
        return [(0, 0)]

    midpoint = total_padding // 2
    splits: list[tuple[int, int]] = [(midpoint, total_padding - midpoint)]
    if total_padding > 1:
        for candidate in (
            (max(0, midpoint - 1), total_padding - max(0, midpoint - 1)),
            (min(total_padding, midpoint + 1), total_padding - min(total_padding, midpoint + 1)),
        ):
            if candidate not in splits:
                splits.append(candidate)
            reverse_candidate = (candidate[1], candidate[0])
            if reverse_candidate not in splits:
                splits.append(reverse_candidate)
    return splits


def _iter_restored_candidates(
    candidate: np.ndarray,
    target_width: int,
    target_height: int,
    *,
    allow_border_restore: bool,
    max_candidates: int = 3,
) -> list[tuple[str, np.ndarray]]:
    restored_candidates: list[tuple[str, np.ndarray]] = []

    def append_candidate(label: str, image: np.ndarray) -> None:
        if len(restored_candidates) >= max_candidates:
            return
        restored_candidates.append((label, image))

    if candidate.shape[1] == target_width and candidate.shape[0] == target_height:
        append_candidate("exact_geometry", candidate)
    else:
        append_candidate(
            "direct_resize",
            cv2.resize(candidate, (target_width, target_height), interpolation=cv2.INTER_LINEAR),
        )

    if not allow_border_restore:
        return restored_candidates

    observed_scale = max(
        candidate.shape[1] / float(target_width),
        candidate.shape[0] / float(target_height),
    )
    for scale_multiplier in (1.012, 1.02):
        if len(restored_candidates) >= max_candidates:
            break
        display_scale = observed_scale * scale_multiplier
        display_width = max(candidate.shape[1], int(round(target_width * display_scale)))
        display_height = max(candidate.shape[0], int(round(target_height * display_scale)))
        missing_width = display_width - candidate.shape[1]
        missing_height = display_height - candidate.shape[0]
        if missing_width == 0 and missing_height == 0:
            continue

        for top, bottom in _padding_splits(missing_height):
            for left, right in _padding_splits(missing_width):
                if len(restored_candidates) >= max_candidates:
                    return restored_candidates
                padded = cv2.copyMakeBorder(
                    candidate,
                    top,
                    bottom,
                    left,
                    right,
                    cv2.BORDER_REPLICATE,
                )
                append_candidate(
                    f"border_restore_t{top}_b{bottom}_l{left}_r{right}",
                    cv2.resize(padded, (target_width, target_height), interpolation=cv2.INTER_LINEAR),
                )

    return restored_candidates


def _screenshot_recovery_budget_seconds(image: np.ndarray) -> float:
    megapixels = (image.shape[0] * image.shape[1]) / 1_000_000.0
    if megapixels <= 1.5:
        return 2.0
    if megapixels <= 3.0:
        return 3.5
    if megapixels <= 5.0:
        return 5.0
    return 6.5


def _verify_screenshot_recovery(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    candidates: list[tuple[str, np.ndarray]] | None = None,
) -> tuple[bool, str, str]:
    last_error: Exception | None = None
    found_registry_match = False
    deadline = time.perf_counter() + _screenshot_recovery_budget_seconds(image)
    failed_visual_match_count = 0
    timed_out_without_proof = False

    for candidate_label, candidate in (candidates or _iter_screenshot_candidates(image)):
        if time.perf_counter() >= deadline:
            timed_out_without_proof = True
            break

        is_visual_candidate = candidate_label.startswith(("foreground_box", "edge_box"))
        candidate_fingerprint = generate_fast_image_fingerprint(candidate)
        registry_matches = find_registry_matches(
            candidate_fingerprint,
            asset_types=("image",),
            max_total_distance=SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE,
            max_dhash_distance=SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE,
            max_phash_distance=SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE,
            require_output_dimensions=True,
        )
        registry_matches = _filter_registry_matches_for_public_key(
            registry_matches,
            public_key_path,
        )
        if not registry_matches:
            if candidate_label == "full_frame" and not found_registry_match:
                break
            continue

        found_registry_match = True
        candidate_height, candidate_width = candidate.shape[:2]
        attempted_dimension_count = 0
        max_dimension_attempts = 6 if candidate_label == "trimmed_border_5" else 3
        allow_border_restore = candidate_label == "trimmed_border_5"

        for match in registry_matches:
            if time.perf_counter() >= deadline:
                timed_out_without_proof = True
                break
            dimensions = match["dimensions"]
            if dimensions is None:
                continue
            attempted_dimension_count += 1
            if attempted_dimension_count > max_dimension_attempts:
                break

            target_width, target_height = dimensions
            for restored_label, restored in _iter_restored_candidates(
                candidate,
                target_width,
                target_height,
                allow_border_restore=allow_border_restore,
            ):
                if (
                    candidate_label == "full_frame"
                    and restored_label == "exact_geometry"
                ):
                    last_error = ValueError(
                        "Embedded watermark recovered, but the poster fingerprint did not match."
                    )
                    raise last_error

                if time.perf_counter() >= deadline:
                    timed_out_without_proof = True
                    break

                try:
                    is_valid, signature_b64, agreement = _verify_registry_watermark_correlation(
                        restored,
                        match,
                        public_key_path=public_key_path,
                    )
                    return (
                        True,
                        signature_b64,
                        f"screenshot_recovery_correlation:{candidate_label}:{restored_label}:{agreement:.3f}",
                    )
                except Exception as correlation_exc:
                    last_error = correlation_exc

                continue

            if timed_out_without_proof:
                break

        if timed_out_without_proof:
            break

        if is_visual_candidate and registry_matches:
            failed_visual_match_count += 1
            if failed_visual_match_count >= 2 and last_error is not None:
                raise last_error

    if timed_out_without_proof:
        raise ValueError("Watermark marker not found before the screenshot recovery time budget ended.")
    if last_error is not None:
        raise last_error
    raise ValueError("Screenshot recovery could not find a matching signed image geometry.")


MIN_WATERMARK_CORRELATION = 0.53
MIN_WATERMARK_SIGNED_MARGIN = 0.02
SIGNATURE_PAYLOAD_BIT_START = (
    len(WATERMARK_MAGIC)
    + WATERMARK_CHECKSUM_BYTES
    + 4
    + REFERENCE_FINGERPRINT_BYTES
) * 8
SIGNATURE_PAYLOAD_BIT_END = SIGNATURE_PAYLOAD_BIT_START + (RSA_SIGNATURE_BYTES * 8)


def _filter_registry_matches_for_public_key(
    registry_matches: list[dict[str, object]],
    public_key_path: str | Path | None,
) -> list[dict[str, object]]:
    if public_key_path is None:
        return registry_matches

    public_key = load_public_key(public_key_path)
    filtered_matches: list[dict[str, object]] = []
    for match in registry_matches:
        entry = match["entry"]
        try:
            reference_fingerprint = fingerprint_from_base64(entry["reference_fingerprint_b64"])
            signature = signature_from_base64(str(entry["signature_b64"]))
            if verify_digest_signature(
                public_key,
                fingerprint_digest(reference_fingerprint),
                signature,
            ):
                filtered_matches.append(match)
        except Exception:
            continue
    return filtered_matches


def _fingerprint_matches_recovered_copy(reference_fingerprint: bytes, candidate_fingerprint: bytes) -> bool:
    distances = fingerprint_distance(reference_fingerprint, candidate_fingerprint)
    return (
        distances["total"] <= SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE
        and distances["dhash"] <= SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE
        and distances["phash"] <= SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE
    )


def _verify_registry_watermark_correlation(
    image: np.ndarray,
    registry_match: dict[str, object],
    public_key_path: str | Path | None = None,
) -> tuple[bool, str, float]:
    entry = registry_match["entry"]
    reference_fingerprint = fingerprint_from_base64(entry["reference_fingerprint_b64"])
    signature_b64 = str(entry["signature_b64"])
    signature = signature_from_base64(signature_b64)
    public_key = load_public_key(public_key_path)
    if not verify_digest_signature(public_key, fingerprint_digest(reference_fingerprint), signature):
        raise ValueError("Registry match was found, but the selected public key did not validate it.")

    current_fingerprint = generate_image_fingerprint(image)
    if not _fingerprint_matches_recovered_copy(reference_fingerprint, current_fingerprint):
        raise ValueError("Registry match was found, but the visual content did not match.")

    expected_payload = build_watermark_payload(signature, reference_fingerprint)
    agreement, signed_margin = watermark_payload_correlation(
        image,
        expected_payload,
        include_legacy_permutation=False,
        coefficient_layouts=(WATERMARK_EMBED_COEFFICIENT_PAIRS,),
        bit_start=SIGNATURE_PAYLOAD_BIT_START,
        bit_end=SIGNATURE_PAYLOAD_BIT_END,
    )
    if agreement < MIN_WATERMARK_CORRELATION or signed_margin < MIN_WATERMARK_SIGNED_MARGIN:
        raise ValueError(
            "Watermark evidence was too weak after recovery: "
            f"{agreement:.3f} agreement, {signed_margin:.3f} margin."
        )

    return True, signature_b64, agreement


def _verify_registry_visual_match(
    image: np.ndarray,
    registry_match: dict[str, object],
    public_key_path: str | Path | None = None,
) -> tuple[bool, str]:
    entry = registry_match["entry"]
    reference_fingerprint = fingerprint_from_base64(entry["reference_fingerprint_b64"])
    signature_b64 = str(entry["signature_b64"])
    signature = signature_from_base64(signature_b64)
    public_key = load_public_key(public_key_path)
    if not verify_digest_signature(public_key, fingerprint_digest(reference_fingerprint), signature):
        raise ValueError("Registry match was found, but the selected public key did not validate it.")

    current_fingerprint = generate_image_fingerprint(image)
    if not _fingerprint_matches_recovered_copy(reference_fingerprint, current_fingerprint):
        raise ValueError("Registry match was found, but the visual content did not match.")

    return True, signature_b64


def _verify_full_frame_registry_recovery(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
) -> tuple[bool, str, str]:
    """
    Recover a forwarded full-frame image by resizing it back to a known signed geometry.

    Messaging apps often downscale or recompress the whole poster without adding the
    extra canvas/border clues that our screenshot detector relies on. This path keeps
    the recovery focused on the full image before we fall back to screenshot heuristics.
    """
    candidate_fingerprint = generate_fast_image_fingerprint(image)
    registry_matches = find_registry_matches(
        candidate_fingerprint,
        asset_types=("image",),
        max_total_distance=SCREENSHOT_RECOVERY_MAX_TOTAL_DISTANCE,
        max_dhash_distance=SCREENSHOT_RECOVERY_MAX_DHASH_DISTANCE,
        max_phash_distance=SCREENSHOT_RECOVERY_MAX_PHASH_DISTANCE,
        require_output_dimensions=True,
    )
    registry_matches = _filter_registry_matches_for_public_key(
        registry_matches,
        public_key_path,
    )
    if not registry_matches:
        raise ValueError("Forwarded-image recovery could not find a matching signed image geometry.")

    image_height, image_width = image.shape[:2]
    last_error: Exception | None = None
    attempted_match_count = 0

    for match in registry_matches:
        dimensions = match["dimensions"]
        if dimensions is None:
            continue
        attempted_match_count += 1
        if attempted_match_count > 6:
            break

        target_width, target_height = dimensions
        restored_candidates: list[tuple[str, np.ndarray]] = []
        if target_width == image_width and target_height == image_height:
            restored_candidates.append(("exact_geometry", image))
        else:
            downscaling = image_width > target_width or image_height > target_height
            primary_interpolation = cv2.INTER_AREA if downscaling else cv2.INTER_CUBIC
            restored_candidates.append(
                (
                    "direct_resize_primary",
                    cv2.resize(image, (target_width, target_height), interpolation=primary_interpolation),
                )
            )
            restored_candidates.append(
                (
                    "direct_resize_lanczos",
                    cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_LANCZOS4),
                )
            )
            restored_candidates.append(
                (
                    "direct_resize_lanczos_blur",
                    cv2.GaussianBlur(
                        cv2.resize(image, (target_width, target_height), interpolation=cv2.INTER_LANCZOS4),
                        (3, 3),
                        0,
                    ),
                )
            )

        for restored_label, restored in restored_candidates:
            try:
                is_valid, signature_b64, agreement = _verify_registry_watermark_correlation(
                    restored,
                    match,
                    public_key_path=public_key_path,
                )
                return True, signature_b64, f"forwarded_full_frame_correlation:{restored_label}:{agreement:.3f}"
            except Exception as correlation_exc:
                last_error = correlation_exc

            continue

    if last_error is not None:
        raise last_error
    raise ValueError("Forwarded-image recovery could not reconstruct a matching signed image.")


def _verify_image_with_mode(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    allow_registry_fallback: bool = False,
) -> tuple[bool, str, str]:
    screenshot_candidates = _iter_screenshot_candidates(image)

    watermark_error: Exception | None = None
    try:
        is_valid, signature_b64, signature_ok, _ = _verify_embedded_watermark_detailed(
            image,
            public_key_path=public_key_path,
            resize_factors=(1.0,),
            include_legacy_permutation=False,
            coefficient_layouts=(WATERMARK_EMBED_COEFFICIENT_PAIRS,),
        )
        if is_valid:
            return True, signature_b64, "embedded_watermark"
        if not signature_ok:
            raise ValueError("Embedded watermark recovered, but the selected public key did not validate it.")
        watermark_error = ValueError("Embedded watermark recovered, but the poster fingerprint did not match.")
    except Exception as exc:
        watermark_error = exc
        if "selected public key did not validate" in str(exc).lower():
            raise watermark_error

    try:
        return _verify_full_frame_registry_recovery(
            image,
            public_key_path=public_key_path,
        )
    except Exception as forwarded_recovery_error:
        if watermark_error is None:
            watermark_error = forwarded_recovery_error

    try:
        return _verify_screenshot_recovery(
            image,
            public_key_path=public_key_path,
            candidates=screenshot_candidates,
        )
    except Exception as screenshot_error:
        if allow_registry_fallback:
            raise ValueError(
                "Registry fallback is disabled for poster authenticity verification. "
                "Only an embedded watermark can prove a poster is authentic."
            ) from screenshot_error
        try:
            is_valid, signature_b64 = _verify_embedded_watermark(
                image,
                public_key_path=public_key_path,
                resize_factors=(1.0,),
            )
            if is_valid:
                return True, signature_b64, "embedded_watermark_legacy"
        except Exception as legacy_error:
            if watermark_error is not None:
                raise watermark_error from legacy_error
            raise screenshot_error from legacy_error

        if watermark_error is not None:
            raise watermark_error from screenshot_error
        raise screenshot_error


def verify_image(
    image: np.ndarray,
    public_key_path: str | Path | None = None,
    allow_registry_fallback: bool = False,
) -> tuple[bool, str]:
    is_valid, signature_b64, _ = _verify_image_with_mode(
        image,
        public_key_path=public_key_path,
        allow_registry_fallback=allow_registry_fallback,
    )
    return is_valid, signature_b64


def verify_poster(
    poster_path: str | Path | np.ndarray,
    public_key_path: str | Path | None = None,
    audit: bool = True,
    allow_registry_fallback: bool = False,
    exhaustive_video: bool = False,
) -> tuple[bool, str] | list[dict[str, object]] | dict[str, object]:
    if isinstance(poster_path, np.ndarray):
        return verify_image(
            poster_path,
            public_key_path=public_key_path,
            allow_registry_fallback=allow_registry_fallback,
        )

    if Path(poster_path).suffix.lower() == ".pdf":
        try:
            from .pdf_support import verify_pdf
        except ImportError:
            from pdf_support import verify_pdf

        return verify_pdf(poster_path, public_key_path=public_key_path, audit=audit)

    if is_supported_video_path(poster_path):
        return verify_video(
            poster_path,
            public_key_path=public_key_path,
            audit=audit,
            exhaustive=exhaustive_video,
        )

    try:
        image = read_image(poster_path)
        is_valid, signature_b64, verification_mode = _verify_image_with_mode(
            image,
            public_key_path=public_key_path,
            allow_registry_fallback=allow_registry_fallback,
        )
        if audit:
            log_verification_event(
                "image_verified",
                result="success" if is_valid else "failure",
                asset_type="image",
                input_path=Path(poster_path),
                file_format=Path(poster_path).suffix.lower(),
                verification_mode=verification_mode,
                verification_status="authentic" if is_valid else "fake_or_tampered",
            )
        return is_valid, signature_b64
    except Exception as exc:
        if audit:
            log_verification_event(
                "image_verified",
                result="failure",
                asset_type="image",
                input_path=Path(poster_path),
                file_format=Path(poster_path).suffix.lower(),
                error=str(exc),
                verification_status="verification_error",
            )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a watermarked poster image.")
    parser.add_argument("poster", help="Path to the received poster image.")
    parser.add_argument(
        "--public-key",
        default=None,
        help="Optional path to a PEM encoded RSA public key.",
    )
    parser.add_argument(
        "--show-signature",
        action="store_true",
        help="Print the recovered watermark signature string.",
    )
    parser.add_argument(
        "--allow-registry-fallback",
        action="store_true",
        help=(
            "Retained only for compatibility. Authentic verification still requires "
            "an embedded watermark."
        ),
    )
    parser.add_argument(
        "--strict-video",
        action="store_true",
        help="Use the slower exhaustive video verification path with wider recovery attempts.",
    )
    args = parser.parse_args()

    try:
        result = verify_poster(
            args.poster,
            public_key_path=args.public_key,
            allow_registry_fallback=args.allow_registry_fallback,
            exhaustive_video=args.strict_video,
        )
        if isinstance(result, list):
            fake_pages = [page["page"] for page in result if not page["valid"]]
            if not fake_pages:
                print("Authentic Government PDF")
                for page in result:
                    print(f"Page {page['page']}: Authentic")
                    if args.show_signature and page["signature"]:
                        print(page["signature"])
                return

            print("Warning: PDF contains fake or tampered pages")
            for page in result:
                status = "Authentic" if page["valid"] else "Fake"
                print(f"Page {page['page']}: {status}")
                if args.show_signature and page["signature"]:
                    print(page["signature"])
            sys.exit(1)

        if isinstance(result, dict):
            print(result["status"])
            print(result["detail"])
            print(
                "Timeline summary: "
                f"{result['authenticMoments']} authentic / "
                f"{result['tamperedMoments']} tampered / "
                f"{result['missingMoments']} missing sampled moments"
            )
            if args.show_signature:
                for sample in result["sampleResults"]:
                    if sample["signature"]:
                        print(sample["signature"])
            if not result["isAuthentic"]:
                sys.exit(1)
            return

        is_valid, signature_b64 = result
        if is_valid:
            print("Authentic Government Poster")
            if args.show_signature:
                print(signature_b64)
            return
    except Exception:
        pass

    print("Warning: Poster is fake or tampered")
    sys.exit(1)


if __name__ == "__main__":
    main()
