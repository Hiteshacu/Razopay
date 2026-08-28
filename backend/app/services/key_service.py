from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ..schemas import AuthorityCreate
from ..security import username_for
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
        self._key_store = key_store
        self.audit = audit or AuditService(self.firebase)

    @property
    def key_store(self) -> PrivateKeyStore:
        # Built on first use rather than in __init__ so read-only endpoints —
        # notably GET /api/keys/public, the Android app's first call — keep
        # working when MASTER_KEY is absent. Only key generation needs it.
        if self._key_store is None:
            self._key_store = PrivateKeyStore()
        return self._key_store

    def create_authority(self, payload: AuthorityCreate, caller: dict | None = None) -> dict:
        authority_id = f"auth_{uuid4().hex[:12]}"
        account_email = (caller or {}).get("email")
        data = {
            "authority_id": authority_id,
            "authority_name": payload.authority_name,
            "department": payload.department,
            # The authority own contact address. Not the account that created
            # it, and quite possibly a different organisation entirely.
            "email": payload.email,
            "created_at": utc_now(),
            "status": "ACTIVE",
            # Who this belongs to. Everything downstream hangs off this one
            # field: which keys an account may generate, which authorities it
            # may sign with, and what its console shows it.
            "created_by_uid": (caller or {}).get("uid"),
            "created_by_email": account_email,
            "owner_username": username_for(account_email),
        }
        self.firebase.create_document("authorities", authority_id, data)
        self.audit.record("AUTHORITY_CREATED", actor=account_email or payload.email,
                          actor_uid=(caller or {}).get("uid"),
                          authority_id=authority_id, details=data)
        return data

    @staticmethod
    def _belongs_to(record: dict, caller: dict | None) -> bool:
        """Whether this authority or key is this account's own.

        Strict, with no exemption for the owner. The owner's own console
        should show the owner's own work; mixing every account's authorities
        into one list is what made it impossible to tell whose was whose.
        Another account's records are reached through that account's page
        under People, where you have said whose you want to see.

        It also settles signing: you sign with your own authority, never
        with somebody else's, whatever your role.
        """
        created_by = record.get("created_by_uid")
        return bool(created_by) and created_by == (caller or {}).get("uid")

    def list_authorities(self, caller: dict | None = None) -> list[dict]:
        """The authorities this account may use.

        Scoped, so one operator never sees another operator authority in
        their console. Unscoped, every account could pick any authority on
        the system and issue documents in its name.
        """
        authorities = self.firebase.list_collection("authorities")
        return [a for a in authorities if self._belongs_to(a, caller)]

    def require_authority(self, authority_id: str, caller: dict | None = None) -> dict:
        """Fetch an authority this account may use, or refuse.

        The same message either way. Distinguishing "no such authority" from
        "not yours" would let an account map out the others by guessing ids.
        """
        authority = self.firebase.get_document("authorities", authority_id)
        if not authority or not self._belongs_to(authority, caller):
            raise ValueError(f"Authority not found: {authority_id}")
        return authority

    def generate_key_pair(
        self,
        authority_id: str,
        authority_name: str | None = None,
        caller: dict | None = None,
    ) -> dict:
        authority = self.require_authority(authority_id, caller)

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
            # Copied from the authority rather than from the caller: the key
            # belongs to whoever owns the authority, which stays true even if
            # the two are ever created by different people.
            "created_by_uid": authority.get("created_by_uid"),
            "created_by_email": authority.get("created_by_email"),
            "owner_username": authority.get("owner_username") or "",
        }
        self.firebase.create_document("public_keys", key_id, data)
        self.audit.record(
            "KEY_PAIR_GENERATED",
            actor=authority.get("created_by_email") or "system",
            actor_uid=authority.get("created_by_uid"),
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
        """Every public key on the system, for anyone who asks.

        Deliberately unscoped and unauthenticated. Someone checking a notice
        has no account and no idea which office issued it, so verification
        has to be able to reach every key. These are public keys, and
        publishing them is the entire point of having them.
        """
        return self.firebase.list_public_keys(authority_id=authority_id)

    def list_keys_for(self, caller: dict | None, authority_id: str | None = None) -> list[dict]:
        """The keys this account may sign with, for the console."""
        keys = self.firebase.list_public_keys(authority_id=authority_id)
        return [key for key in keys if self._belongs_to(key, caller)]

    def get_public_key(self, key_id: str) -> dict:
        key = self.firebase.get_document("public_keys", key_id)
        if not key:
            raise ValueError(f"Public key not found: {key_id}")
        return key

