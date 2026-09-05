from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from ..config import ensure_local_storage_dirs, settings
from ..core.trust_shield_adapter import sign_file_adapter, visual_fingerprint_hex
from .audit_service import AuditService, utc_now
from .document_store import get_document_store
from .firebase_service import FirebaseService
from .key_service import KeyService
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

    @staticmethod
    def _download_url(document_id: str) -> str:
        """Where a client fetches the signed file.

        Always this backend, never the object store directly. The link then
        survives a change of storage provider, carries the per-account access
        check, and never puts store credentials in front of a browser.
        """
        return f"{settings.public_base_url}/api/documents/{document_id}/file"

    async def sign_upload(
        self,
        file: UploadFile,
        authority_id: str,
        key_id: str,
        signed_by: dict | None = None,
    ) -> dict:
        # Ownership is checked here, not only in the console. The console
        # offers an account nothing but its own authorities, but the console
        # is not the security boundary — an authority_id is a form field, and
        # anyone can post a different one.
        authority = KeyService(self.firebase).require_authority(authority_id, signed_by)
        key = self.firebase.get_document("public_keys", key_id)
        if not key or key.get("authority_id") != authority_id:
            raise ValueError("Selected key does not belong to the selected authority.")

        original_filename = self._safe_filename(file.filename or "document.png")
        suffix = Path(original_filename).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise ValueError("Unsupported file type. Use PNG, JPG, JPEG, or PDF.")

        document_id = f"doc_{uuid4().hex[:16]}"
        output_suffix = ".pdf" if suffix == ".pdf" else ".png"
        # Both of these are scratch. The signed output is handed to the
        # document store once the engine has finished with it, and the store
        # decides where it durably lives — a second copy here would only be a
        # copy that the next restart deletes.
        upload_path = self.temp_dir / f"{document_id}_{original_filename}"
        output_path = self.temp_dir / f"{document_id}_signed{output_suffix}"

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

            signed_filename = output_path.name
            store = get_document_store()
            storage_path = f"signed_documents/{authority_id}/{document_id}/{signed_filename}"
            store.put(output_path, storage_path)
            storage_type = store.name
            signed_url = self._download_url(document_id)

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
                # Who signed it, so an administrator can see every account's
                # work and a member can be shown only their own.
                "signed_by_uid": (signed_by or {}).get("uid"),
                "signed_by_email": (signed_by or {}).get("email"),
                "signing_mode": "invisible_watermark",
                # The signature woven into the pixels, which is what lets a
                # later verification find this record from the document alone.
                # Without it the filed copy cannot be located, and localisation
                # falls back to the carrier — which cannot tell an editor's
                # redraw from a forger's.
                "watermark_signature": (
                    sign_result["signature"]
                    if isinstance(sign_result.get("signature"), str) else None
                ),
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
                    actor=(signed_by or {}).get("email") or "system",
                    actor_uid=(signed_by or {}).get("uid"),
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
            # Both paths are scratch now, whichever store is in use.
            for scratch in (upload_path, output_path):
                try:
                    scratch.unlink(missing_ok=True)
                except OSError:
                    pass
