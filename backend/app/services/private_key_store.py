from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cryptography.fernet import Fernet

from ..config import settings


class PrivateKeyStore:
    def __init__(self, root: Path | None = None) -> None:
        if not settings.master_key:
            raise RuntimeError("MASTER_KEY is missing. Generate one with backend/generate_master_key.py.")
        self.root = root or settings.secure_keys_root
        self.fernet = Fernet(settings.master_key.encode("utf-8"))

    def _path_for(self, authority_id: str, key_id: str) -> Path:
        return self.root / authority_id / f"{key_id}.enc"

    def save_private_key(self, authority_id: str, key_id: str, private_key_pem: bytes) -> Path:
        target = self._path_for(authority_id, key_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        encrypted = self.fernet.encrypt(private_key_pem)
        target.write_bytes(encrypted)
        return target

    def load_private_key_bytes(self, authority_id: str, key_id: str) -> bytes:
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

