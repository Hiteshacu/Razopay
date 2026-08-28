from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import fitz
import numpy as np

try:
    from .utils import (
        AUTO_EMBED_STRENGTHS,
        fingerprint_digest,
        fingerprint_distance,
        generate_image_fingerprint,
        load_private_key,
        load_public_key,
        log_signing_event,
        log_verification_event,
        register_signed_asset,
        read_image,
        sign_digest,
        signature_from_base64,
        signature_to_base64,
        verify_digest_signature,
    )
    from .watermark_embedder import embed_signature
    from .watermark_extractor import extract_watermark_bundle
except ImportError:
    from utils import (
        AUTO_EMBED_STRENGTHS,
        fingerprint_digest,
        fingerprint_distance,
        generate_image_fingerprint,
        load_private_key,
        load_public_key,
        log_signing_event,
        log_verification_event,
        register_signed_asset,
        read_image,
        sign_digest,
        signature_from_base64,
        signature_to_base64,
        verify_digest_signature,
    )
    from watermark_embedder import embed_signature
    from watermark_extractor import extract_watermark_bundle


PDF_RENDER_DPI = 150
PDF_MAX_TOTAL_FINGERPRINT_DISTANCE = 2
PDF_MAX_DHASH_DISTANCE = 1
PDF_MAX_PHASH_DISTANCE = 2


def derive_pdf_output_path(pdf_path: str | Path, output_path: str | Path | None = None) -> Path:
    if output_path is not None:
        return Path(output_path)

    document = Path(pdf_path)
    return document.with_name(f"{document.stem}_signed.pdf")


def render_pdf_pages(pdf_path: str | Path, dpi: int = PDF_RENDER_DPI) -> list[np.ndarray]:
    """Render each page of a PDF into an 8-bit BGR image for watermarking."""
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"Could not read PDF: {pdf_file}")

    scale = dpi / 72.0
    page_images: list[np.ndarray] = []
    with fitz.open(str(pdf_file)) as document:
        if document.page_count == 0:
            raise ValueError("PDF contains no pages.")

        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            samples = np.frombuffer(pixmap.samples, dtype=np.uint8)
            rgb = samples.reshape(pixmap.height, pixmap.width, pixmap.n)
            if pixmap.n == 4:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGBA2BGR)
            else:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            page_images.append(bgr)

    return page_images


def save_page_images_as_pdf(page_images: list[np.ndarray], output_path: str | Path) -> Path:
    """Persist signed page images as a multipage PDF using lossless PNG streams."""
    if not page_images:
        raise ValueError("No page images were provided for PDF export.")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    document = fitz.open()
    try:
        for page_image in page_images:
            height, width = page_image.shape[:2]
            page_width = width * 72.0 / PDF_RENDER_DPI
            page_height = height * 72.0 / PDF_RENDER_DPI
            page = document.new_page(width=page_width, height=page_height)
            success, encoded = cv2.imencode(".png", page_image)
            if not success:
                raise RuntimeError("Failed to encode a signed PDF page as PNG.")
            page.insert_image(
                fitz.Rect(0, 0, page_width, page_height),
                stream=encoded.tobytes(),
            )

        document.save(str(output))
    finally:
        document.close()

    return output


def _verify_pdf_page(page_image: np.ndarray, public_key_path: str | Path | None = None) -> tuple[bool, str]:
    reference_fingerprint, signature_b64 = extract_watermark_bundle(page_image)
    signature = signature_from_base64(signature_b64)
    current_fingerprint = generate_image_fingerprint(page_image)
    public_key = load_public_key(public_key_path)
    signature_ok = verify_digest_signature(
        public_key,
        fingerprint_digest(reference_fingerprint),
        signature,
    )
    distances = fingerprint_distance(reference_fingerprint, current_fingerprint)
    fingerprint_ok = (
        distances["total"] <= PDF_MAX_TOTAL_FINGERPRINT_DISTANCE
        and distances["dhash"] <= PDF_MAX_DHASH_DISTANCE
        and distances["phash"] <= PDF_MAX_PHASH_DISTANCE
    )
    return signature_ok and fingerprint_ok, signature_b64


def _sign_pdf_page(
    page_image: np.ndarray,
    output_path: str | Path,
    private_key_path: str | Path | None = None,
) -> tuple[str, np.ndarray, bytes]:
    """
    Sign one PDF page with a two-pass watermarking flow.

    The first embed establishes the carrier coefficients. We then recompute the
    fingerprint from that signed page, sign the stabilized fingerprint, and
    embed again into the original page. This makes strict page verification
    reliable for PDFs whose rendered pages shift slightly after watermarking.
    """
    private_key = load_private_key(private_key_path)
    output = Path(output_path)
    last_error: Exception | None = None

    for base_strength in AUTO_EMBED_STRENGTHS:
        try:
            with tempfile.TemporaryDirectory(prefix="dts_pdf_page_") as temp_dir:
                temp_root = Path(temp_dir)
                first_pass_path = temp_root / "page_first_pass.png"

                first_fingerprint = generate_image_fingerprint(page_image)
                first_signature_b64 = signature_to_base64(
                    sign_digest(private_key, fingerprint_digest(first_fingerprint))
                )
                embed_signature(
                    page_image,
                    first_signature_b64,
                    fingerprint=first_fingerprint,
                    output_path=first_pass_path,
                    base_strength=base_strength,
                )

                first_pass_image = read_image(first_pass_path)
                stabilized_fingerprint = generate_image_fingerprint(first_pass_image)
                stabilized_signature_b64 = signature_to_base64(
                    sign_digest(private_key, fingerprint_digest(stabilized_fingerprint))
                )

                embed_signature(
                    page_image,
                    stabilized_signature_b64,
                    fingerprint=stabilized_fingerprint,
                    output_path=output,
                    base_strength=base_strength,
                )
                final_image = read_image(output)
                is_valid, _ = _verify_pdf_page(final_image)
                if is_valid:
                    return stabilized_signature_b64, final_image, stabilized_fingerprint
        except Exception as exc:
            last_error = exc

    attempted = ", ".join(str(int(strength)) for strength in AUTO_EMBED_STRENGTHS)
    raise RuntimeError(
        "Signed PDF page failed verification for the available watermark strengths. "
        f"Tried strengths: {attempted}."
    ) from last_error


def sign_pdf(
    pdf_path: str | Path,
    output_path: str | Path | None = None,
    private_key_path: str | Path | None = None,
    public_key_path: str | Path | None = None,
    self_check: bool = True,
) -> tuple[list[str], Path]:
    """
    Digitally sign every page of a PDF and rebuild a signed multipage PDF.

    Each page is rasterized, watermarked independently, and then reassembled so
    verification can report page-level authenticity results later.
    """
    output = derive_pdf_output_path(pdf_path, output_path)

    try:
        page_images = render_pdf_pages(pdf_path)
        page_signatures: list[str] = []
        signed_page_images: list[np.ndarray] = []
        with tempfile.TemporaryDirectory(prefix="dts_pdf_sign_") as temp_dir:
            temp_root = Path(temp_dir)
            for page_number, page_image in enumerate(page_images, start=1):
                signed_page_path = temp_root / f"page_{page_number:04d}.png"
                signature_b64, signed_page_image, stabilized_fingerprint = _sign_pdf_page(
                    page_image,
                    signed_page_path,
                    private_key_path=private_key_path,
                )
                page_signatures.append(signature_b64)
                register_signed_asset(
                    "pdf_page",
                    output,
                    stabilized_fingerprint,
                    signature_b64,
                    source_path=pdf_path,
                    page_number=page_number,
                )
                if self_check:
                    is_valid, _ = _verify_pdf_page(signed_page_image, public_key_path=public_key_path)
                    if not is_valid:
                        raise RuntimeError(f"Signed PDF page {page_number} failed verification.")
                signed_page_images.append(signed_page_image)

        save_page_images_as_pdf(signed_page_images, output)
        log_signing_event(
            "pdf_signed",
            asset_type="pdf",
            input_path=Path(pdf_path),
            output_path=output,
            page_count=len(page_signatures),
            self_check_enabled=self_check,
        )
        return page_signatures, output
    except Exception as exc:
        log_signing_event(
            "pdf_signed",
            result="failure",
            asset_type="pdf",
            input_path=Path(pdf_path),
            output_path=output,
            error=str(exc),
            self_check_enabled=self_check,
        )
        raise


def verify_pdf(
    pdf_path: str | Path,
    public_key_path: str | Path | None = None,
    audit: bool = True,
) -> list[dict[str, object]]:
    """
    Verify every page in a PDF.

    Any page that fails watermark extraction or signature validation is marked
    as fake so callers can point citizens to the exact mismatched page.
    """
    try:
        page_images = render_pdf_pages(pdf_path)
        results: list[dict[str, object]] = []
        for page_number, page_image in enumerate(page_images, start=1):
            try:
                is_valid, signature_b64 = _verify_pdf_page(page_image, public_key_path=public_key_path)
            except Exception:
                is_valid, signature_b64 = False, ""

            results.append(
                {
                    "page": page_number,
                    "valid": is_valid,
                    "signature": signature_b64,
                }
            )

        if audit:
            fake_pages = [page["page"] for page in results if not page["valid"]]
            log_verification_event(
                "pdf_verified",
                result="success" if not fake_pages else "failure",
                asset_type="pdf",
                input_path=Path(pdf_path),
                page_count=len(results),
                fake_pages=fake_pages,
                authentic_pages=[page["page"] for page in results if page["valid"]],
                verification_status="authentic" if not fake_pages else "fake_or_tampered",
            )
        return results
    except Exception as exc:
        if audit:
            log_verification_event(
                "pdf_verified",
                result="failure",
                asset_type="pdf",
                input_path=Path(pdf_path),
                error=str(exc),
                verification_status="verification_error",
            )
        raise
