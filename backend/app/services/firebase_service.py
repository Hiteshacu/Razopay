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

    def latest_document(self, collection: str, order_field: str) -> dict[str, Any] | None:
        """The single most recent document in a collection.

        Firestore orders and limits server-side, so this transfers one document
        however large the collection grows. The caller used to read a page of
        them and sort in Python, which made every write pay for the whole page.
        """
        docs = list(
            self.db.collection(collection)
            .order_by(order_field, direction="DESCENDING")
            .limit(1)
            .stream()
        )
        return docs[0].to_dict() if docs else None

    def get_document(self, collection: str, document_id: str) -> dict[str, Any] | None:
        snapshot = self.db.collection(collection).document(document_id).get()
        return snapshot.to_dict() if snapshot.exists else None

    def list_public_keys(self, authority_id: str | None = None) -> list[dict[str, Any]]:
        query = self.db.collection("public_keys")
        if authority_id:
            query = query.where(filter=FieldFilter("authority_id", "==", authority_id))
        return [doc.to_dict() for doc in query.stream()]

    def find_signed_document_by_signature(self, signature_b64: str) -> dict[str, Any] | None:
        """The record filed for the document carrying this signature.

        Equality on a single field, which Firestore indexes without being
        asked, so this needs no deployed index. Limited to one because the
        signature commits to the page: two records sharing one would mean the
        same document was filed twice, and either copy answers the question.
        """
        if not signature_b64:
            return None
        query = (self.db.collection("signed_documents")
                 .where(filter=FieldFilter("watermark_signature", "==", signature_b64))
                 .limit(1))
        for document in query.stream():
            return document.to_dict()
        return None

    #: Hamming distance, in bits of a 128-bit perceptual fingerprint, within
    #: which two images are the same document.
    #:
    #: Measured on a signed letter against everything that happens to one: a
    #: WhatsApp round trip lands at 2, JPEG quality 20 at 4, a photograph of a
    #: screen at 5, an editor's watermark at 6, the whole page re-typeset by an
    #: editor at 7. Three unrelated documents land at 65, 65 and 67. Twenty
    #: sits in the middle of a gap fifty bits wide.
    FINGERPRINT_MATCH_BITS = 20

    #: How many records to scan for that match. Firestore cannot answer a
    #: Hamming-distance query, so this is a linear pass, and a cap keeps one
    #: verification from reading an unbounded collection.
    FINGERPRINT_SCAN_LIMIT = 500

    def find_signed_document_by_fingerprint(self, fingerprint_hex: str) -> dict[str, Any] | None:
        """The filed record whose document looks like this one.

        The way back to a document whose signature cannot be read at all —
        which is the state an online image editor leaves a page in, having
        redrawn every line of text on it. The perceptual fingerprint survives
        that, because it is a description of the layout rather than of the
        pixels.

        This identifies; it never authenticates. Two documents matching here
        means they are the same page, not that this copy is genuine — that
        question belongs to the signature, and where the signature is gone the
        honest answer says so.
        """
        if not fingerprint_hex:
            return None
        try:
            wanted = bytes.fromhex(fingerprint_hex)
        except ValueError:
            return None

        best = None
        best_distance = self.FINGERPRINT_MATCH_BITS + 1
        for document in (self.db.collection("signed_documents")
                         .limit(self.FINGERPRINT_SCAN_LIMIT).stream()):
            record = document.to_dict() or {}
            stored = record.get("visual_fingerprint_hash")
            if not isinstance(stored, str):
                continue
            try:
                other = bytes.fromhex(stored)
            except ValueError:
                continue
            if len(other) != len(wanted):
                continue
            distance = sum(bin(a ^ b).count("1") for a, b in zip(wanted, other))
            if distance < best_distance:
                best, best_distance = record, distance
        if best is None:
            return None
        return {**best, "fingerprint_distance": best_distance}

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
