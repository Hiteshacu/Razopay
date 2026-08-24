from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import ensure_local_storage_dirs, settings
from .firebase_client import get_firestore_client, get_storage_bucket
from .routes import audit, auth, authorities, chat, documents, keys, signing, verification


app = FastAPI(
    title="Digital Trust Shield API",
    description="Signing and verification API for invisible RSA + DCT watermark proofs.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=settings.local_upload_root, check_dir=False), name="uploads")

app.include_router(auth.router)
app.include_router(authorities.router)
app.include_router(keys.router)
app.include_router(signing.router)
app.include_router(verification.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(audit.router)


@app.on_event("startup")
def startup_checks():
    ensure_local_storage_dirs()


@app.get("/api/health")
def health_check():
    try:
        firestore_client = get_firestore_client()
        next(firestore_client.collections(), None)
        firestore_status = "enabled"
    except Exception as exc:
        firestore_status = f"error: {exc}"

    if settings.use_local_storage:
        firebase_storage_status = "disabled"
    else:
        try:
            get_storage_bucket()
            firebase_storage_status = "enabled"
        except Exception as exc:
            firebase_storage_status = f"error: {exc}"

    return {
        "status": "ok",
        "firestore": firestore_status,
        "storage_mode": settings.storage_mode,
        "firebase_storage": firebase_storage_status,
        "chatbot": {
            "tavily": "configured" if settings.tavily_api_key else "missing",
            "groq": "configured" if settings.groq_api_key else "missing",
            "model": settings.groq_model,
        },
    }
