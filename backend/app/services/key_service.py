from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..schemas import AuthorityCreate
from .audit_service import AuditService
from .firebase_service import FirebaseService
from .private_key_store import PrivateKeyStore


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class KeyService:
    def __init__(
        self,
        firebase: FirebaseService | None = None,
        key_store: PrivateKeyStore | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self.firebase = firebase or FirebaseService()
        self.key_store = key_store or PrivateKeyStore()
        self.audit = audit or AuditService(self.firebase)

    def create_authority(self, payload: AuthorityCreate) -> dict:
        authority_id = f"auth_{uuid4().hex[:12]}"
        data = {
            "authority_id": authority_id,
            "authority_name": payload.authority_name,
            "department": payload.department,
            "email": payload.email,
            "created_at": utc_now(),
            "status": "ACTIVE",
        }
        self.firebase.create_document("authorities", authority_id, data)
        self.audit.record("AUTHORITY_CREATED", actor=payload.email, authority_id=authority_id, details=data)
        return data

    def list_authorities(self) -> list[dict]:
        return self.firebase.list_collection("authorities")

    def generate_key_pair(self, authority_id: str, authority_name: str | None = None) -> dict:
        authority = self.firebase.get_document("authorities", authority_id)
        if not authority:
            raise ValueError(f"Authority not found: {authority_id}")

        resolved_authority_name = authority_name or authority.get("authority_name") or "Unknown Authority"
        key_id = f"key_{uuid4().hex[:16]}"
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_key = private_key.public_key()

        private_key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        public_key_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        fingerprint = hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()

        encrypted_path = self.key_store.save_private_key(authority_id, key_id, private_key_pem)
        data = {
            "key_id": key_id,
            "authority_id": authority_id,
            "authority_name": resolved_authority_name,
            "public_key_pem": public_key_pem,
            "algorithm": "RSA-PSS-SHA256",
            "key_size": 2048,
            "created_at": utc_now(),
            "active": True,
            "fingerprint_sha256": fingerprint,
            "storage_path_optional": f"public_keys/{authority_id}/{key_id}.pem",
        }
        self.firebase.create_document("public_keys", key_id, data)
        self.audit.record(
            "KEY_PAIR_GENERATED",
            authority_id=authority_id,
            key_id=key_id,
            details={
                "public_key_fingerprint": fingerprint,
                "encrypted_private_key_path": str(encrypted_path),
                "private_key_storage": "backend_encrypted_fernet",
            },
        )
        return data

    def list_public_keys(self, authority_id: str | None = None) -> list[dict]:
        return self.firebase.list_public_keys(authority_id=authority_id)

    def get_public_key(self, key_id: str) -> dict:
        key = self.firebase.get_document("public_keys", key_id)
        if not key:
            raise ValueError(f"Public key not found: {key_id}")
        return key

