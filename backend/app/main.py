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

    # Without a persistent disk the registry has to live in Firestore, or the
    # proof needed to recover a watermark from a forwarded or screenshotted
    # image disappears the next time the container restarts.
    if settings.registry_backend == "firestore":
        # Never let this abort startup. A service that refuses to boot cannot
        # serve /api/health, so the host reports a failed deploy instead of a
        # running service with one degraded subsystem.
        try:
            import sys
            from pathlib import Path as _Path

            project_root = _Path(__file__).resolve().parents[2]
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from utils import set_registry_storage

            from .services.registry_storage import FirestoreRegistryStorage

            set_registry_storage(FirestoreRegistryStorage())
        except Exception as exc:  # pragma: no cover - defensive
            print(f"WARNING: Firestore registry backend not installed: {exc}")


def _email_configured() -> bool:
    from .services.email_service import EmailService

    return EmailService().configured


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
        "persistence": {
            "registry": settings.registry_backend,
            "private_keys": settings.key_store_backend,
        },
        "admin_auth": {
            "required": settings.require_admin_auth,
            # Whether approval emails can be sent at all — the difference
            # between "not configured" and "configured but failing" is
            # otherwise invisible from outside.
            "approval_email": "configured" if _email_configured() else "not configured",
        },
        "chatbot": {
            "tavily": "configured" if settings.tavily_api_key else "missing",
            "groq": "configured" if settings.groq_api_key else "missing",
            "model": settings.groq_model,
        },
    }
