from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..security import require_admin

from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    authority_id: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
):
    return FirebaseService().list_signed_documents(authority_id=authority_id)

