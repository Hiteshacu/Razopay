from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

from ..config import settings
from ..firebase_client import get_firestore_client, get_storage_bucket


class FirebaseService:
    def __init__(self) -> None:
        self.db = get_firestore_client()
        self.bucket = None

    def create_document(self, collection: str, document_id: str, data: dict[str, Any]) -> dict[str, Any]:
        self.db.collection(collection).document(document_id).set(data)
        return data

    def list_collection(self, collection: str, limit: int = 100) -> list[dict[str, Any]]:
        docs = self.db.collection(collection).limit(limit).stream()
        return [doc.to_dict() for doc in docs]

    def get_document(self, collection: str, document_id: str) -> dict[str, Any] | None:
        snapshot = self.db.collection(collection).document(document_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_public_keys(self, authority_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.collection("public_keys")
        if authority_id:
            query = query.where(filter=FieldFilter("authority_id", "==", authority_id))
        return [doc.to_dict() for doc in query.stream()]

    def list_signed_documents(self, authority_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.collection("signed_documents")
        if authority_id:
            query = query.where(filter=FieldFilter("authority_id", "==", authority_id))
        return [doc.to_dict() for doc in query.stream()]

    def upload_file(self, local_path: str | Path, storage_path: str, content_type: str | None = None) -> str:
        if settings.use_local_storage:
            raise RuntimeError("Firebase Storage upload was requested while USE_LOCAL_STORAGE=true.")
        if self.bucket is None:
            self.bucket = get_storage_bucket()
        blob = self.bucket.blob(storage_path)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        if settings.storage_make_public:
            blob.make_public()
            return blob.public_url
        try:
            return blob.generate_signed_url(
                expiration=timedelta(minutes=settings.storage_signed_url_minutes),
                method="GET",
            )
        except Exception:
            # Some hackathon Firebase buckets/service accounts cannot sign URLs locally.
            # Keep the canonical path so the record remains auditable even without a web URL.
            pass
        return f"gs://{self.bucket.name}/{storage_path}"

    def add_auto_document(self, collection: str, data: dict[str, Any]) -> str:
        ref = self.db.collection(collection).document()
        ref.set(data)
        return ref.id
