from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..security import can_administer
from ..security import require_admin
from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("")
def list_documents(
    authority_id: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
):
    """Signed documents visible to the caller.

    An administrator sees every document on the system. A member sees only
    what they signed themselves, so one account's work is never exposed to
    another.
    """
    documents = FirebaseService().list_signed_documents(authority_id=authority_id)
    if can_administer(admin.get("role", "member")):
        return documents

    uid = admin.get("uid")
    return [document for document in documents if document.get("signed_by_uid") == uid]
