from __future__ import annotations

import secrets

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import LoginRequest, LoginResponse


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest) -> LoginResponse:
    valid_username = secrets.compare_digest(payload.username, settings.admin_username)
    valid_password = secrets.compare_digest(payload.password, settings.admin_password)
    if not (valid_username and valid_password):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")
    return LoginResponse(success=True, token="hackathon-admin-session", message="Login successful")

