from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException

from ..config import settings
from ..schemas import LoginRequest, LoginResponse
from ..security import admin_status, verify_identity


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
