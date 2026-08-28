from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    list_all_users,
    owner_email,
    require_administrator,
    require_owner,
    set_role,
)
from ..services.firebase_service import FirebaseService


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(admin: dict = Depends(require_administrator)):
    """Everyone on the system, with role and status."""
    return {"owner_email": owner_email(), "users": list_all_users()}


@router.post("/users/{uid}/role")
def change_role(uid: str, payload: dict, owner: dict = Depends(require_owner)):
    """Promote to admin or return to member. Owner only."""
    role = str(payload.get("role") or "").lower()
    if role not in (ROLE_ADMIN, ROLE_MEMBER):
        raise HTTPException(status_code=400, detail="Role must be admin or member.")
    try:
        record = set_role(uid, role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "email": record.get("email"),
        "role": role,
        "message": f"{record.get('email')} is now {'an administrator' if role == ROLE_ADMIN else 'a member'}.",
    }


@router.get("/overview")
def overview(admin: dict = Depends(require_administrator)):
    """System-wide totals, and who signed what.

    A member only ever sees their own work, so these figures exist to give
    an administrator the view across every account rather than a per-account
    slice of it.
    """
    firebase = FirebaseService()
    documents = firebase.list_signed_documents()
    users = list_all_users()

    by_signer: dict[str, dict] = {}
    for document in documents:
        email = str(document.get("signed_by_email") or "unattributed")
        entry = by_signer.setdefault(email, {"email": email, "documents": 0, "last_signed": None})
        entry["documents"] += 1
        created = str(document.get("created_at") or "")
        if created > str(entry["last_signed"] or ""):
            entry["last_signed"] = created

    return {
        "totals": {
            "documents": len(documents),
            "users": len(users),
            "approved_users": sum(1 for user in users if user["approved"]),
            "pending_users": sum(1 for user in users if not user["approved"]),
            "administrators": sum(1 for user in users if user["role"] in ("owner", "admin")),
        },
        "by_signer": sorted(by_signer.values(), key=lambda item: -item["documents"]),
    }
