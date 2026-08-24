"""Move local engine state into Firestore so a diskless host can use it.

Run once from your laptop, before deploying:

    cd backend
    .venv\\Scripts\\python.exe migrate_to_firestore.py

It copies two things:

  1. Encrypted private keys from secure_private_keys/*.enc into the
     `private_keys` collection. The ciphertext is copied verbatim — it is
     never decrypted here, so MASTER_KEY is only needed to prove the files
     are readable, and Firestore only ever receives encrypted bytes.

  2. official_registry.json into `engine_state/signed_registry`, minus any
     entry whose output file no longer exists AND that has no cached
     width/height, since those cannot be used for recovery anyway.

Safe to run more than once — it overwrites by key id rather than duplicating.
"""

from __future__ import annotations

import base64
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent
# BACKEND_ROOT must land ahead of PROJECT_ROOT: the project root holds a
# module named app.py which would otherwise shadow the backend's app package.
for candidate in (str(PROJECT_ROOT), str(BACKEND_ROOT)):
    if candidate in sys.path:
        sys.path.remove(candidate)
    sys.path.insert(0, candidate)

from app.config import settings  # noqa: E402
from app.services.firebase_service import FirebaseService  # noqa: E402
from app.services.private_key_store import KEY_COLLECTION  # noqa: E402
from app.services.registry_storage import (  # noqa: E402
    COLLECTION as REGISTRY_COLLECTION,
    DOCUMENT_ID as REGISTRY_DOCUMENT,
)


def migrate_private_keys(firebase: FirebaseService) -> int:
    source_root = settings.secure_keys_root
    if not source_root.exists():
        print(f"  no local key folder at {source_root} — nothing to copy")
        return 0

    copied = 0
    for key_file in sorted(source_root.glob("*/*.enc")):
        authority_id = key_file.parent.name
        key_id = key_file.stem
        ciphertext = key_file.read_bytes()
        firebase.create_document(
            KEY_COLLECTION,
            key_id,
            {
                "key_id": key_id,
                "authority_id": authority_id,
                "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
                "encryption": "fernet-master-key",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "migrated_from": "local_file",
            },
        )
        print(f"  {authority_id}/{key_id}  ({len(ciphertext)} bytes ciphertext)")
        copied += 1
    return copied


def migrate_registry(firebase: FirebaseService) -> tuple[int, int]:
    registry_path = PROJECT_ROOT / "official_registry.json"
    if not registry_path.exists():
        print("  no official_registry.json — nothing to copy")
        return 0, 0

    data = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    entries = data.get("entries", [])

    usable = []
    for entry in entries:
        metadata = entry.get("metadata")
        has_dimensions = (
            isinstance(metadata, dict)
            and isinstance(metadata.get("width"), int)
            and isinstance(metadata.get("height"), int)
        )
        output_path = entry.get("output_path")
        file_exists = bool(output_path) and Path(output_path).exists()
        # Recovery needs the signed geometry: either cached in metadata, or
        # readable from the file. Neither means the entry is dead weight.
        if has_dimensions or file_exists:
            usable.append(entry)

    from app.services.registry_storage import FirestoreRegistryStorage

    FirestoreRegistryStorage(firebase).save({"version": data.get("version", 1), "entries": usable})
    return len(usable), len(entries) - len(usable)


def main() -> None:
    print(f"Firebase credentials : {settings.credentials_path}")
    if not settings.credentials_path.exists():
        print("ERROR: service account file not found. Check backend/.env.")
        sys.exit(1)
    if not settings.master_key:
        print("ERROR: MASTER_KEY is missing from backend/.env.")
        sys.exit(1)

    firebase = FirebaseService()

    print("\nCopying private keys (ciphertext only, never decrypted):")
    key_count = migrate_private_keys(firebase)

    print("\nCopying signed-asset registry:")
    kept, dropped = migrate_registry(firebase)
    print(f"  {kept} entries copied, {dropped} unusable entries skipped")

    print(
        f"\nDone. {key_count} keys in '{KEY_COLLECTION}', "
        f"registry in '{REGISTRY_COLLECTION}/{REGISTRY_DOCUMENT}'."
    )
    print("Set REGISTRY_BACKEND=firestore and KEY_STORE_BACKEND=firestore on the host.")


if __name__ == "__main__":
    main()
