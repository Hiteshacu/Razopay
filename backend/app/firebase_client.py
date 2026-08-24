from __future__ import annotations

from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, firestore, storage

from .config import settings


@lru_cache(maxsize=1)
def get_firebase_app():
    if firebase_admin._apps:
        return firebase_admin.get_app()
    if not settings.credentials_path.exists():
        raise RuntimeError(
            f"Firebase service account not found at {settings.credentials_path}. "
            "Create backend/.env and set FIREBASE_CREDENTIALS."
        )

    cred = credentials.Certificate(str(settings.credentials_path))
    options = {"storageBucket": settings.firebase_storage_bucket} if settings.firebase_storage_bucket else None
    return firebase_admin.initialize_app(cred, options)


def get_firestore_client():
    get_firebase_app()
    return firestore.client()


def get_storage_bucket():
    get_firebase_app()
    if settings.use_local_storage:
        raise RuntimeError("Firebase Storage is disabled because USE_LOCAL_STORAGE=true.")
    if not settings.firebase_storage_bucket:
        raise RuntimeError(
            "Firebase Storage is enabled but FIREBASE_STORAGE_BUCKET is empty. "
            "Set FIREBASE_STORAGE_BUCKET or switch USE_LOCAL_STORAGE=true."
        )
    return storage.bucket(settings.firebase_storage_bucket)
