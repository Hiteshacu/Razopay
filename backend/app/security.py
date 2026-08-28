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

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from firebase_admin import auth as firebase_auth

from .config import settings
from .firebase_client import get_firebase_app
from .services.email_service import EmailService
from .services.firebase_service import FirebaseService


ADMIN_COLLECTION = "admin_users"

# Three roles, deliberately few.
#
#   owner   the account named in OWNER_EMAIL. Approves accounts, grants and
#           revokes roles, and sees every document signed on the system.
#           Cannot be demoted, so the system can never be left with nobody
#           able to administer it.
#   admin   can approve accounts and see all documents, but cannot change
#           anyone's role.
#   member  the default for an approved account: signs documents and sees
#           its own, nothing else.
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"
ROLES = (ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER)


def owner_email() -> str:
    """The single account that always administers the system."""
    configured = settings.owner_email.strip().lower()
    if configured:
        return configured
    return settings.admin_emails[0] if settings.admin_emails else ""


def role_for(record: dict | None, email: str | None) -> str:
    if email and email.lower() == owner_email():
        return ROLE_OWNER
    stored = str((record or {}).get("role") or "").lower()
    return stored if stored in ROLES else ROLE_MEMBER


def can_administer(role: str) -> bool:
    """Whether this role may approve accounts and see everyone's documents."""
    return role in (ROLE_OWNER, ROLE_ADMIN)


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
    if not email:
        return False
    return email == owner_email() or email in settings.admin_emails


def admin_status(identity: dict) -> dict:
    """Whether this identity may act as an authority, approving bootstraps."""
    if not settings.require_admin_auth:
        return {**identity, "approved": True, "reason": "auth_disabled", "role": ROLE_OWNER}

    uid = identity["uid"]
    email = identity.get("email")
    firebase = FirebaseService()

    record = firebase.get_document(ADMIN_COLLECTION, uid)
    if record and record.get("approved"):
        return {**identity, "approved": True, "reason": "approved", "role": role_for(record, email)}

    if _is_bootstrap_admin(email):
        # The owner, or an address seeded through ADMIN_EMAILS: approved on
        # sight so the system always has someone able to administer it.
        role = role_for(None, email)
        if role != ROLE_OWNER:
            role = ROLE_ADMIN
        firebase.create_document(
            ADMIN_COLLECTION,
            uid,
            {
                "uid": uid,
                "email": email,
                "approved": True,
                "approved_via": "seed",
                "role": role,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return {**identity, "approved": True, "reason": "bootstrap", "role": role}

    now = datetime.now(timezone.utc)

    if not record:
        # First sight of this account: record the request so an owner can act
        # on it, rather than approval depending on someone noticing a database
        # row.
        record = {
            "uid": uid,
            "email": email,
            "approved": False,
            "created_at": now.isoformat(),
            "approval_token": secrets.token_urlsafe(32),
            "approval_token_expires": (now + timedelta(days=7)).isoformat(),
            "notification_sent": False,
        }
        firebase.create_document(ADMIN_COLLECTION, uid, record)

    # Notify on every visit until one actually succeeds. Sending used to be
    # attempted only when the record was created, so a request raised before
    # SMTP was configured lost its notification permanently — adding the
    # credentials afterwards could never recover it.
    if not record.get("notification_sent") and _notification_cooldown_passed(record, now):
        sent = _notify_owner_of_request(record.get("email"), str(record.get("approval_token") or ""))
        record["notification_sent"] = sent
        record["notification_attempted_at"] = now.isoformat()
        firebase.create_document(ADMIN_COLLECTION, uid, record)

    return {**identity, "approved": False, "reason": "pending_approval", "role": ROLE_MEMBER}


NOTIFICATION_RETRY_MINUTES = 5


def _notification_cooldown_passed(record: dict, now: datetime) -> bool:
    """Avoid retrying on every single request while SMTP stays broken."""
    attempted = str(record.get("notification_attempted_at") or "")
    if not attempted:
        return True
    try:
        return now - datetime.fromisoformat(attempted) > timedelta(minutes=NOTIFICATION_RETRY_MINUTES)
    except ValueError:
        return True


def _notify_owner_of_request(requester_email: str | None, token: str) -> bool:
    owner = settings.approval_notify_email or owner_email()
    if not owner:
        print("WARNING: no APPROVAL_NOTIFY_EMAIL or ADMIN_EMAILS set; approval request not sent")
        return False

    return EmailService().send_approval_request(
        owner_email=owner,
        requester_email=requester_email or "an account with no email address",
        approve_url=f"{settings.portal_base_url}/?approve={token}",
    )


def list_pending_requests() -> list[dict]:
    """Accounts that have signed in but are not approved yet.

    Records for accounts that no longer exist are dropped. Deleting a user in
    the Firebase console leaves their request behind, and a queue showing
    people who cannot sign in is worse than no queue.
    """
    firebase = FirebaseService()
    try:
        get_firebase_app()
        live_uids = set()
        page = firebase_auth.list_users()
        while page:
            live_uids.update(user.uid for user in page.users)
            page = page.get_next_page()
    except Exception:
        live_uids = None  # cannot check; show everything rather than hide it

    pending = [
        {
            "uid": record.get("uid"),
            "email": record.get("email"),
            "requested_at": record.get("created_at"),
            "notified": bool(record.get("notification_sent")),
        }
        for record in firebase.list_collection(ADMIN_COLLECTION, limit=500)
        if not record.get("approved")
        and (live_uids is None or str(record.get("uid")) in live_uids)
    ]
    pending.sort(key=lambda item: str(item.get("requested_at") or ""), reverse=True)
    return pending


def list_all_users() -> list[dict]:
    """Every account the system knows about, with its role and status."""
    firebase = FirebaseService()
    try:
        get_firebase_app()
        live = {}
        page = firebase_auth.list_users()
        while page:
            for user in page.users:
                live[user.uid] = user.email
            page = page.get_next_page()
    except Exception:
        live = None

    users = []
    for record in firebase.list_collection(ADMIN_COLLECTION, limit=500):
        uid = str(record.get("uid"))
        if live is not None and uid not in live:
            continue  # account deleted in the console; the record is stale
        users.append(
            {
                "uid": uid,
                "email": record.get("email"),
                "approved": bool(record.get("approved")),
                "role": role_for(record, record.get("email")),
                "created_at": record.get("created_at"),
                "approved_at": record.get("approved_at"),
                "approved_by": record.get("approved_by"),
            }
        )
    users.sort(key=lambda item: (not item["approved"], str(item.get("email") or "")))
    return users


def set_role(uid: str, role: str) -> dict:
    if role not in (ROLE_ADMIN, ROLE_MEMBER):
        raise ValueError("Role must be admin or member.")

    firebase = FirebaseService()
    record = firebase.get_document(ADMIN_COLLECTION, uid)
    if not record:
        raise LookupError("That account no longer exists.")
    if (record.get("email") or "").lower() == owner_email():
        # Refusing this is what guarantees the system always has an
        # administrator, whatever else happens to the other accounts.
        raise PermissionError("The owner's role cannot be changed.")

    record["role"] = role
    record["approved"] = True
    firebase.create_document(ADMIN_COLLECTION, uid, record)
    return record


def set_approval(uid: str, *, approved: bool, actor: str) -> dict:
    firebase = FirebaseService()
    record = firebase.get_document(ADMIN_COLLECTION, uid)
    if not record:
        raise LookupError("That request no longer exists.")
    record.update(
        {
            "approved": approved,
            # Approval grants use of the system, not administration of it.
            # Raising someone to admin stays a separate, deliberate act.
            "role": record.get("role") or ROLE_MEMBER,
            "approved_via": "console",
            "approved_by": actor,
            "approved_at": datetime.now(timezone.utc).isoformat(),
            # Retire the emailed link once the decision is made here.
            "approval_token": None,
            "approval_token_expires": None,
        }
    )
    firebase.create_document(ADMIN_COLLECTION, uid, record)
    return record


def delete_request(uid: str) -> dict:
    firebase = FirebaseService()
    record = firebase.get_document(ADMIN_COLLECTION, uid)
    if not record:
        raise LookupError("That request no longer exists.")
    firebase.db.collection(ADMIN_COLLECTION).document(uid).delete()
    return record


def find_approval_request(token: str) -> dict | None:
    """Look up a pending request by its token, if it is still valid."""
    if not token:
        return None
    firebase = FirebaseService()
    for record in firebase.list_collection(ADMIN_COLLECTION, limit=500):
        if not secrets.compare_digest(str(record.get("approval_token") or ""), token):
            continue
        if record.get("approved"):
            return {**record, "state": "already_approved"}
        expires = str(record.get("approval_token_expires") or "")
        try:
            if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
                return {**record, "state": "expired"}
        except ValueError:
            pass
        return {**record, "state": "pending"}
    return None


def approve_request(token: str) -> dict:
    """Grant authority to the account holding this token, once."""
    record = find_approval_request(token)
    if record is None:
        raise LookupError("This approval link is not valid.")
    if record.get("state") == "expired":
        raise LookupError("This approval link has expired.")
    if record.get("state") == "already_approved":
        return {"email": record.get("email"), "already": True}

    firebase = FirebaseService()
    updated = {
        **{k: v for k, v in record.items() if k != "state"},
        "approved": True,
        "approved_via": "email_link",
        "approved_at": datetime.now(timezone.utc).isoformat(),
        # Burn the token so the link cannot be replayed.
        "approval_token": None,
        "approval_token_expires": None,
    }
    firebase.create_document(ADMIN_COLLECTION, str(record["uid"]), updated)
    return {"email": record.get("email"), "already": False}


def require_administrator(identity: dict = Depends(verify_identity)) -> dict:
    """For actions only an owner or admin may take."""
    record = require_admin(identity)
    if not can_administer(record.get("role", ROLE_MEMBER)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action needs an administrator.",
        )
    return record


def require_owner(identity: dict = Depends(verify_identity)) -> dict:
    """For actions only the owner may take, such as changing roles."""
    record = require_admin(identity)
    if record.get("role") != ROLE_OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner can change roles.",
        )
    return record


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
