from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import ensure_local_storage_dirs, settings
from .firebase_client import get_firestore_client, get_storage_bucket
from .routes import (
    admin, audit, auth, authorities, chat, documents, keys, payout_advice, payslip,
    signing, verification,
)


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

# Signed documents are NOT served as static files. They were, and that made
# every signed document readable by anyone who had or guessed its URL, with
# no account check at all. They now go through /api/documents/{id}/file,
# which knows who is asking.

app.include_router(auth.router)
app.include_router(authorities.router)
app.include_router(keys.router)
app.include_router(signing.router)
app.include_router(verification.router)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(audit.router)
app.include_router(admin.router)
app.include_router(payout_advice.router)
app.include_router(payslip.router)


@app.on_event("startup")
def startup_checks():
    ensure_local_storage_dirs()

    # Say plainly when identity is switched off.
    #
    # REQUIRE_ADMIN_AUTH defaults to false so a fresh checkout runs without a
    # Firebase project, and the failure that causes when deployed is entirely
    # silent: every request is admitted as the owner, and every key is written
    # with an empty owner_username because there is no caller to name. Nothing
    # errors. The first sign of trouble is the public verifier failing to find
    # a signer who plainly exists, three screens from the cause.
    if not settings.require_admin_auth:
        print(
            "WARNING: REQUIRE_ADMIN_AUTH is false. Every request is treated as "
            "the owner and no signer is recorded on the keys this instance "
            "creates. Set REQUIRE_ADMIN_AUTH=true on any deployment reachable "
            "from the internet, then create authorities again — records made "
            "now cannot be assigned an owner later.",
            flush=True,
        )

    # Private keys and the registry on a container filesystem do not survive a
    # redeploy. Losing them means the authority can never sign again, and the
    # recovery path for a screenshotted document goes with the registry.
    data_dir = os.getenv("DTS_DATA_DIR", "").strip()
    if settings.key_store_backend == "local" and data_dir and not os.path.ismount(data_dir):
        print(
            f"WARNING: private keys are on the container filesystem "
            f"({settings.secure_keys_dir}) and nothing is mounted at {data_dir}. "
            "A redeploy will destroy them, and the authority will never sign "
            "again. Mount a volume there, or set KEY_STORE_BACKEND=firestore "
            "and REGISTRY_BACKEND=firestore.",
            flush=True,
        )

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


def _email_transport() -> str:
    from .services.email_service import EmailService

    return EmailService().transport


def _document_store_status() -> str:
    """Can the configured document store be constructed?

    Constructing it validates the endpoint, bucket and credentials without
    touching the network — the S3 client itself is built lazily on first use
    — so this is cheap enough to answer on every health check.
    """
    try:
        from .services.document_store import get_document_store

        get_document_store()
    except Exception as exc:
        return f"error: {exc}"
    return "ready"


def _master_key_status() -> str:
    """Is MASTER_KEY present and usable as a Fernet key?

    A wrong-length or mistyped value fails the same way a missing one does,
    from the caller's point of view, so the two are reported separately.
    """
    if not settings.master_key:
        return "missing"
    try:
        from cryptography.fernet import Fernet

        Fernet(settings.master_key.encode("utf-8"))
    except Exception:
        return "invalid: not a 32-byte url-safe base64 key"
    return "configured"


@app.get("/api/ping")
def ping():
    """Cheapest possible proof that the process is running.

    Exists for the keep-alive schedule. A free instance sleeps after fifteen
    minutes without traffic and takes about a minute to wake, so something has
    to knock on the door regularly — but /api/health is the wrong door to
    knock on that often. It reaches Firestore on every call, which spends
    quota a hundred and forty times a day for nothing, and it reports a
    failure when a dependency is degraded even though the service is up. An
    uptime monitor pointed at it would page about a subsystem rather than
    about the thing it is supposed to watch.

    This touches nothing and cannot fail while the process is alive, which is
    exactly the question a keep-alive is asking.
    """
    return {"status": "awake"}


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
        "document_store": settings.document_store_backend,
        # Whether that store can actually be built, which is a different
        # question from which one is named. A store missing its endpoint or
        # credentials reports its backend happily here and then fails on the
        # first signature — so the name alone was never enough to tell an
        # operator whether signing would work.
        "document_store_status": _document_store_status(),
        "firebase_storage": firebase_storage_status,
        "persistence": {
            "registry": settings.registry_backend,
            "private_keys": settings.key_store_backend,
            # Whether keys can actually be written, which is not the same as
            # which backend is configured. Without a usable MASTER_KEY the
            # store refuses to construct, so key generation fails while every
            # other line here still reads healthy — which is exactly the
            # confusing state this field exists to make visible. Reports the
            # shape of the key, never the key.
            "master_key": _master_key_status(),
        },
        "admin_auth": {
            "required": settings.require_admin_auth,
            # Whether approval emails can be sent at all — the difference
            # between "not configured" and "configured but failing" is
            # otherwise invisible from outside.
            # "smtp" is blocked outright on some hosts, so naming the
            # transport says more than a yes/no.
            "approval_email": _email_transport(),
        },
        "chatbot": {
            "tavily": "configured" if settings.tavily_api_key else "missing",
            "groq": "configured" if settings.groq_api_key else "missing",
            "model": settings.groq_model,
        },
    }
