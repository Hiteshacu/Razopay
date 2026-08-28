from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..security import require_admin

from ..schemas import KeyGenerateRequest
from ..services.key_service import KeyService


router = APIRouter(prefix="/api/keys", tags=["keys"])


@router.post("/generate")
def generate_key_pair(payload: KeyGenerateRequest, admin: dict = Depends(require_admin)):
    try:
        return KeyService().generate_key_pair(
            payload.authority_id, payload.authority_name, caller=admin
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/public")
def list_public_keys(authority_id: str | None = Query(default=None)):
    """Every public key, for the verification app.

    Open on purpose. Someone checking a notice has no account, and cannot
    know in advance which office issued it.
    """
    return KeyService().list_public_keys(authority_id=authority_id)


@router.get("")
def list_my_keys(
    authority_id: str | None = Query(default=None),
    admin: dict = Depends(require_admin),
):
    """The keys this account may sign with, which is what the console shows.

    Separate from /public because the two answer different questions. The
    public list exists so anyone can verify anything; this one exists so an
    operator is only offered keys that are theirs to use.
    """
    return KeyService().list_keys_for(admin, authority_id=authority_id)

