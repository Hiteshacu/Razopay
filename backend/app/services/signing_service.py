from __future__ import annotations

import mimetypes
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import ensure_local_storage_dirs, settings
from ..core.trust_shield_adapter import sign_file_adapter, visual_fingerprint_hex
from .audit_service import AuditService, utc_now
from .firebase_service import FirebaseService
from .private_key_store import PrivateKeyStore


ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".pdf"}


class SigningService:
    def __init__(
        self,
        firebase: FirebaseService | None = None,
        key_store: PrivateKeyStore | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.firebase = firebase or FirebaseService()
        self.key_store = key_store or PrivateKeyStore()
        self.audit = audit or AuditService(self.firebase)
        ensure_local_storage_dirs()
        self.temp_dir = settings.temp_dir
        self.original_dir = settings.original_documents_dir
        self.signed_dir = settings.signed_documents_dir

    def _safe_filename(self, filename: str) -> str:
        stem = Path(filename).stem or "document"
        suffix = Path(filename).suffix.lower() or ".png"
        safe_stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem).strip("_")
        return f"{safe_stem or 'document'}{suffix}"

    def _local_download_url(self, signed_filename: str) -> str:
        return f"http://127.0.0.1:8000/uploads/signed_documents/{signed_filename}"

    async def sign_upload(self, file: UploadFile, authority_id: str, key_id: str) -> dict:
        authority = self.firebase.get_document("authorities", authority_id)
        if not authority:
            raise ValueError(f"Authority not found: {authority_id}")
        key = self.firebase.get_document("public_keys", key_id)
        if not key or key.get("authority_id") != authority_id:
            raise ValueError("Selected key does not belong to the selected authority.")

        original_filename = self._safe_filename(file.filename or "document.png")
        suffix = Path(original_filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file type. Use PNG, JPG, JPEG, or PDF.")

        document_id = f"doc_{uuid4().hex[:16]}"
        output_suffix = ".pdf" if suffix == ".pdf" else ".png"
        if settings.use_local_storage:
            upload_path = self.original_dir / f"{document_id}_{original_filename}"
            output_path = self.signed_dir / f"{document_id}_signed{output_suffix}"
        else:
            upload_path = self.temp_dir / f"{document_id}_{original_filename}"
            output_path = self.temp_dir / f"{document_id}_signed{output_suffix}"

        signing_completed = False

        try:
            with upload_path.open("wb") as handle:
                shutil.copyfileobj(file.file, handle)

            with self.key_store.temporary_private_key_file(authority_id, key_id) as private_key_path:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as key_file:
                    key_file.write(str(key["public_key_pem"]).encode("utf-8"))
                    public_key_path = Path(key_file.name)
                try:
                    sign_result = sign_file_adapter(
                        upload_path,
                        output_path,
                        private_key_path,
                        public_key_path=public_key_path,
                    )
                finally:
                    public_key_path.unlink(missing_ok=True)
            signing_completed = True

            signed_filename = output_path.name
            if settings.use_local_storage:
                storage_type = "local"
                storage_path = f"signed_documents/{signed_filename}"
                signed_url = self._local_download_url(signed_filename)
            else:
                storage_type = "firebase_storage"
                storage_path = f"signed_documents/{authority_id}/{document_id}/signed_output{output_suffix}"
                content_type = mimetypes.guess_type(str(output_path))[0] or "application/octet-stream"
                signed_url = self.firebase.upload_file(output_path, storage_path, content_type=content_type)

            metadata = {
                "document_id": document_id,
                "authority_id": authority_id,
                "authority_name": authority.get("authority_name"),
                "public_key_id": key_id,
                "key_id": key_id,
                "original_filename": original_filename,
                "signed_filename": signed_filename,
                "file_type": suffix.removeprefix(".").upper(),
                "visual_fingerprint_hash": visual_fingerprint_hex(upload_path),
                "storage_type": storage_type,
                "download_url": signed_url,
                "signed_file_storage_path": storage_path,
                "signed_file_download_url": signed_url,
                "created_at": utc_now(),
                "signature_status": "signed",
                "status": "SIGNED",
                "signing_mode": "invisible_watermark",
                "notes": "Signed by Digital Trust Shield FastAPI backend.",
            }
            try:
                self.firebase.create_document("signed_documents", document_id, metadata)
            except Exception as exc:
                raise RuntimeError(
                    f"Document was signed and stored using {storage_type}, "
                    f"but Firestore metadata save failed: {exc}"
                ) from exc
            try:
                self.audit.record(
                    "DOCUMENT_SIGNED",
                    authority_id=authority_id,
                    key_id=key_id,
                    document_id=document_id,
                    details={"original_filename": original_filename, "storage_path": storage_path},
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Document was signed and Firestore metadata was saved, but audit logging failed: {exc}"
                ) from exc
            return {
                "success": True,
                "document_id": document_id,
                "signed_file_url": signed_url,
                "download_url": signed_url,
                "signed_file_storage_path": storage_path,
                "signed_filename": signed_filename,
                "storage_type": storage_type,
                "key_id": key_id,
                "authority_id": authority_id,
                "message": "Document signed successfully",
                "debug": {"signature_type": type(sign_result["signature"]).__name__},
            }
        finally:
            should_cleanup = (not settings.use_local_storage) or (settings.use_local_storage and not signing_completed)
            if should_cleanup:
                try:
                    upload_path.unlink(missing_ok=True)
                    output_path.unlink(missing_ok=True)
                except Exception:
                    pass
