from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sign_poster import sign_poster  # noqa: E402
from utils import generate_image_fingerprint, read_image  # noqa: E402
from verify_poster import verify_poster  # noqa: E402


def sign_file_adapter(
    input_path: str | Path,
    output_path: str | Path,
    private_key_path: str | Path,
    public_key_path: str | Path | None = None,
) -> dict[str, Any]:
    signature, signed_output = sign_poster(
        input_path,
        output_path=output_path,
        private_key_path=private_key_path,
        public_key_path=public_key_path,
        self_check=True,
    )
    return {
        "signature": signature,
        "signed_output": str(signed_output),
    }


def verify_file_adapter(input_path: str | Path, public_key_path: str | Path) -> dict[str, Any]:
    result = verify_poster(input_path, public_key_path=public_key_path, audit=False)
    if isinstance(result, list):
        tampered_pages = [page for page in result if not page.get("valid")]
        return {
            "valid": not tampered_pages,
            "asset_type": "pdf",
            "details": {"pages": result, "tampered_pages": tampered_pages},
        }
    if isinstance(result, dict):
        return {
            "valid": bool(result.get("isAuthentic")),
            "asset_type": "video",
            "details": result,
        }
    is_valid, signature_b64 = result
    return {
        "valid": bool(is_valid),
        "asset_type": "image",
        # The whole signature, alongside the preview shown to a reader. It is
        # how the copy filed at signing time is found again, and it is not a
        # secret — it is carried in the pixels of every copy of the document.
        # Kept out of `details` so it does not travel to the browser for no
        # reason.
        "signature": signature_b64,
        "details": {"signature_preview": signature_b64[:32] + "..."},
    }


def visual_fingerprint_hex(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return generate_image_fingerprint(read_image(path)).hex()
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def page_fingerprints_hex(path: str | Path) -> list[str]:
    """A perceptual fingerprint for every page of a document.

    One entry for an image, one per page for a PDF. This exists because
    `visual_fingerprint_hex` answers with a SHA-256 of the file for anything
    that is not an image, and a file hash cannot recognise a document that has
    been through anything at all — which makes it useless for the one job that
    matters here, finding the filed copy of a page whose signature an editor
    has destroyed. A page exported from a signed PDF and then edited was
    unfindable for exactly that reason.

    Never raises: a document whose pages cannot be rendered simply has no page
    fingerprints, and lookup falls back to what it had before.
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    try:
        if suffix in {".png", ".jpg", ".jpeg"}:
            return [generate_image_fingerprint(read_image(file_path)).hex()]
        if suffix == ".pdf":
            # The project root is already on sys.path, put there above.
            from pdf_support import render_pdf_pages

            return [generate_image_fingerprint(page).hex()
                    for page in render_pdf_pages(file_path)]
    except Exception as exc:  # pragma: no cover - bookkeeping must not block
        print(f"WARNING: page fingerprints unavailable for {file_path.name}: {exc}", flush=True)
    return []
