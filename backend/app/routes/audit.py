from __future__ import annotations

from fastapi import APIRouter

from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_logs():
    logs = FirebaseService().list_collection("audit_logs", limit=200)
    return sorted(logs, key=lambda item: item.get("timestamp", ""), reverse=True)

