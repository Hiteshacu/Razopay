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
        message = str(exc) or exc.__class__.__name__
        lowered = message.lower()
        if (
            "watermark marker not found" in lowered
            or ("watermark" in lowered and ("not found" in lowered or "too weak" in lowered))
            or "screenshot recovery could not find" in lowered
            or "time budget" in lowered
            or "timed out" in lowered
        ):
            return "WATERMARK_NOT_FOUND", "No hidden Digital Trust Shield proof was found in this image."
        if "signature" in lowered:
            return "SIGNATURE_INVALID", "The hidden proof was found, but the RSA signature was invalid."
        if "fingerprint" in lowered or "content did not match" in lowered:
            return "TAMPERED", "The hidden signature does not match the current visual content."
        return "ERROR", message

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
            if result["valid"]:
                details = result.get("details", {})
                if selected_key_id and selected_key_id != key_id:
                    details = {
                        **details,
                        "auto_detected_key": True,
                        "selected_key_id": selected_key_id,
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
            return {
                "success": False,
                "result": "TAMPERED",
                "reason": "The document proof was present but did not validate.",
                "authority_name": key.get("authority_name"),
                "authority_id": key.get("authority_id"),
                "key_id": key_id,
                "details": result.get("details", {}),
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

    def _active_public_keys_for_retry(self, selected_key_id: str) -> list[dict]:
        return [
            key
            for key in self.firebase.list_public_keys()
            if key.get("active", True) and key.get("key_id") != selected_key_id
        ]

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

            if not response["success"]:
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
