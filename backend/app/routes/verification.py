from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services.verification_service import VerificationService


router = APIRouter(prefix="/api", tags=["verification"])


@router.post("/verify")
async def verify_document(
    file: UploadFile = File(...),
    key_id: str = Form(...),
):
    try:
        return await VerificationService().verify_upload(file, key_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

