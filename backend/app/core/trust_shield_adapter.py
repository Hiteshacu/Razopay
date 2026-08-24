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
        "details": {"signature_preview": signature_b64[:32] + "..."},
    }


def visual_fingerprint_hex(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg"}:
        return generate_image_fingerprint(read_image(path)).hex()
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
