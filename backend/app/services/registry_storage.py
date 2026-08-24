"""Firestore home for the signed-asset registry.

Free Render instances have no persistent disk, so official_registry.json would
be wiped on every restart — and with it the ability to recover a watermark from
a WhatsApp-compressed or screenshotted image. Keeping the registry in Firestore
makes it outlive the container.

The whole registry lives in one document as a JSON string. That keeps the read
to a single Firestore operation per cold start and sidesteps Firestore's
restrictions on nested arrays. Firestore caps a document at 1 MiB; entries are
roughly 900 bytes each, so the oldest are dropped past a safety threshold
rather than letting a write fail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .firebase_service import FirebaseService


COLLECTION = "engine_state"
DOCUMENT_ID = "signed_registry"
MAX_ENTRIES_BYTES = 800_000


class FirestoreRegistryStorage:
    def __init__(self, firebase: FirebaseService | None = None) -> None:
        self.firebase = firebase or FirebaseService()

    def load(self) -> dict[str, Any] | None:
        document = self.firebase.get_document(COLLECTION, DOCUMENT_ID)
        if not document:
            return None
        try:
            entries = json.loads(document.get("entries_json") or "[]")
        except json.JSONDecodeError:
            entries = []
        return {"version": document.get("version", 1), "entries": entries}

    def save(self, data: dict[str, Any]) -> None:
        entries = list(data.get("entries", []))
        entries_json = json.dumps(entries, sort_keys=True)

        # Drop the oldest entries rather than let a write blow the 1 MiB cap.
        while len(entries_json.encode("utf-8")) > MAX_ENTRIES_BYTES and len(entries) > 1:
            entries.sort(key=lambda entry: str(entry.get("created_at_utc", "")))
            entries = entries[1:]
            entries_json = json.dumps(entries, sort_keys=True)

        self.firebase.create_document(
            COLLECTION,
            DOCUMENT_ID,
            {
                "version": data.get("version", 1),
                "entry_count": len(entries),
                "entries_json": entries_json,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
