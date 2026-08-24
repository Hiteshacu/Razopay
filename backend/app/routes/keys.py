from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..schemas import KeyGenerateRequest
from ..services.key_service import KeyService


router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.post("/generate")
def generate_key_pair(payload: KeyGenerateRequest):
    try:
        return KeyService().generate_key_pair(payload.authority_id, payload.authority_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/public")
def list_public_keys(authority_id: str | None = Query(default=None)):
    return KeyService().list_public_keys(authority_id=authority_id)

