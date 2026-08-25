"""Admin authentication built on Firebase Auth.

The portal signs an operator in with Firebase and sends the resulting ID
token on every request. This module verifies that token against the project's
own credentials and decides whether the caller is allowed to act as an
authority.

Signing in is not the same as being allowed to sign documents. Anyone can
create an account, so a second check gates the operations that matter: the
caller's account must be approved in the `admin_users` collection. Emails
listed in ADMIN_EMAILS are approved on first sign-in so the first operator
can get in without a chicken-and-egg problem.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth as firebase_auth

from .config import settings
from .firebase_client import get_firebase_app
from .services.firebase_service import FirebaseService


ADMIN_COLLECTION = "admin_users"


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to continue.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization.split(" ", 1)[1].strip()


def verify_identity(authorization: str | None = Header(default=None)) -> dict:
    """Resolve the caller's Firebase identity, or reject the request."""
    if not settings.require_admin_auth:
        # Authentication disabled — used while setting Firebase Auth up, and
        # for local development against a backend with no Firebase project.
        return {"uid": "auth-disabled", "email": None, "approved": True}

    token = _bearer_token(authorization)
    get_firebase_app()
    try:
        claims = firebase_auth.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "uid": claims.get("uid") or claims.get("sub"),
        "email": (claims.get("email") or "").lower() or None,
        "email_verified": bool(claims.get("email_verified")),
    }


def _is_bootstrap_admin(email: str | None) -> bool:
    return bool(email) and email in settings.admin_emails


def admin_status(identity: dict) -> dict:
    """Whether this identity may act as an authority, approving bootstraps."""
    if not settings.require_admin_auth:
        return {**identity, "approved": True, "reason": "auth_disabled"}

    uid = identity["uid"]
    email = identity.get("email")
    firebase = FirebaseService()

    record = firebase.get_document(ADMIN_COLLECTION, uid)
    if record and record.get("approved"):
        return {**identity, "approved": True, "reason": "approved"}

    if _is_bootstrap_admin(email):
        # Listed in ADMIN_EMAILS: record the approval so the list is only
        # needed to seed the first operators, not to run the service.
        firebase.create_document(
            ADMIN_COLLECTION,
            uid,
            {
                "uid": uid,
                "email": email,
                "approved": True,
                "approved_via": "admin_emails",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {**identity, "approved": True, "reason": "bootstrap"}

    if not record:
        # Remember the request so an existing admin can approve it later
        # rather than the person having to ask out of band.
        firebase.create_document(
            ADMIN_COLLECTION,
            uid,
            {
                "uid": uid,
                "email": email,
                "approved": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return {**identity, "approved": False, "reason": "pending_approval"}


def require_admin(identity: dict = Depends(verify_identity)) -> dict:
    """Dependency for endpoints only an approved authority may call."""
    status_record = admin_status(identity)
    if not status_record["approved"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "This account is not approved to act as an authority yet. "
                "Ask an existing administrator to approve it."
            ),
        )
    return status_record
