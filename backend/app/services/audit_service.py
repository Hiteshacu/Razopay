from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from .firebase_service import FirebaseService


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AuditService:
    def __init__(self, firebase: FirebaseService | None = None) -> None:
        self.firebase = firebase or FirebaseService()

    def _latest_hash(self) -> str:
        logs = self.firebase.list_collection("audit_logs", limit=200)
        if not logs:
            return "0" * 64
        latest = sorted(logs, key=lambda item: item.get("timestamp", ""), reverse=True)[0]
        return str(latest.get("current_hash") or "0" * 64)

    def record(
        self,
        event_type: str,
        *,
        actor: str = "system",
        authority_id: str | None = None,
        key_id: str | None = None,
        document_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        previous_hash = self._latest_hash()
        timestamp = utc_now()
        payload = {
            "event_type": event_type,
            "actor": actor,
            "authority_id": authority_id,
            "key_id": key_id,
            "document_id": document_id,
            "timestamp": timestamp,
            "details": details or {},
            "previous_hash": previous_hash,
        }
        payload["current_hash"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()
        self.firebase.add_auto_document("audit_logs", payload)
        return payload

