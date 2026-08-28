from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..security import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    can_see_all_records,
    list_all_users,
    owner_email,
    require_administrator,
    require_owner,
    set_role,
)
from ..services.audit_service import logs_for_account
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
    """Totals for the People page.

    The account figures are system-wide, because approving accounts is an
    administrator's job and they need to see all of them.

    The document figures are not. They are scoped to what the caller is
    allowed to see, so an administrator who may not read another account's
    documents cannot infer them from a count either — "12 documents signed"
    when you signed 3 tells you plenty about the other 9.
    """
    firebase = FirebaseService()
    users = list_all_users()

    sees_everything = can_see_all_records(admin.get("role", ROLE_MEMBER))
    documents = firebase.list_signed_documents()
    if not sees_everything:
        documents = [
            document
            for document in documents
            if document.get("signed_by_uid")
            and document.get("signed_by_uid") == admin.get("uid")
        ]

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
        # Only the owner gets the per-account breakdown; for anyone else it
        # would be a list of one, which is just their own total again.
        "by_signer": (
            sorted(by_signer.values(), key=lambda item: -item["documents"])
            if sees_everything
            else []
        ),
        "documents_scope": "all" if sees_everything else "own",
    }


@router.get("/users/{uid}/activity")
def user_activity(uid: str, owner: dict = Depends(require_owner)):
    """Everything one account has done, on one page.

    Owner only, and deliberately a separate request rather than a wider
    version of the ordinary listings. Every other view in the console shows
    you your own work; seeing somebody else's is a thing you ask for by
    name, about one account at a time. That keeps "whose is this?" from
    being a question you have to ask of every row you look at.

    Public key material only. Private keys never leave the key store, and
    nothing here would be improved by changing that.
    """
    firebase = FirebaseService()

    account = next((user for user in list_all_users() if user["uid"] == uid), None)
    if account is None:
        raise HTTPException(status_code=404, detail="No such account.")

    authorities = [
        record
        for record in firebase.list_collection("authorities")
        if record.get("created_by_uid") == uid
    ]
    keys = [
        {key: value for key, value in record.items() if key != "public_key_pem"}
        for record in firebase.list_public_keys()
        if record.get("created_by_uid") == uid
    ]
    documents = sorted(
        (
            record
            for record in firebase.list_signed_documents()
            if record.get("signed_by_uid") == uid
        ),
        key=lambda item: str(item.get("created_at") or ""),
        reverse=True,
    )
    audit = logs_for_account(firebase.list_collection("audit_logs", limit=500), uid)

    return {
        "user": account,
        "totals": {
            "authorities": len(authorities),
            "keys": len(keys),
            "documents": len(documents),
        },
        "authorities": sorted(authorities, key=lambda item: str(item.get("created_at") or ""), reverse=True),
        "keys": sorted(keys, key=lambda item: str(item.get("created_at") or ""), reverse=True),
        "documents": documents,
        "audit": audit,
    }
