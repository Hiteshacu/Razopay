from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from ..schemas import ChatRequest, ChatResponse
from ..services.chat_service import ChatService


router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        return await ChatService().answer(request)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:400] if exc.response is not None else str(exc)
        raise HTTPException(status_code=502, detail=f"AI/search provider error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach AI/search provider: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
