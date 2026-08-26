from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..schemas import LoginRequest, LoginResponse
from ..security import admin_status, approve_request, find_approval_request, verify_identity


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def current_admin(identity: dict = Depends(verify_identity)):
    """Who the caller is, and whether they may act as an authority.

    The portal calls this straight after sign-in so it can tell an approved
    operator apart from someone whose account exists but is still waiting,
    and show the right screen instead of a wall of failed requests.
    """
    record = admin_status(identity)
    return {
        "authenticated": True,
        "uid": record.get("uid"),
        "email": record.get("email"),
        "approved": record["approved"],
        "reason": record.get("reason"),
        "auth_required": settings.require_admin_auth,
    }


@router.get("/approval/{token}")
def read_approval_request(token: str):
    """Describe a pending request so the page can show who it is for.

    Deliberately read-only. Mail clients and link scanners fetch URLs in
    messages before a person ever clicks, so approving on a GET would let an
    unopened email grant access by itself. Approval happens on the POST below.
    """
    record = find_approval_request(token)
    if record is None:
        raise HTTPException(status_code=404, detail="This approval link is not valid.")
    return {
        "email": record.get("email"),
        "requested_at": record.get("created_at"),
        "state": record.get("state"),
    }


@router.post("/approval/{token}")
def approve_from_email(token: str):
    """Grant authority to the account named by this token."""
    try:
        result = approve_request(token)
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "success": True,
        "email": result["email"],
        "already_approved": result["already"],
        "message": (
            f"{result['email']} was already approved."
            if result["already"]
            else f"{result['email']} can now sign documents."
        ),
    }


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    """Legacy username/password sign-in.

    Superseded by Firebase Auth and kept only so an existing local setup does
    not break mid-demo. It is refused once real authentication is switched on,
    because it hands out a fixed token that proves nothing.
    """
    if settings.require_admin_auth:
        raise HTTPException(
            status_code=410,
            detail="Password sign-in has been replaced by Firebase authentication.",
        )

    valid_username = secrets.compare_digest(payload.username, settings.admin_username)
    valid_password = secrets.compare_digest(payload.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return LoginResponse(success=True, token="hackathon-admin-session", message="Login successful")
