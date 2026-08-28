from __future__ import annotations

from fastapi import APIRouter, Depends

from ..security import require_admin

from ..services.audit_service import logs_for_account
from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("")
def list_audit_logs(admin: dict = Depends(require_admin)):
    """This account's own audit trail.

    Every account, the owner included. The audit log used to be returned
    whole to anybody signed in, so a member could read the owner's activity
    — which authorities exist, which keys were generated and when — none of
    which is theirs to see.

    The owner reads another account's trail through that account's page
    under People, where asking for it is explicit.
    """
    logs = FirebaseService().list_collection("audit_logs", limit=500)
    return logs_for_account(logs, admin.get("uid"))

