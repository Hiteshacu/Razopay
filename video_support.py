from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np

try:
    from .utils import (
        AUTO_EMBED_STRENGTHS,
        BLOCK_SIZE,
        FORWARDED_SHARE_MAX_DIM,
        fingerprint_distance,
        fingerprint_digest,
        generate_image_fingerprint,
        load_private_key,
        load_public_key,
        log_signing_event,
        log_verification_event,
        register_signed_asset,
        signature_from_base64,
        signature_to_base64,
        sign_digest,
        verify_digest_signature,
        watermark_payload_bit_length,
    )
    from .watermark_embedder import embed_signature
    from .watermark_extractor import extract_watermark_bundle
except ImportError:
    from utils import (
        AUTO_EMBED_STRENGTHS,
        BLOCK_SIZE,
        FORWARDED_SHARE_MAX_DIM,
        fingerprint_distance,
        fingerprint_digest,
        generate_image_fingerprint,
        load_private_key,
        load_public_key,
        log_signing_event,
        log_verification_event,
        register_signed_asset,
        signature_from_base64,
        signature_to_base64,
        sign_digest,
        verify_digest_signature,
        watermark_payload_bit_length,
    )
    from watermark_embedder import embed_signature
    from watermark_extractor import extract_watermark_bundle


VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}
DEFAULT_VIDEO_FPS = 24.0
VIDEO_MIN_SAMPLE_COUNT = 2
VIDEO_MAX_SAMPLE_COUNT = 6
VIDEO_SAMPLE_SPACING_SECONDS = 3.0
VIDEO_TIMELINE_MARGIN_RATIO = 0.08
VIDEO_VERIFICATION_WINDOW_SECONDS = 0.35
VIDEO_REQUIRED_AUTHENTIC_RATIO = 0.45
VIDEO_FORWARD_MAX_DIM = min(1280, FORWARDED_SHARE_MAX_DIM)
VIDEO_OUTPUT_SUFFIX = ".mp4"
VIDEO_OUTPUT_FOURCC = "mp4v"
VIDEO_MAX_TOTAL_FINGERPRINT_DISTANCE = 10
VIDEO_MAX_DHASH_DISTANCE = 8
VIDEO_MAX_PHASH_DISTANCE = 4
VIDEO_RUN_FORWARDED_SELF_CHECK = False
VIDEO_FAST_RECOVERY_FACTORS = (1.0, 1.1, 1.25)
VIDEO_FULL_RECOVERY_FACTORS = (1.0, 1.05, 1.1, 1.125, 1.15, 1.175, 1.2, 1.25)
VIDEO_UNSIGNED_PROBE_LIMIT = 2


def is_supported_video_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def derive_video_output_path(
    video_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    if output_path is not None:
        return Path(output_path)
    source = Path(video_path)
    return source.with_name(f"{source.stem}_signed{VIDEO_OUTPUT_SUFFIX}")


def _safe_video_fps(raw_fps: float) -> float:
    if raw_fps and math.isfinite(raw_fps) and raw_fps > 0:
        return float(raw_fps)
    return DEFAULT_VIDEO_FPS


def _normalized_video_size(width: int, height: int) -> tuple[int, int]:
    normalized_width = width if width % 2 == 0 else width + 1
    normalized_height = height if height % 2 == 0 else height + 1
    return normalized_width, normalized_height


def _fit_within_box(width: int, height: int, max_dim: int) -> tuple[int, int]:
    longest_side = max(width, height)
    if longest_side <= max_dim:
        return _normalized_video_size(width, height)
    scale = max_dim / float(longest_side)
    resized_width = max(2, int(round(width * scale)))
    resized_height = max(2, int(round(height * scale)))
    return _normalized_video_size(resized_width, resized_height)


def _prepare_frame_for_size(frame: np.ndarray, target_size: tuple[int, int]) -> np.ndarray:
    target_width, target_height = target_size
    height, width = frame.shape[:2]
    if (width, height) == target_size:
        return frame
    if width > target_width or height > target_height:
        return cv2.resize(frame, target_size, interpolation=cv2.INTER_AREA)

    padded = np.full((target_height, target_width, 3), 0, dtype=frame.dtype)
    padded[:height, :width] = frame
    if width < target_width:
        padded[:height, width:target_width] = frame[:, width - 1 : width, :]
    if height < target_height:
        padded[height:target_height, :, :] = padded[height - 1 : height, :, :]
    return padded


def _open_video_capture(video_path: str | Path) -> cv2.VideoCapture:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Could not open video: {video_path}")
    return capture


def read_video_metadata(video_path: str | Path) -> dict[str, object]:
    capture = _open_video_capture(video_path)
    try:
        fps = _safe_video_fps(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(max(0, round(capture.get(cv2.CAP_PROP_FRAME_COUNT))))
        width = int(max(1, round(capture.get(cv2.CAP_PROP_FRAME_WIDTH))))
        height = int(max(1, round(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))))
    finally:
        capture.release()

    if frame_count <= 0:
        raise ValueError("Video contains no readable frames.")

    return {
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_seconds": frame_count / fps,
        "writer_size": _normalized_video_size(width, height),
    }


def select_video_sample_indices(frame_count: int, fps: float) -> list[int]:
    if frame_count <= 0:
        raise ValueError("Video contains no frames for sampling.")
    if frame_count == 1:
        return [0]

    duration_seconds = frame_count / _safe_video_fps(fps)
    estimated_count = int(round(duration_seconds / VIDEO_SAMPLE_SPACING_SECONDS)) + 1
    sample_count = max(VIDEO_MIN_SAMPLE_COUNT, estimated_count)
    sample_count = min(VIDEO_MAX_SAMPLE_COUNT, sample_count, frame_count)

    if sample_count == frame_count:
        return list(range(frame_count))

    margin = min(VIDEO_TIMELINE_MARGIN_RATIO, 1.0 / max(sample_count + 1, 2))
    positions = (
        [0.5]
        if sample_count == 1
        else np.linspace(margin, 1.0 - margin, sample_count).tolist()
    )

    indices: list[int] = []
    for position in positions:
        frame_index = int(round(position * (frame_count - 1)))
        frame_index = max(0, min(frame_count - 1, frame_index))
        if not indices or frame_index != indices[-1]:
            indices.append(frame_index)

    if not indices:
        indices = [frame_count // 2]

    return indices


def _ensure_video_frame_capacity(frame_size: tuple[int, int]) -> None:
    width, height = frame_size
    total_blocks = (width // BLOCK_SIZE) * (height // BLOCK_SIZE)
    required_blocks = watermark_payload_bit_length()
    if total_blocks < required_blocks:
        raise ValueError(
            "Video frames are too small to carry the current RSA watermark payload. "
            f"Writer size {width}x{height} provides {total_blocks} 8x8 blocks, "
            f"but at least {required_blocks} are required."
        )


def _write_visual_track(
    source_video: str | Path,
    output_path: str | Path,
    fps: float,
    writer_size: tuple[int, int],
    sample_indices: list[int],
    private_key,
    base_strength: float,
    payload_map: dict[int, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    capture = _open_video_capture(source_video)
    fourcc = cv2.VideoWriter_fourcc(*VIDEO_OUTPUT_FOURCC)
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, writer_size)
    if not writer.isOpened():
        capture.release()
        writer.release()
        raise RuntimeError(f"Could not open the output video writer for: {output_path}")

    if payload_map is None:
        payload_map = {}
    sample_index_set = set(sample_indices)
    current_index = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            prepared = _prepare_frame_for_size(frame, writer_size)
            if current_index in sample_index_set:
                payload = payload_map.get(current_index)
                if payload is None:
                    reference_fingerprint = generate_image_fingerprint(prepared)
                    signature_b64 = signature_to_base64(
                        sign_digest(private_key, fingerprint_digest(reference_fingerprint))
                    )
                    payload = {
                        "frame_index": current_index,
                        "reference_fingerprint": reference_fingerprint,
                        "signature_b64": signature_b64,
                    }
                    payload_map[current_index] = payload
                prepared = embed_signature(
                    prepared,
                    signature=str(payload["signature_b64"]),
                    fingerprint=bytes(payload["reference_fingerprint"]),
                    output_path=None,
                    base_strength=base_strength,
                )
            writer.write(prepared)
            current_index += 1
    finally:
        capture.release()
        writer.release()

    return [payload_map[index] for index in sorted(payload_map)]


def _ffmpeg_binary() -> str | None:
    return shutil.which("ffmpeg")


def _finalize_video_output(
    source_video: str | Path,
    visual_track_path: str | Path,
    output_path: str | Path,
) -> bool:
    visual_track = Path(visual_track_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    ffmpeg = _ffmpeg_binary()

    if ffmpeg is None:
        shutil.move(str(visual_track), str(output))
        return False

    command = [
        ffmpeg,
        "-y",
        "-i",
        str(visual_track),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-shortest",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
        visual_track.unlink(missing_ok=True)
        return True
    except Exception:
        shutil.move(str(visual_track), str(output))
        return False


def _simulate_forwarded_video_copy(source_path: str | Path, output_path: str | Path) -> Path:
    metadata = read_video_metadata(source_path)
    source = Path(source_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    capture = _open_video_capture(source)
    fps = min(_safe_video_fps(float(metadata["fps"])), 30.0)
    writer_size = _fit_within_box(
        int(metadata["width"]),
        int(metadata["height"]),
        VIDEO_FORWARD_MAX_DIM,
    )
    writer = cv2.VideoWriter(
        str(destination),
        cv2.VideoWriter_fourcc(*VIDEO_OUTPUT_FOURCC),
        fps,
        writer_size,
    )
    if not writer.isOpened():
        capture.release()
        writer.release()
        raise RuntimeError("Could not open the forwarded-video simulation writer.")

    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            resized = cv2.resize(frame, writer_size, interpolation=cv2.INTER_AREA)
            writer.write(resized)
    finally:
        capture.release()
        writer.release()

    return destination


def _video_search_offsets(fps: float, allow_neighbor_search: bool = True) -> list[int]:
    if not allow_neighbor_search:
        return [0]
    radius = max(1, int(round(_safe_video_fps(fps) * VIDEO_VERIFICATION_WINDOW_SECONDS)))
    offsets = [0]
    for delta in range(1, radius + 1):
        offsets.extend([delta, -delta])
    return offsets


def _read_frame_at(capture: cv2.VideoCapture, frame_index: int) -> tuple[int, np.ndarray] | None:
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_index))
    ok, frame = capture.read()
    if not ok:
        return None
    actual_index = int(max(0, round(capture.get(cv2.CAP_PROP_POS_FRAMES))) - 1)
    return actual_index, frame


def _verify_video_frame(
    frame: np.ndarray,
    public_key_path: str | Path | None = None,
    resize_factors: tuple[float, ...] = VIDEO_FULL_RECOVERY_FACTORS,
    include_legacy_permutation: bool = False,
) -> tuple[str, str | None]:
    try:
        reference_fingerprint, signature_b64 = extract_watermark_bundle(
            frame,
            resize_factors=resize_factors,
            include_legacy_permutation=include_legacy_permutation,
        )
    except Exception:
        return "missing", None

    signature = signature_from_base64(signature_b64)
    current_fingerprint = generate_image_fingerprint(frame)
    public_key = load_public_key(public_key_path)
    signature_ok = verify_digest_signature(
        public_key,
        fingerprint_digest(reference_fingerprint),
        signature,
    )
    distances = fingerprint_distance(reference_fingerprint, current_fingerprint)
    fingerprint_ok = (
        distances["total"] <= VIDEO_MAX_TOTAL_FINGERPRINT_DISTANCE
        and distances["dhash"] <= VIDEO_MAX_DHASH_DISTANCE
        and distances["phash"] <= VIDEO_MAX_PHASH_DISTANCE
    )
    if signature_ok and fingerprint_ok:
        return "authentic", signature_b64
    return "tampered", signature_b64


def _required_authentic_samples(sample_count: int) -> int:
    if sample_count <= 1:
        return 1
    return max(1, math.ceil(sample_count * VIDEO_REQUIRED_AUTHENTIC_RATIO))


def _build_video_status(
    sample_results: list[dict[str, object]],
    sample_count: int,
) -> tuple[bool, str, str]:
    authentic_count = sum(1 for item in sample_results if item["status"] == "authentic")
    tampered_count = sum(1 for item in sample_results if item["status"] == "tampered")
    missing_count = sample_count - authentic_count - tampered_count
    required_authentic = _required_authentic_samples(sample_count)

    if authentic_count >= required_authentic and tampered_count == 0:
        return (
            True,
            "Authentic Signed Video",
            (
                "Trusted proof was recovered from "
                f"{authentic_count} sampled moments across the video timeline."
            ),
        )

    if tampered_count > 0:
        return (
            False,
            "Tampered or altered video",
            (
                "At least one sampled video moment contained a Digital Trust Shield "
                "watermark that no longer matched the signed fingerprint."
            ),
        )

    if authentic_count == 0:
        return (
            False,
            "Unsigned/Unverified video",
            "No valid embedded Digital Trust Shield proof was recovered from the sampled video moments.",
        )

    return (
        False,
        "Insufficient trusted proof",
        (
            "Some valid signed moments were recovered, but not enough of the timeline "
            "could be re-verified after transformation."
        ),
    )


def verify_video(
    video_path: str | Path,
    public_key_path: str | Path | None = None,
    audit: bool = True,
    sample_indices: list[int] | None = None,
    allow_neighbor_search: bool = True,
    exhaustive: bool = False,
) -> dict[str, object]:
    metadata = read_video_metadata(video_path)
    if sample_indices is None:
        sample_indices = select_video_sample_indices(
            int(metadata["frame_count"]),
            float(metadata["fps"]),
        )
    capture = _open_video_capture(video_path)
    sample_results: list[dict[str, object]] = []

    def evaluate_indices(
        indices: list[int],
        resize_factors: tuple[float, ...],
        neighbor_search: bool,
    ) -> list[dict[str, object]]:
        results: list[dict[str, object]] = []
        offsets = _video_search_offsets(
            float(metadata["fps"]),
            allow_neighbor_search=neighbor_search,
        )
        for expected_index in indices:
            best_result: dict[str, object] | None = None
            visited: set[int] = set()
            for offset in offsets:
                candidate_index = max(0, min(int(metadata["frame_count"]) - 1, expected_index + offset))
                frame_data = _read_frame_at(capture, candidate_index)
                if frame_data is None:
                    continue
                actual_index, frame = frame_data
                if actual_index in visited:
                    continue
                visited.add(actual_index)

                status, signature_b64 = _verify_video_frame(
                    frame,
                    public_key_path=public_key_path,
                    resize_factors=resize_factors,
                    include_legacy_permutation=False,
                )
                result = {
                    "expected_frame": expected_index,
                    "matched_frame": actual_index,
                    "status": status,
                    "signature": signature_b64,
                }
                if status == "authentic":
                    best_result = result
                    break
                if status == "tampered" and best_result is None:
                    best_result = result

            if best_result is None:
                best_result = {
                    "expected_frame": expected_index,
                    "matched_frame": None,
                    "status": "missing",
                    "signature": None,
                }
            results.append(best_result)
        return results

    try:
        fast_probe_indices = sample_indices[: min(VIDEO_UNSIGNED_PROBE_LIMIT, len(sample_indices))]
        probe_results = evaluate_indices(
            fast_probe_indices,
            resize_factors=VIDEO_FAST_RECOVERY_FACTORS,
            neighbor_search=False,
        )
        if (
            not exhaustive
            and fast_probe_indices
            and all(result["status"] == "missing" for result in probe_results)
        ):
            sample_results = probe_results
        else:
            sample_results = evaluate_indices(
                sample_indices,
                resize_factors=VIDEO_FULL_RECOVERY_FACTORS if exhaustive else VIDEO_FAST_RECOVERY_FACTORS,
                neighbor_search=allow_neighbor_search if exhaustive else False,
            )
    finally:
        capture.release()

    is_authentic, status, detail = _build_video_status(sample_results, len(sample_indices))
    summary = {
        "assetType": "video",
        "isAuthentic": is_authentic,
        "status": status,
        "detail": detail,
        "sampledMoments": len(sample_indices),
        "authenticMoments": sum(1 for item in sample_results if item["status"] == "authentic"),
        "tamperedMoments": sum(1 for item in sample_results if item["status"] == "tampered"),
        "missingMoments": sum(1 for item in sample_results if item["status"] == "missing"),
        "durationSeconds": round(float(metadata["duration_seconds"]), 2),
        "fps": round(float(metadata["fps"]), 2),
        "frameCount": int(metadata["frame_count"]),
        "sampleResults": sample_results,
    }

    if audit:
        log_verification_event(
            "video_verified",
            result="success" if is_authentic else "failure",
            asset_type="video",
            input_path=Path(video_path),
            file_format=Path(video_path).suffix.lower(),
            verification_status="authentic" if is_authentic else "fake_or_tampered",
            sampled_moments=summary["sampledMoments"],
            authentic_moments=summary["authenticMoments"],
            tampered_moments=summary["tamperedMoments"],
            missing_moments=summary["missingMoments"],
        )

    return summary


def sign_video(
    video_path: str | Path,
    output_path: str | Path | None = None,
    private_key_path: str | Path | None = None,
    public_key_path: str | Path | None = None,
    self_check: bool = True,
) -> tuple[dict[str, object], Path]:
    source = Path(video_path)
    output = derive_video_output_path(source, output_path=output_path)
    metadata = read_video_metadata(source)
    _ensure_video_frame_capacity(tuple(metadata["writer_size"]))
    private_key = load_private_key(private_key_path)
    sample_indices = select_video_sample_indices(
        int(metadata["frame_count"]),
        float(metadata["fps"]),
    )
    payload_map: dict[int, dict[str, object]] = {}
    temp_output_dir: tempfile.TemporaryDirectory[str] | None = None
    last_error: Exception | None = None

    try:
        for base_strength in AUTO_EMBED_STRENGTHS:
            temp_output_dir = tempfile.TemporaryDirectory(prefix="dts_video_sign_")
            temp_root = Path(temp_output_dir.name)
            visual_track = temp_root / "signed_visual.mp4"

            _write_visual_track(
                source_video=source,
                output_path=visual_track,
                fps=_safe_video_fps(float(metadata["fps"])),
                writer_size=tuple(metadata["writer_size"]),
                sample_indices=sample_indices,
                private_key=private_key,
                base_strength=base_strength,
                payload_map=payload_map,
            )
            payloads = [payload_map[index] for index in sorted(payload_map)]
            audio_preserved = _finalize_video_output(source, visual_track, output)

            if self_check:
                try:
                    verification = verify_video(
                        output,
                        public_key_path=public_key_path,
                        audit=False,
                        sample_indices=sample_indices,
                        allow_neighbor_search=False,
                    )
                    if not verification["isAuthentic"]:
                        raise RuntimeError(str(verification["detail"]))

                    if VIDEO_RUN_FORWARDED_SELF_CHECK:
                        with tempfile.TemporaryDirectory(prefix="dts_video_share_check_") as share_dir:
                            forwarded_path = Path(share_dir) / "forwarded_preview.mp4"
                            _simulate_forwarded_video_copy(output, forwarded_path)
                            forwarded_verification = verify_video(
                                forwarded_path,
                                public_key_path=public_key_path,
                                audit=False,
                            )
                            if not forwarded_verification["isAuthentic"]:
                                raise RuntimeError(str(forwarded_verification["detail"]))
                except Exception as exc:
                    last_error = exc
                    output.unlink(missing_ok=True)
                    temp_output_dir.cleanup()
                    temp_output_dir = None
                    continue

            for sequence_number, payload in enumerate(payloads, start=1):
                register_signed_asset(
                    "video_frame",
                    output,
                    bytes(payload["reference_fingerprint"]),
                    str(payload["signature_b64"]),
                    source_path=source,
                    page_number=sequence_number,
                    metadata={
                        "frame_index": int(payload["frame_index"]),
                        "fps": round(float(metadata["fps"]), 4),
                        "duration_seconds": round(float(metadata["duration_seconds"]), 4),
                        "sample_count": len(payloads),
                    },
                )

            summary = {
                "assetType": "video",
                "sampledMoments": len(payloads),
                "audioPreserved": audio_preserved,
                "durationSeconds": round(float(metadata["duration_seconds"]), 2),
                "fps": round(float(metadata["fps"]), 2),
                "frameCount": int(metadata["frame_count"]),
                "writerWidth": int(tuple(metadata["writer_size"])[0]),
                "writerHeight": int(tuple(metadata["writer_size"])[1]),
                "signatures": [str(payload["signature_b64"]) for payload in payloads],
                "sampleFrames": [int(payload["frame_index"]) for payload in payloads],
            }
            log_signing_event(
                "video_signed",
                asset_type="video",
                input_path=source,
                output_path=output,
                file_format=output.suffix.lower(),
                sampled_moments=summary["sampledMoments"],
                duration_seconds=summary["durationSeconds"],
                audio_preserved=audio_preserved,
                self_check_enabled=self_check,
            )
            return summary, output
    except Exception as exc:
        last_error = exc
    finally:
        if temp_output_dir is not None:
            temp_output_dir.cleanup()

    log_signing_event(
        "video_signed",
        result="failure",
        asset_type="video",
        input_path=source,
        output_path=output,
        error=str(last_error) if last_error is not None else "Unknown video signing failure.",
        self_check_enabled=self_check,
    )
    raise RuntimeError(
        "Video signing failed for the available watermark strengths."
    ) from last_error
