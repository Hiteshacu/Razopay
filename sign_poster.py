from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter

try:
    from .utils import (
        AUTO_EMBED_STRENGTHS,
        FORWARDED_SHARE_JPEG_QUALITY,
        FORWARDED_SHARE_MAX_DIM,
        generate_image_fingerprint,
        generate_image_hash as _generate_image_hash,
        load_private_key as _load_private_key,
        log_signing_event,
        register_signed_asset,
        read_image,
        sign_digest,
        signature_to_base64,
    )
    from .video_support import is_supported_video_path, sign_video
    from .watermark_embedder import embed_signature
except ImportError:
    from utils import (
        AUTO_EMBED_STRENGTHS,
        FORWARDED_SHARE_JPEG_QUALITY,
        FORWARDED_SHARE_MAX_DIM,
        generate_image_fingerprint,
        generate_image_hash as _generate_image_hash,
        load_private_key as _load_private_key,
        log_signing_event,
        register_signed_asset,
        read_image,
        sign_digest,
        signature_to_base64,
    )
    from video_support import is_supported_video_path, sign_video
    from watermark_embedder import embed_signature


def load_private_key(private_key_path: str | Path | None = None):
    return _load_private_key(private_key_path)


def generate_image_hash(image: str | Path):
    image_array = read_image(image)
    return _generate_image_hash(image_array)


def sign_hash(private_key, image_hash: bytes) -> str:
    signature = sign_digest(private_key, image_hash)
    return signature_to_base64(signature)


def derive_output_path(poster_path: str | Path, output_path: str | Path | None = None) -> Path:
    if output_path is not None:
        return Path(output_path)

    poster = Path(poster_path)
    suffix = poster.suffix.lower() if poster.suffix else ".png"
    return poster.with_name(f"{poster.stem}_signed{suffix}")


def _simulate_forwarded_copy(
    source_path: str | Path,
    output_path: str | Path,
    *,
    max_dim: int = FORWARDED_SHARE_MAX_DIM,
    jpeg_quality: int = FORWARDED_SHARE_JPEG_QUALITY,
) -> Path:
    """
    Re-encode the signed poster as a moderately compressed JPEG.

    This approximates the kind of conversion/resizing common in messaging apps
    so signing can automatically pick a watermark strength that survives it.
    """
    source = Path(source_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as poster:
        if poster.mode in {"RGBA", "LA"} or "transparency" in poster.info:
            rgba = poster.convert("RGBA")
            white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            poster = Image.alpha_composite(white, rgba).convert("RGB")
        else:
            poster = poster.convert("RGB")

        width, height = poster.size
        longest_side = max(width, height)
        if longest_side > max_dim:
            scale = max_dim / float(longest_side)
            resized = (
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
            )
            poster = poster.resize(resized, Image.Resampling.LANCZOS)

        poster.save(
            destination,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
        )

    return destination


def _simulate_whatsapp_screenshot(source_path: str | Path, output_path: str | Path) -> Path:
    """
    Approximate a screenshot of the forwarded image as displayed inside a chat view.

    The image is shown smaller than full size on a dark canvas, which is close to
    the portrait-phone screenshots that users commonly upload back for verification.
    """
    source = Path(source_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as poster:
        poster = poster.convert("RGB")
        display_scale = 0.62 if poster.height >= poster.width else 0.72
        display_size = (
            max(64, int(round(poster.width * display_scale))),
            max(64, int(round(poster.height * display_scale))),
        )
        displayed = poster.resize(display_size, Image.Resampling.BICUBIC)

        canvas = Image.new(
            "RGB",
            (displayed.width + 90, displayed.height + 140),
            (24, 24, 24),
        )
        canvas.paste(displayed, (45, 70))
        canvas.save(destination, format="PNG")

    return destination


def _simulate_blurred_whatsapp_screenshot(source_path: str | Path, output_path: str | Path) -> Path:
    """
    Approximate the softer screenshot rendering often seen after phone capture
    and resharing, where the displayed image loses a little local contrast.
    """
    source = Path(source_path)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="dts_blur_screenshot_") as temp_dir:
        base_screenshot_path = Path(temp_dir) / "whatsapp_base.png"
        _simulate_whatsapp_screenshot(source, base_screenshot_path)

        with Image.open(base_screenshot_path) as screenshot:
            screenshot.convert("RGB").filter(ImageFilter.GaussianBlur(radius=0.9)).save(
                destination,
                format="PNG",
            )

    return destination


def _self_check_signed_output(
    output_path: str | Path,
    public_key_path: str | Path | None = None,
) -> None:
    try:
        from .verify_poster import verify_poster
    except ImportError:
        from verify_poster import verify_poster

    direct_ok, _ = verify_poster(output_path, public_key_path=public_key_path, audit=False)
    if not direct_ok:
        raise RuntimeError("Direct verification of the signed poster failed.")

    with tempfile.TemporaryDirectory(prefix="dts_share_check_") as temp_dir:
        forwarded_path = Path(temp_dir) / "forwarded_preview.jpg"
        _simulate_forwarded_copy(output_path, forwarded_path)
        forwarded_ok, _ = verify_poster(forwarded_path, public_key_path=public_key_path, audit=False)
        if not forwarded_ok:
            raise RuntimeError("Verification failed after the forwarded-share self-check.")

        whatsapp_download_path = Path(temp_dir) / "whatsapp_download.jpg"
        _simulate_forwarded_copy(
            output_path,
            whatsapp_download_path,
            max_dim=960,
            jpeg_quality=46,
        )
        whatsapp_download_ok, _ = verify_poster(
            whatsapp_download_path,
            public_key_path=public_key_path,
            audit=False,
        )
        if not whatsapp_download_ok:
            raise RuntimeError("Verification failed after the WhatsApp download self-check.")

        whatsapp_screenshot_path = Path(temp_dir) / "whatsapp_screenshot.png"
        _simulate_whatsapp_screenshot(forwarded_path, whatsapp_screenshot_path)
        whatsapp_ok, _ = verify_poster(
            whatsapp_screenshot_path,
            public_key_path=public_key_path,
            audit=False,
        )
        if not whatsapp_ok:
            raise RuntimeError("Verification failed after the WhatsApp screenshot self-check.")

        blurred_whatsapp_screenshot_path = Path(temp_dir) / "whatsapp_screenshot_blurred.png"
        _simulate_blurred_whatsapp_screenshot(forwarded_path, blurred_whatsapp_screenshot_path)
        blurred_whatsapp_ok, _ = verify_poster(
            blurred_whatsapp_screenshot_path,
            public_key_path=public_key_path,
            audit=False,
        )
        if not blurred_whatsapp_ok:
            raise RuntimeError("Verification failed after the blurred WhatsApp screenshot self-check.")


def sign_image(
    image,
    output_path: str | Path,
    private_key_path: str | Path | None = None,
    public_key_path: str | Path | None = None,
    self_check: bool = True,
    after_embed=None,
) -> tuple[str, Path]:
    reference_fingerprint = generate_image_fingerprint(image)
    image_hash = _generate_image_hash(image)
    private_key = load_private_key(private_key_path)
    signature_b64 = sign_hash(private_key, image_hash)
    output = Path(output_path)

    attempted_strengths = AUTO_EMBED_STRENGTHS if self_check else (AUTO_EMBED_STRENGTHS[0],)
    last_error: Exception | None = None
    for base_strength in attempted_strengths:
        embed_signature(
            image,
            signature_b64,
            fingerprint=reference_fingerprint,
            output_path=output,
            base_strength=base_strength,
        )
        if after_embed is not None:
            after_embed(output, signature_b64, reference_fingerprint)

        if not self_check:
            return signature_b64, output

        try:
            _self_check_signed_output(output, public_key_path=public_key_path)
            return signature_b64, output
        except Exception as exc:
            last_error = exc

    attempted = ", ".join(str(int(strength)) for strength in attempted_strengths)
    raise RuntimeError(
        "Signed poster self-check failed for the available watermark strengths. "
        f"Tried strengths: {attempted}."
    ) from last_error


def sign_poster(
    poster_path: str | Path,
    output_path: str | Path | None = None,
    private_key_path: str | Path | None = None,
    public_key_path: str | Path | None = None,
    self_check: bool = True,
) -> tuple[str | list[str] | dict[str, object], Path]:
    if Path(poster_path).suffix.lower() == ".pdf":
        try:
            from .pdf_support import sign_pdf
        except ImportError:
            from pdf_support import sign_pdf

        return sign_pdf(
            poster_path,
            output_path=output_path,
            private_key_path=private_key_path,
            public_key_path=public_key_path,
            self_check=self_check,
        )

    if is_supported_video_path(poster_path):
        return sign_video(
            poster_path,
            output_path=output_path,
            private_key_path=private_key_path,
            public_key_path=public_key_path,
            self_check=self_check,
        )

    image = read_image(poster_path)
    output = derive_output_path(poster_path, output_path)

    def register_current_attempt(signed_output: Path, signature_b64: str, reference_fingerprint: bytes) -> None:
        register_signed_asset(
            "image",
            signed_output,
            reference_fingerprint,
            signature_b64,
            source_path=poster_path,
            metadata={
                "height": int(image.shape[0]),
                "width": int(image.shape[1]),
            },
        )

    try:
        signature_b64, signed_output = sign_image(
            image,
            output,
            private_key_path=private_key_path,
            public_key_path=public_key_path,
            self_check=self_check,
            after_embed=register_current_attempt,
        )
        log_signing_event(
            "image_signed",
            asset_type="image",
            input_path=Path(poster_path),
            output_path=signed_output,
            file_format=Path(signed_output).suffix.lower(),
            self_check_enabled=self_check,
        )
        return signature_b64, signed_output
    except Exception as exc:
        log_signing_event(
            "image_signed",
            result="failure",
            asset_type="image",
            input_path=Path(poster_path),
            output_path=output,
            error=str(exc),
            self_check_enabled=self_check,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description="Sign a poster and embed the signature watermark.")
    parser.add_argument("poster", help="Path to the poster image to sign.")
    parser.add_argument(
        "--output",
        "--out",
        default=None,
        help="Where to save the signed poster image. Defaults to <input>_signed with the same extension.",
    )
    parser.add_argument(
        "--private-key",
        default=None,
        help="Optional path to a PEM encoded RSA private key.",
    )
    parser.add_argument(
        "--skip-self-check",
        "--fast",
        action="store_true",
        help="Skip the immediate verification pass after signing for faster output.",
    )
    args = parser.parse_args()

    signature_b64, output_path = sign_poster(
        args.poster,
        output_path=args.output,
        private_key_path=args.private_key,
        self_check=not args.skip_self_check,
    )
    if isinstance(signature_b64, list):
        print(f"Signed PDF saved to: {output_path}")
        print(f"Total pages signed: {len(signature_b64)}")
        for page_number, page_signature in enumerate(signature_b64, start=1):
            print(f"Page {page_number} signature: {page_signature}")
        return

    if isinstance(signature_b64, dict):
        print(f"Signed video saved to: {output_path}")
        print(f"Sampled moments signed: {signature_b64['sampledMoments']}")
        print(f"Audio preserved: {signature_b64['audioPreserved']}")
        for sample_number, sample_signature in enumerate(signature_b64["signatures"], start=1):
            print(f"Sample {sample_number} signature: {sample_signature}")
        return

    print(signature_b64)
    print(f"Signed poster saved to: {output_path}")


if __name__ == "__main__":
    main()
