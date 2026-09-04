from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import ensure_local_storage_dirs, settings
from ..core.trust_shield_adapter import verify_file_adapter
from .audit_service import utc_now
from .firebase_service import FirebaseService


class VerificationService:
    def __init__(self, firebase: FirebaseService | None = None) -> None:
        self.firebase = firebase or FirebaseService()
        ensure_local_storage_dirs()
        self.upload_dir = settings.temp_dir

    def _classify_error(self, exc: Exception) -> tuple[str, str]:
        """Turn an engine failure into one of the four verdicts.

        Order matters. Every "recovered, but ..." message the engine raises
        also contains the word "watermark", so the specific verdicts have to
        be tested before the generic nothing-was-found rules or they are
        swallowed by them.

        This previously matched on the words "signature" and "fingerprint",
        neither of which appears in the engine's actual wrong-key message
        ("...the selected public key did not validate it"). That fell through
        to ERROR, and because the automatic retry across other keys fires only
        on SIGNATURE_INVALID, it never fired — for exactly the case it exists
        to handle. Several other real messages fell through too: "Failed to
        extract watermark payload", "Forwarded-image recovery could not find
        a matching signed image geometry", "Poster is too small to contain a
        valid watermark".

        Kept deliberately in step with trustshield.api._classify in the
        library, so the same document gets the same verdict either way.
        """
        message = str(exc) or exc.__class__.__name__
        lowered = message.lower()

        if "did not validate" in lowered:
            return "SIGNATURE_INVALID", "The hidden proof was found, but the RSA signature was invalid."

        if "fingerprint did not match" in lowered or "content did not match" in lowered:
            return "TAMPERED", "The hidden signature does not match the current visual content."

        if "length does not match" in lowered or "length is invalid" in lowered:
            return "WATERMARK_NOT_FOUND", "No complete Digital Trust Shield proof could be recovered."

        if (
            "watermark" in lowered
            or "recovery could not" in lowered
            or "time budget" in lowered
            or "timed out" in lowered
        ):
            return "WATERMARK_NOT_FOUND", "No hidden Digital Trust Shield proof was found in this image."

        return "ERROR", message

    @staticmethod
    def _inspect_carrier(upload_path: Path) -> dict | None:
        """What the carrier says about this page, on its own.

        Read from the signature alone — the payload is recovered from the
        image in hand, so nothing is compared against any stored record.

        This catches what the fingerprint cannot. The fingerprint is 128 bits
        of whole-page structure and the tolerance that carries it through a
        messaging app also absorbs a repainted figure: a measured 4.1% edit
        passed as authentic on one page and was caught on another, because
        size is not what decides. The carrier is per-block, so an edit shows
        as a contiguous patch of disagreement where recompression shows as
        thin scatter.

        Never allowed to fail a verification.
        """
        try:
            import sys as _sys

            root = str(Path(__file__).resolve().parents[3])
            if root not in _sys.path:
                _sys.path.insert(0, root)
            from razorpayx.locate import EDIT_BLOB_THRESHOLD, inspect_carrier

            from utils import read_image

            finding = inspect_carrier(read_image(upload_path))
            payload = {
                "measurable": finding.measurable,
                "edited": finding.edited,
                "blob": finding.blob,
                "threshold": EDIT_BLOB_THRESHOLD,
                "background_rate": round(finding.background_rate, 4),
            }
            if finding.region is not None:
                payload["damaged_region"] = {
                    "left": finding.region.left,
                    "top": finding.region.top,
                    "right": finding.region.right,
                    "bottom": finding.region.bottom,
                    "peak_x": finding.region.peak_x,
                    "peak_y": finding.region.peak_y,
                    "concentration": round(finding.region.concentration, 2),
                }
            return payload
        except Exception:
            return None

    def _verify_with_public_key(
        self,
        upload_path: Path,
        key_id: str,
        key: dict,
        selected_key_id: str | None = None,
    ) -> dict:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_file:
            key_file.write(str(key["public_key_pem"]).encode("utf-8"))
            public_key_path = Path(key_file.name)
        try:
            result = verify_file_adapter(upload_path, public_key_path)
            carrier = self._inspect_carrier(upload_path)
            if result["valid"]:
                details = dict(result.get("details", {}))
                if carrier:
                    details["carrier"] = carrier
                if selected_key_id and selected_key_id != key_id:
                    details = {
                        **details,
                        "auto_detected_key": True,
                        "selected_key_id": selected_key_id,
                    }

                # The signature is genuine and the fingerprint still matches,
                # but the carrier is torn in one place. That is an edit small
                # enough for the fingerprint's tolerance to absorb, which is
                # exactly the case it was blind to, so the carrier overrules.
                if carrier and carrier.get("edited"):
                    return {
                        "success": False,
                        "result": "TAMPERED",
                        "reason": (
                            "The signature is genuine, but the proof woven through "
                            "the page is torn in one region — that part was edited "
                            "after signing."
                        ),
                        "authority_name": key.get("authority_name"),
                        "authority_id": key.get("authority_id"),
                        "key_id": key_id,
                        "details": details,
                    }
                return {
                    "success": True,
                    "result": "AUTHENTIC",
                    "reason": "Embedded signature verified and visual fingerprint matched.",
                    "authority_name": key.get("authority_name"),
                    "authority_id": key.get("authority_id"),
                    "key_id": key_id,
                    "details": details,
                }
            # The page changed. Say where, from the carrier rather than from
            # any record of what was printed — there is nothing to compare
            # against here, and that is the point: the signature travels with
            # the document and a stored record does not.
            tampered_details = dict(result.get("details", {}))
            if carrier:
                tampered_details["carrier"] = carrier
            return {
                "success": False,
                "result": "TAMPERED",
                "reason": "The document proof was present but did not validate.",
                "authority_name": key.get("authority_name"),
                "authority_id": key.get("authority_id"),
                "key_id": key_id,
                "details": tampered_details,
            }
        except Exception as exc:
            result_code, reason = self._classify_error(exc)
            return {
                "success": False,
                "result": result_code,
                "reason": reason,
                "authority_name": key.get("authority_name"),
                "authority_id": key.get("authority_id"),
                "key_id": key_id,
                "details": {"technical_error": str(exc)},
            }
        finally:
            public_key_path.unlink(missing_ok=True)

    # Trying every key against an image that carries no proof at all multiplies
    # the slowest path by the number of registered keys. Cap it even when a
    # retry is warranted.
    MAX_KEY_RETRIES = 3

    def _active_public_keys_for_retry(self, selected_key_id: str) -> list[dict]:
        return [
            key
            for key in self.firebase.list_public_keys()
            if key.get("active", True) and key.get("key_id") != selected_key_id
        ][: self.MAX_KEY_RETRIES]

    @staticmethod
    def _is_worth_retrying_with_other_keys(result: str) -> bool:
        """Only a key mismatch is worth re-testing against other keys.

        SIGNATURE_INVALID means a watermark was recovered but the selected key
        did not validate it — exactly the case where the document belongs to a
        different authority, so another key may succeed.

        WATERMARK_NOT_FOUND means no proof was recovered at all, and TAMPERED
        means one was recovered and validated but the visible content has since
        changed. Neither verdict can be altered by trying a different key, so
        retrying only repeats the most expensive path once per registered key.
        """
        return result == "SIGNATURE_INVALID"

    async def verify_upload(self, file: UploadFile, key_id: str) -> dict:
        key = self.firebase.get_document("public_keys", key_id)
        if not key:
            raise ValueError(f"Public key not found: {key_id}")

        verification_id = f"ver_{uuid4().hex[:16]}"
        filename = Path(file.filename or "verification_upload.png").name
        suffix = Path(filename).suffix.lower() or ".png"
        upload_path = self.upload_dir / f"{verification_id}{suffix}"

        with upload_path.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        try:
            response = self._verify_with_public_key(upload_path, key_id, key)

            if not response["success"] and self._is_worth_retrying_with_other_keys(response["result"]):
                for candidate_key in self._active_public_keys_for_retry(key_id):
                    candidate_key_id = str(candidate_key.get("key_id"))
                    candidate_response = self._verify_with_public_key(
                        upload_path,
                        candidate_key_id,
                        candidate_key,
                        selected_key_id=key_id,
                    )
                    if candidate_response["success"]:
                        response = candidate_response
                        break

            log_data = {
                "verification_id": verification_id,
                "uploaded_filename": filename,
                "selected_key_id": key_id,
                "authority_id": response.get("authority_id") or key.get("authority_id"),
                "result": response["result"],
                "reason": response["reason"],
                "confidence_or_distance": response["details"].get("distance") if response.get("details") else None,
                "verified_at": utc_now(),
                "uploaded_file_storage_path_optional": None,
            }
            self.firebase.add_auto_document("verification_logs", log_data)
            return response
        finally:
            try:
                upload_path.unlink(missing_ok=True)
            except Exception:
                pass
