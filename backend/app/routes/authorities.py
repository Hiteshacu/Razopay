from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas import AuthorityCreate
from ..services.key_service import KeyService


router = APIRouter(prefix="/api/authorities", tags=["authorities"])


@router.post("")
def create_authority(payload: AuthorityCreate):
    try:
        return KeyService().create_authority(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_authorities():
    return KeyService().list_authorities()

