from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.signing_service import SigningService


router = APIRouter(prefix="/api", tags=["signing"])


@router.post("/sign")
async def sign_document(
    file: UploadFile = File(...),
    authority_id: str = Form(...),
    key_id: str = Form(...),
):
    try:
        return await SigningService().sign_upload(file, authority_id, key_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

