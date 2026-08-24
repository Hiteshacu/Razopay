from __future__ import annotations

from fastapi import APIRouter, Query

from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(authority_id: str | None = Query(default=None)):
    return FirebaseService().list_signed_documents(authority_id=authority_id)

