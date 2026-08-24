from __future__ import annotations

import base64
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from cryptography.fernet import Fernet

from ..config import settings


KEY_COLLECTION = "private_keys"


class PrivateKeyStore:
    """Encrypted-at-rest storage for authority private keys.

    Two backends. `local` writes Fernet ciphertext to disk and suits a laptop
    or any host with durable storage. `firestore` keeps the same ciphertext in
    Firestore, which is what a free Render instance needs because its
    filesystem is wiped on every restart — losing the keys would mean an
    authority could never sign again.

    Either way the plaintext key exists only in memory, and only for the
    duration of one signing call. MASTER_KEY lives in the process environment
    and is never written anywhere, so Firestore only ever holds ciphertext it
    cannot read.
    """

    def __init__(self, root: Path | None = None, firebase=None) -> None:
        if not settings.master_key:
            raise RuntimeError("MASTER_KEY is missing. Generate one with backend/generate_master_key.py.")
        self.root = root or settings.secure_keys_root
        self.fernet = Fernet(settings.master_key.encode("utf-8"))
        self.use_firestore = settings.key_store_backend == "firestore"
        self._firebase = firebase

    @property
    def firebase(self):
        if self._firebase is None:
            from .firebase_service import FirebaseService

            self._firebase = FirebaseService()
        return self._firebase

    def _path_for(self, authority_id: str, key_id: str) -> Path:
        return self.root / authority_id / f"{key_id}.enc"

    def save_private_key(self, authority_id: str, key_id: str, private_key_pem: bytes) -> str:
        encrypted = self.fernet.encrypt(private_key_pem)

        if self.use_firestore:
            self.firebase.create_document(
                KEY_COLLECTION,
                key_id,
                {
                    "key_id": key_id,
                    "authority_id": authority_id,
                    "ciphertext_b64": base64.b64encode(encrypted).decode("ascii"),
                    "encryption": "fernet-master-key",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            return f"{KEY_COLLECTION}/{key_id}"

        target = self._path_for(authority_id, key_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encrypted)
        return str(target)

    def load_private_key_bytes(self, authority_id: str, key_id: str) -> bytes:
        if self.use_firestore:
            document = self.firebase.get_document(KEY_COLLECTION, key_id)
            if not document:
                raise FileNotFoundError(
                    f"Encrypted private key not found in Firestore for key_id={key_id}."
                )
            encrypted = base64.b64decode(str(document["ciphertext_b64"]).encode("ascii"))
            return self.fernet.decrypt(encrypted)

        source = self._path_for(authority_id, key_id)
        if not source.exists():
            raise FileNotFoundError(f"Encrypted private key not found for key_id={key_id}.")
        return self.fernet.decrypt(source.read_bytes())

    @contextmanager
    def temporary_private_key_file(self, authority_id: str, key_id: str) -> Iterator[Path]:
        private_key_bytes = self.load_private_key_bytes(authority_id, key_id)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pem")
        temp_path = Path(temp_file.name)
        try:
            temp_file.write(private_key_bytes)
            temp_file.close()
            yield temp_path
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
