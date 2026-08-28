from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..security import require_admin

from ..services.signing_service import SigningService


router = APIRouter(prefix="/api", tags=["signing"])


@router.post("/sign")
async def sign_document(
    file: UploadFile = File(...),
    authority_id: str = Form(...),
    key_id: str = Form(...),
    admin: dict = Depends(require_admin),
):
    try:
        return await SigningService().sign_upload(file, authority_id, key_id, signed_by=admin)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

